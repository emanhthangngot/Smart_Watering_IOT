# Build spec — Farm Multi-Agent, Trust-Tiered Autonomy

Tài liệu này là nguồn sự thật duy nhất trong 6 tiếng. Mỗi người đọc phần của mình, và đọc mục 3 (contracts) + mục 9 (luồng phối hợp) để biết mình nối vào đâu.

---

## 1. Nguyên tắc kiến trúc

Bốn luật, vi phạm luật nào là bug luật đó:

1. **Dữ liệu đi một chiều.** `sim → ingest → bundle → trust → agents → tools → verify → api → ui`. Không module nào gọi ngược lên trên.
2. **Quyền hành động là hàm của chất lượng dữ liệu**, cưỡng chế ở tool layer bằng decorator, không bằng prompt.
3. **Agent nào không cần suy luận thì không có LLM.** Chỉ Planning và Reporting gọi model.
4. **Mọi decision phải nối được về ít nhất một reading có thật.** Ràng buộc này ép bằng code, không bằng lời dặn.

Ranh giới sở hữu thư mục (không ai sửa file của người khác):

| Người | Sở hữu |
|---|---|
| A — Lead/Data | `sim/`, `ingest/`, `registry/`, `store/`, `contracts.py`, `fixtures/` |
| B — Trust | `trust/` |
| C — Agents | `agents/`, `graph/` |
| D — Tools/API | `tools/`, `verify/`, `api/` |
| E — Frontend | `frontend/` |

---

## 2. Cây thư mục

```
farm-agent/
├── CLAUDE.md
├── contracts.py                 # A sở hữu — FROZEN sau T+0:25
├── fixtures/
│   ├── bundle_healthy.json      # DCS ~0.92 → AUTO
│   ├── bundle_stale.json        # SOIL_01 cũ 14' → PROPOSE
│   └── bundle_broken.json       # SOIL+PH mất, pump mâu thuẫn → INVESTIGATE
├── backend/
│   ├── sim/          run.py  devices.py  faults.py
│   ├── ingest/       mqtt_client.py  writer.py
│   ├── registry/     specs.py  scopes.py
│   ├── store/        db.py  schema.sql  queries.py  bundle.py
│   ├── trust/        rules.py  score.py  reasons.py  test_trust.py
│   ├── agents/       coordinator.py  field_iot.py  planning.py
│   │                 action.py  reporting.py  context.py  fallback.py
│   ├── graph/        edges.py  explain.py  grounding.py
│   ├── tools/        registry.py  decorator.py  impl.py  hints.py
│   ├── verify/       readback.py  assertions.py  posthoc.py
│   └── api/          main.py  routes_farm.py  routes_trust.py
│                     routes_explain.py  routes_sim.py
└── frontend/         src/App.jsx  components/  api.js
```

---

## 3. `contracts.py` — khóa ở phút 25

Đây là file quan trọng nhất. Bốn người còn lại code dựa vào nó, nên nó phải xong trước mọi thứ khác.

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

Tier = Literal["AUTO", "PROPOSE", "INVESTIGATE"]
Status = Literal["fresh", "stale", "missing"]

# ---------- Data plane ----------
class Reading(BaseModel):
    id: str                       # "r_a3f9c1" hoặc "missing:SOIL_01.soil_moisture"
    device: str
    metric: str
    value: float | None
    unit: str
    ts: datetime | None
    age_s: float | None
    freshness: float = Field(ge=0.0, le=1.0)
    status: Status

class WindowStat(BaseModel):
    delta: float                  # thay đổi trong cửa sổ 10'
    min: float
    max: float
    n: int

class ReadingBundle(BaseModel):
    scope: str                    # "A:irrigation_plan"
    built_at: datetime
    readings: list[Reading]
    window_stats: dict[str, WindowStat]   # key = "SOIL_01.soil_moisture"

# ---------- Trust plane ----------
class TrustVerdict(BaseModel):
    scope: str
    dcs: float = Field(ge=0.0, le=1.0)
    tier: Tier
    breakdown: dict               # {"F":0.71,"C":1.0,"K":0.65,"capped_by":"K<0.5"|None}
    fired_rules: list[str]
    blocked_capabilities: list[str]
    degraded_devices: list[str]
    reason_vi: str
    snapshot_id: str

# ---------- Agent plane ----------
class TaskEnvelope(BaseModel):
    trace_id: str
    intent: Literal["plan_irrigation", "check_session", "handle_degraded"]
    scope: str
    raw_request: str
    requested_at: datetime
    actor: str = "manager"

class PlanItem(BaseModel):
    zone: str
    start: str                    # "05:30"
    duration_min: int = Field(ge=0, le=120)
    target_moisture_pct: float | None = None
    priority: int = Field(ge=1, le=5)
    rationale_vi: str
    evidence: list[str] = Field(min_length=1)

class IrrigationPlan(BaseModel):
    items: list[PlanItem]
    assumptions_vi: list[str] = []
    needs_verification_vi: list[str] = []
    unavailable_devices: list[str] = []

class TicketRequest(BaseModel):
    title_vi: str
    devices: list[str]
    reason_vi: str
    evidence: list[str] = []
    priority: int = 3

# ---------- Action plane ----------
class ActionResult(BaseModel):
    ok: bool
    tool: str
    entity_type: str | None = None
    entity_id: str | None = None
    params: dict = {}
    error: str | None = None      # "TIER_DENIED" | "ASSERTION_FAILED" | ...
    required: Tier | None = None
    current: Tier | None = None
    dcs: float | None = None
    hint: str | None = None

class Verification(BaseModel):
    action_id: str
    method: Literal["readback", "assertion", "posthoc"]
    expected: dict
    observed: dict
    passed: bool
    detail: dict = {}

# ---------- Reporting ----------
class FarmReport(BaseModel):
    trace_id: str
    summary_manager_vi: str       # 3-5 câu, ưu tiên hành động
    detail_engineer_vi: str       # có số liệu, breakdown DCS
    data_limitations_vi: list[str]
    tier: Tier
    dcs: float
```

**Quy tắc đổi contract:** ai cần đổi thì hô lên nhóm, chỉ A sửa, sửa xong push ngay và báo. Không tự sửa.

---

## 4. Component: `sim/` (A)

**Có gì bên trong**

- `devices.py` — 6 async task, mỗi task một chu kỳ publish. Giữ một `WorldState` dùng chung để các thiết bị liên kết nhân quả với nhau.
- `faults.py` — các cờ sự cố bật/tắt được.
- `run.py` — entrypoint, publish lên broker.

**`WorldState` — thứ làm cho demo thuyết phục**

```python
@dataclass
class WorldState:
    soil_moisture: float = 34.0
    tank_level: float = 78.0
    pump_on: bool = False
    flow_rate: float = 0.0
    sim_clock: datetime = field(default_factory=utcnow)
    faults: set[str] = field(default_factory=set)

    def tick(self, dt: float):
        et = 0.0009 * dt * (1 + 0.02 * (self.air_temp() - 25))
        self.soil_moisture -= et
        if self.pump_on:
            self.flow_rate = 45.0
            self.tank_level -= (self.flow_rate * dt / 60) / TANK_LITERS * 100
            if "pump_no_effect" not in self.faults:
                self.soil_moisture += 0.055 * dt
        else:
            self.flow_rate = 0.0
        if "tank_leak" in self.faults:
            self.tank_level -= 0.004 * dt
        self.soil_moisture = clamp(self.soil_moisture, 5, 60)
        self.tank_level = clamp(self.tank_level, 0, 100)
```

**Chu kỳ publish** — khớp TTL trong registry: PUMP 10s, TANK 30s, SOIL 60s, SUN 60s, WEATHER 120s, PH 300s.

**API sự cố** (D expose qua `routes_sim.py`, gọi vào đây):

```
POST /sim/device/{code}/stop          ngừng publish
POST /sim/device/{code}/resume
POST /sim/fault/pump_no_effect        bật/tắt
POST /sim/fault/tank_leak
POST /sim/pump/{on|off}
POST /sim/scenario/{1|2|3}            reset về trạng thái kịch bản
```

**Không được làm:** sinh số ngẫu nhiên độc lập cho từng thiết bị. Nếu TANK không giảm khi PUMP chạy, mọi consistency rule của B sẽ cháy sai.

---

## 5. Component: `ingest/` + `registry/` + `store/` (A)

### 5.1 `ingest/mqtt_client.py`

Subscribe `farm/+/+`. Mỗi message → `writer.write_reading(device, metric, value)`.

```python
def write_reading(device, metric, value):
    spec = REGISTRY.get((device, metric))
    if spec is None: return           # metric không khai báo → bỏ, không crash
    rid = "r_" + uuid4().hex[:6]
    db.execute(
        "INSERT INTO readings (id, device, metric, value, unit, ts, received_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (rid, device, metric, value, spec.unit, utcnow(), utcnow()))
```

**Bắt buộc:** ID do server sinh. Đây là cơ chế bắt hallucination của C — LLM không đoán được `r_a3f9c1`.
**Bắt buộc:** dùng `received_at` của server, không tin `ts` trong payload.

### 5.2 `registry/specs.py`

```python
@dataclass
class Spec:
    ttl: int
    unit: str
    scopes: dict[str, int]        # scope -> trọng số
    required_in: set[str] = field(default_factory=set)

REGISTRY = {
 ("SOIL_01","soil_moisture"): Spec(300,"%",    {"A:irrigation_plan":3,"A:session_check":3}, {"A:irrigation_plan","A:session_check"}),
 ("SOIL_01","temperature"):   Spec(300,"°C",   {"A:irrigation_plan":1}),
 ("WEATHER_01","temperature"):Spec(600,"°C",   {"A:irrigation_plan":1}),
 ("WEATHER_01","humidity"):   Spec(600,"%",    {"A:irrigation_plan":2}),
 ("PUMP_01","flow_rate"):     Spec(30,"L/min", {"A:irrigation_plan":2,"A:session_check":3}, {"A:session_check"}),
 ("PUMP_01","power"):         Spec(30,"W",     {"A:session_check":1}),
 ("PH_01","ph"):              Spec(900,"pH",   {"tank:water_quality":3}, {"tank:water_quality"}),
 ("TANK_01","level"):         Spec(120,"%",    {"A:irrigation_plan":3,"A:session_check":2,"tank:water_quality":2}, {"A:irrigation_plan"}),
 ("SUN_01","lux"):            Spec(300,"lx",   {"A:irrigation_plan":1}),
}
```

Ba scope: `A:irrigation_plan`, `A:session_check`, `tank:water_quality`. Khi cần cắt gấp, sửa đúng file này.

### 5.3 `store/bundle.py`

```python
def get_bundle(scope: str) -> ReadingBundle:
    readings = []
    for (dev, metric), spec in REGISTRY.items():
        if scope not in spec.scopes:
            continue
        row = latest(dev, metric, within=timedelta(minutes=30))
        if row is None:
            readings.append(Reading(
                id=f"missing:{dev}.{metric}", device=dev, metric=metric,
                value=None, unit=spec.unit, ts=None, age_s=None,
                freshness=0.0, status="missing"))
            continue
        age = (utcnow() - row.received_at).total_seconds()
        f = freshness(age, spec.ttl)
        readings.append(Reading(
            id=row.id, device=dev, metric=metric, value=row.value, unit=spec.unit,
            ts=row.received_at, age_s=age, freshness=f,
            status="fresh" if f >= 0.99 else ("stale" if f > 0 else "missing")))
    return ReadingBundle(scope=scope, built_at=utcnow(), readings=readings,
                         window_stats=window_stats(scope, minutes=10))

def freshness(age_s, ttl):
    if age_s <= ttl: return 1.0
    if age_s >= 3 * ttl: return 0.0
    return 1.0 - (age_s - ttl) / (2 * ttl)
```

**Bắt buộc:** reading `missing` vẫn nằm trong list. Nếu lọc bỏ, B không phân biệt được "không thuộc scope" và "thiết bị chết".

`window_stats` trả `{"SOIL_01.soil_moisture": WindowStat(delta=+0.4, ...)}` — B cần *xu hướng* để chạy rule `pump_on_soil_flat`.

### 5.4 `store/schema.sql`

```sql
CREATE TABLE readings (
  id TEXT PRIMARY KEY, device TEXT, metric TEXT, value REAL, unit TEXT,
  ts TIMESTAMP, received_at TIMESTAMP);
CREATE INDEX idx_readings_lookup ON readings(device, metric, received_at DESC);

CREATE TABLE trust_snapshots (
  id TEXT PRIMARY KEY, scope TEXT, dcs REAL, tier TEXT,
  breakdown TEXT, fired_rules TEXT, created_at TIMESTAMP);

CREATE TABLE decisions (
  id TEXT PRIMARY KEY, trace_id TEXT, statement TEXT, scope TEXT,
  tier_at_time TEXT, trust_snapshot_id TEXT, agent TEXT, created_at TIMESTAMP);

CREATE TABLE actions (
  id TEXT PRIMARY KEY, trace_id TEXT, tool TEXT, params TEXT,
  idempotency_key TEXT UNIQUE, result TEXT, created_at TIMESTAMP);

CREATE TABLE verifications (
  id TEXT PRIMARY KEY, action_id TEXT, method TEXT,
  expected TEXT, observed TEXT, passed INTEGER, detail TEXT);

CREATE TABLE edges (src TEXT, dst TEXT, rel TEXT, trace_id TEXT);
CREATE INDEX idx_edges_dst ON edges(dst);

CREATE TABLE schedules (
  id TEXT PRIMARY KEY, zone TEXT, start TEXT, duration_min INTEGER,
  priority INTEGER, status TEXT, created_at TIMESTAMP);
CREATE TABLE drafts (
  id TEXT PRIMARY KEY, payload TEXT, status TEXT, dcs REAL, created_at TIMESTAMP);
CREATE TABLE tickets (
  id TEXT PRIMARY KEY, title TEXT, devices TEXT, reason TEXT,
  assignee TEXT, priority INTEGER, status TEXT, created_at TIMESTAMP);
CREATE TABLE notifications (
  id TEXT PRIMARY KEY, channel TEXT, body TEXT, created_at TIMESTAMP);
CREATE TABLE reports (
  id TEXT PRIMARY KEY, trace_id TEXT, payload TEXT, created_at TIMESTAMP);
```

Dùng `PRAGMA journal_mode=WAL` để ingest thread và API không khóa nhau.

---

## 6. Component: `trust/` (B)

**Nhận:** `ReadingBundle` + scope. **Trả:** `TrustVerdict`. **Không** gọi LLM, **không** chạm DB (trừ ghi snapshot).

### 6.1 `rules.py`

Mỗi rule là hàm thuần `(bundle) -> bool`.

```python
RULES = [
  Rule("pump_on_soil_flat", 0.35,
       "PUMP_01 đang chạy nhưng SOIL_01 gần như không tăng",
       lambda b: val(b,"PUMP_01.flow_rate") > 5 and delta(b,"SOIL_01.soil_moisture") < 1.0),

  Rule("tank_drain_no_pump", 0.30,
       "TANK_01 giảm nhưng PUMP_01 không hoạt động",
       lambda b: delta(b,"TANK_01.level") < -2.0 and val(b,"PUMP_01.flow_rate") < 1),

  Rule("lux_night", 0.25,
       "SUN_01 báo sáng bất thường trong khung giờ đêm",
       lambda b: val(b,"SUN_01.lux") > 1000 and is_night(b.built_at)),

  Rule("ph_out_of_range", 0.20,
       "PH_01 nằm ngoài dải hợp lý, nghi cảm biến lỗi",
       lambda b: not (3.0 <= val(b,"PH_01.ph") <= 11.0)),

  Rule("soil_jump", 0.25,
       "SOIL_01 nhảy bất thường mà không có tưới",
       lambda b: delta(b,"SOIL_01.soil_moisture") > 15 and val(b,"PUMP_01.flow_rate") < 1),
]
```

`val()` và `delta()` trả `None` khi thiếu dữ liệu; rule tự bỏ qua (`if None → False`). Rule không được ném exception, bao giờ cũng trả bool.

### 6.2 `score.py`

```python
def compute_trust(bundle, scope) -> TrustVerdict:
    specs = [(d, m, s) for (d, m), s in REGISTRY.items() if scope in s.scopes]
    wsum = sum(s.scopes[scope] for _, _, s in specs)

    F = sum(s.scopes[scope] * r.freshness for r, s in pair(bundle, specs)) / wsum
    C = sum(s.scopes[scope] for r, s in pair(bundle, specs) if r.status != "missing") / wsum

    fired = [r.name for r in RULES if safe(r.fn, bundle)]
    K = max(0.0, 1.0 - sum(r.penalty for r in RULES if r.name in fired))

    dcs, capped = 0.45*F + 0.35*C + 0.20*K, None
    if any(r.status == "missing" or r.freshness == 0
           for r, s in pair(bundle, specs) if scope in s.required_in):
        dcs, capped = min(dcs, 0.40), "required_device_missing"
    if K < 0.5:
        dcs, capped = min(dcs, 0.55), "K<0.5"

    tier = "AUTO" if dcs >= 0.85 else "PROPOSE" if dcs >= 0.50 else "INVESTIGATE"
    ...
```

`blocked_capabilities` sinh từ bảng tier tối thiểu của tool — B và D thống nhất một dict duy nhất đặt trong `contracts.py`:

```python
TOOL_MIN_TIER = {
  "create_irrigation_schedule": "AUTO",
  "propose_irrigation_plan":    "PROPOSE",
  "create_inspection_ticket":   "INVESTIGATE",
  "notify":                     "INVESTIGATE",
  "generate_report":            "INVESTIGATE",
}
```

### 6.3 `reasons.py`

```python
def reason_vi(scope, tier, dcs, degraded, fired) -> str:
    parts = []
    for d in degraded:
        parts.append(f"{d.device} cũ {int(d.age_s//60)} phút" if d.age_s else f"{d.device} mất dữ liệu")
    parts += [RULE_TEXT[name] for name in fired]
    return f"{zone_label(scope)} · {tier} · {dcs:.2f} — {', '.join(parts) or 'dữ liệu đầy đủ'}"
```

### 6.4 `test_trust.py` — viết trước code

```python
def test_healthy():   assert load("bundle_healthy").tier == "AUTO"
def test_stale():     assert load("bundle_stale").tier == "PROPOSE"
def test_broken():    assert load("bundle_broken").tier == "INVESTIGATE"
def test_scope_isolation():
    # PUMP_01 chết: session_check tụt, irrigation_plan giữ nguyên
    assert trust(b, "A:session_check").tier == "INVESTIGATE"
    assert trust(b, "A:irrigation_plan").tier in ("AUTO", "PROPOSE")
```

Test cuối là bằng chứng cho "chế độ partial" — quan trọng nhất khi pitch.

---

## 7. Component: `agents/` (C)

### 7.1 `field_iot.py` — không LLM

```python
def field_iot(env: TaskEnvelope) -> ReadingBundle:
    return get_bundle(env.scope)
```

Mỏng có chủ đích. Nó tồn tại như một agent để giữ ranh giới: không ai khác được gọi `get_bundle` trực tiếp.

### 7.2 `context.py` — lọc theo tier

Đây là kỹ thuật cốt lõi của C.

```python
def build_context(bundle: ReadingBundle, verdict: TrustVerdict) -> str:
    lines = []
    for r in bundle.readings:
        if r.status == "missing":
            lines.append(f"{r.device}.{r.metric}: KHÔNG CÓ DỮ LIỆU")
        elif r.freshness < 0.3 or verdict.tier == "INVESTIGATE":
            lines.append(f"{r.device}.{r.metric}: KHÔNG KHẢ DỤNG (cũ {int(r.age_s//60)} phút)")
        else:
            tag = "" if r.freshness > 0.8 else f"  [cũ {int(r.age_s//60)} phút]"
            lines.append(f"[{r.id}] {r.device}.{r.metric} = {r.value}{r.unit}{tag}")
    return "\n".join(lines)
```

Hai hệ quả: giá trị stale **bị xóa khỏi context** chứ không bị dặn đừng dùng; và chỉ reading khả dụng mới được cấp `[id]`, nên LLM chỉ trích dẫn được thứ được phép.

### 7.3 `planning.py` — có LLM

```python
SYSTEM = """Bạn là chuyên gia tưới tiêu. Trả về DUY NHẤT một JSON object theo schema.
Mỗi mục trong items PHẢI có trường evidence chứa các mã reading dạng [r_xxxxxx]
xuất hiện trong DỮ LIỆU. Tuyệt đối không bịa mã. Nếu một thiết bị được ghi là
KHÔNG KHẢ DỤNG hoặc KHÔNG CÓ DỮ LIỆU, không được suy đoán giá trị của nó — hãy
ghi vào assumptions_vi và unavailable_devices."""

def planning(bundle, verdict) -> IrrigationPlan:
    for attempt in range(2):
        raw = call_llm(SYSTEM, USER.format(
            request=..., tier=verdict.tier, reason=verdict.reason_vi,
            data=build_context(bundle, verdict)), timeout=15)
        try:
            plan = IrrigationPlan.model_validate_json(strip_fences(raw))
            assert_grounded(plan, bundle)
            return plan
        except (ValidationError, UngroundedClaim) as e:
            last_error = e
    return fallback_plan(bundle, verdict)
```

### 7.4 `fallback.py` — bảo hiểm demo

```python
def fallback_plan(bundle, verdict) -> IrrigationPlan:
    soil = reading(bundle, "SOIL_01.soil_moisture")
    tank = reading(bundle, "TANK_01.level")
    if not soil or not tank or soil.status == "missing":
        return IrrigationPlan(items=[], unavailable_devices=[...])
    if soil.value < 30 and tank.value > 20:
        return IrrigationPlan(items=[PlanItem(
            zone="A", start="05:30", duration_min=15, priority=1,
            target_moisture_pct=35.0,
            rationale_vi="Độ ẩm dưới ngưỡng 30%, nguồn nước còn đủ.",
            evidence=[soil.id, tank.id])])
    return IrrigationPlan(items=[], assumptions_vi=["Độ ẩm còn trong ngưỡng an toàn."])
```

Xấu nhưng luôn chạy. Nếu API chết đúng lúc pitch, vẫn demo được trọn vòng đời.

### 7.5 `action.py` — không LLM

```python
def action(plan, verdict, env) -> list[ActionResult]:
    if plan is None or not plan.items:
        return [create_inspection_ticket(ticket_from(verdict), verdict=verdict, env=env)]
    results = []
    for item in plan.items:
        results.append(create_irrigation_schedule(
            zone=item.zone, start=item.start, duration_min=item.duration_min,
            priority=item.priority, evidence=item.evidence, verdict=verdict, env=env))
    return results
```

Map plan → tool call, không suy luận. Đặt LLM ở đây chỉ tăng độ trễ và nguy cơ sai tham số.

### 7.6 `coordinator.py` — state machine

```python
async def run(env: TaskEnvelope) -> FarmReport:
    bundle  = field_iot(env)
    verdict = compute_trust(bundle, env.scope)
    save_snapshot(verdict)

    plan = None
    if verdict.tier != "INVESTIGATE":
        plan = await planning(bundle, verdict)
        link_evidence(plan, verdict, env.trace_id)

    results, attempts = [], 0
    while attempts < 2:
        attempts += 1
        results = action(plan, verdict, env)
        denied = [r for r in results if r.error == "TIER_DENIED"]
        if not denied:
            break
        plan = downgrade(plan, denied)          # schedule → draft → ticket

    if not results or all(not r.ok for r in results):
        results = [create_inspection_ticket(ticket_from(verdict), verdict=verdict, env=env)]

    for r in results:
        if r.ok:
            verify_readback(r); verify_assertions(r)
    return await reporting(env.trace_id)
```

Hai chi tiết cứu demo: giới hạn 2 vòng, và `create_inspection_ticket` là fallback **không bao giờ bị từ chối** (tier tối thiểu là `INVESTIGATE`). Hệ thống không có trạng thái "không làm được gì".

### 7.7 `graph/grounding.py`

```python
def assert_grounded(plan, bundle):
    valid = {r.id for r in bundle.readings if r.status != "missing"}
    for item in plan.items:
        bad = set(item.evidence) - valid
        if bad:
            raise UngroundedClaim(item, f"evidence không tồn tại: {bad}")
```

### 7.8 `graph/explain.py`

```python
def explain(decision_id: str) -> list[dict]:
    """BFS ngược theo rel ∈ {supports, derived_from} về tới node reading.
    Trả reading kèm age_s TẠI THỜI ĐIỂM ra quyết định, không phải hiện tại."""
```

Khác biệt "tại thời điểm" vs "hiện tại" rất quan trọng: người dùng cần biết hệ thống *đã thấy gì*.

---

## 8. Component: `tools/` + `verify/` + `api/` (D)

### 8.1 `tools/decorator.py`

```python
ORDER = {"INVESTIGATE": 0, "PROPOSE": 1, "AUTO": 2}

def tool(name: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, verdict: TrustVerdict, env: TaskEnvelope, **kw):
            min_tier = TOOL_MIN_TIER[name]
            if ORDER[verdict.tier] < ORDER[min_tier]:
                return ActionResult(ok=False, tool=name, error="TIER_DENIED",
                                    required=min_tier, current=verdict.tier,
                                    dcs=verdict.dcs, hint=HINTS[name])
            key = sha1(f"{env.trace_id}|{name}|{canonical(kw)}").hexdigest()
            if prev := find_action(key):
                return prev
            res = fn(*args, **kw)
            record_action(key, name, kw, res, env.trace_id)
            return res
        return wrapper
    return deco
```

### 8.2 `tools/hints.py`

```python
HINTS = {
  "create_irrigation_schedule": "Độ tin cậy chưa đủ để ghi lịch. Dùng propose_irrigation_plan.",
  "propose_irrigation_plan":    "Dữ liệu quá yếu để đề xuất tưới. Dùng create_inspection_ticket.",
}
```

Bảng này là thứ biến hành vi xuống cấp thành emergent mà vẫn kiểm soát được.

### 8.3 `verify/`

```python
def verify_readback(action) -> Verification:
    entity = fetch_entity(action.entity_type, action.entity_id)
    mism = {k: (v, entity.get(k)) for k, v in action.params.items()
            if k in entity and entity[k] != v}
    return save(Verification(action_id=action.entity_id, method="readback",
                             expected=action.params, observed=entity,
                             passed=not mism, detail=mism))

ASSERTIONS = [
  ("water_budget",  lambda: total_planned_liters() <= tank_liters_available()),
  ("no_overlap",    lambda: not overlapping_windows("PUMP_01")),
  ("within_window", lambda: all(5 <= hour(s.start) <= 19 for s in active_schedules())),
]
```

`water_budget` chính là Water Ledger: kế hoạch vượt lượng nước khả dụng thì **không ghi được**, không phải chỉ cảnh báo.

### 8.4 `api/` — bề mặt HTTP

```
POST /farm/request            {intent, scope, raw_request} → {trace_id}
GET  /farm/trace/{trace_id}   → {plan, actions, verifications, report}
GET  /trust/current           → [TrustVerdict, ...] cho mọi scope   (UI poll 5s)
GET  /explain/{decision_id}   → [{reading, value, age_s, device}, ...]
GET  /entities/{type}/{id}    → read-back
GET  /timeline/{trace_id}     → [{tool, params, result, verify}, ...]
POST /approvals/{draft_id}/approve
POST /approvals/{draft_id}/reject
POST /sim/...                 (mục 4)
```

---

## 9. Luồng phối hợp end-to-end

Kịch bản 1, tier `AUTO`. Theo dõi cột "ai gọi ai":

| # | Ai | Làm gì | Nhận | Trả |
|---|---|---|---|---|
| 1 | `api` | `POST /farm/request` → tạo `TaskEnvelope`, sinh `trace_id` | HTTP | envelope |
| 2 | `coordinator` | gọi `field_iot(env)` | envelope | — |
| 3 | `field_iot` | `store.get_bundle(scope)` | envelope | `ReadingBundle` |
| 4 | `coordinator` | gọi `compute_trust(bundle, scope)` | bundle | — |
| 5 | `trust` | chạy F/C/K, lưu snapshot | bundle | `TrustVerdict` |
| 6 | `coordinator` | tier ≠ INVESTIGATE → gọi `planning` | verdict | — |
| 7 | `planning` | `build_context` → LLM → validate → `assert_grounded` | bundle+verdict | `IrrigationPlan` |
| 8 | `graph` | ghi cạnh `reading → decision (supports)` | plan | — |
| 9 | `coordinator` | gọi `action(plan, verdict, env)` | plan | — |
| 10 | `action` | với mỗi item gọi `create_irrigation_schedule` | plan item | `ActionResult` |
| 11 | `tools` | decorator kiểm tier → pass → ghi `schedules` + `actions` | params | result |
| 12 | `graph` | ghi `decision → action (produced)` | result | — |
| 13 | `verify` | read-back + assertion | result | `Verification` ×2 |
| 14 | `graph` | ghi `action → verify (verified_by)` | verification | — |
| 15 | `reporting` | đọc trace → LLM → 2 persona | trace_id | `FarmReport` |
| 16 | `ui` | poll `/trust/current`, fetch `/farm/trace/{id}` | — | render |

**Nhánh `PROPOSE`** — bước 11 trả `TIER_DENIED`, coordinator gọi `downgrade()` biến plan thành draft, vòng 2 gọi `propose_irrigation_plan` (pass), UI hiện khu phê duyệt.

**Nhánh `INVESTIGATE`** — bước 6 bị bỏ qua hoàn toàn (không gọi LLM planning), coordinator đi thẳng tới `create_inspection_ticket`, reporting ghi rõ giới hạn dữ liệu.

**Ai phụ thuộc ai** (dùng để biết ai bị chặn khi người khác chậm):

```
A  ──> B, C, D   (contracts + fixtures + bundle)
B  ──> D          (blocked_capabilities, tier)
C  ──> D          (gọi tool)
D  ──> E          (API)
```

A là đường găng. Fixtures ở phút 25 giải phóng B, C, D, E khỏi phụ thuộc runtime vào A.

---

## 10. Fixtures — hợp đồng thử nghiệm

`bundle_healthy.json` — mọi reading `age_s < ttl`, SOIL 28.4%, TANK 76%, PUMP 0, không rule nào cháy → F≈1, C=1, K=1 → DCS≈0.92 → `AUTO`.

`bundle_stale.json` — SOIL_01 `age_s=840` (ttl 300 → freshness≈0.4), còn lại tươi → F≈0.78, C=1, K=1 → DCS≈0.90... **cần chỉnh**: thêm WEATHER_01 `age_s=1500` (freshness 0) → F≈0.62 → DCS≈0.71 → `PROPOSE`.

`bundle_broken.json` — SOIL_01 và PH_01 `status=missing`, PUMP_01 flow 45 nhưng `window_stats.SOIL_01.delta=0.1` → rule `pump_on_soil_flat` cháy → K=0.65, và SOIL_01 là required → cap 0.40 → `INVESTIGATE`.

**A phải verify ba file này ra đúng ba tier trước khi giao cho B.** Nếu fixture sai, test của B sai theo và cả nhóm mất một tiếng.

---

## 11. Thứ tự build và điểm đồng bộ

| Mốc | Điều kiện đạt |
|---|---|
| T+0:25 | `contracts.py` freeze, 3 fixture verify xong, stub 5 module push lên `main` |
| T+1:15 | Mỗi người demo 60s cái mình có; sửa lệch contract ngay |
| T+2:30 | **Vertical slice**: bấm tắt SOIL_01 → chip trên điện thoại đổi màu. Chưa cần agent, chưa cần tool |
| T+3:30 | Checkpoint nhẹ; A chuyển sang floater cứu người tắc |
| T+4:15 | **Full loop** cả 3 kịch bản, có verification |
| T+4:45 | Feature freeze |
| T+5:30 | Chạy 3 kịch bản 5 lần liên tiếp không lỗi; seed data dự phòng sẵn sàng |

---

## 12. Danh sách cắt (theo thứ tự)

1. `verify/posthoc.py` — không bắt đầu.
2. Reporting 2 persona → gộp 1 bản.
3. Bỏ SUN_01 + PH_01 khỏi DCS (còn 4/6 thiết bị, vẫn đủ tiêu chí).
4. Rules từ 5 xuống 2: giữ `pump_on_soil_flat` và `tank_drain_no_pump`.
5. Coordinator LLM → state machine cứng (thực ra spec này đã là state machine, nên bước này miễn phí).

**Không bao giờ cắt:** trust engine, tier enforcement ở decorator, `explain()` + panel "Vì sao?", read-back verification. Bốn thứ này là bài dự thi.

---

## 13. `CLAUDE.md` — dán vào root ngay phút 20

```markdown
# Farm Multi-Agent — Hackathon 6h
Stack: FastAPI + SQLite (WAL) + paho-mqtt / Vite + React + Tailwind
Contracts: contracts.py — FROZEN. Cần đổi thì DỪNG LẠI và hỏi.
Fixtures: fixtures/*.json — dùng cho mọi test.

## Ranh giới sở hữu
Chỉ sửa file trong thư mục được giao (xem mục 1 BUILD_SPEC.md).

## Quy tắc
- Mọi PlanItem phải có evidence[] trỏ tới reading_id có thật.
- Tier enforcement ở decorator trong tools/, KHÔNG ở prompt.
- trust/ là code thuần, không import bất cứ thứ gì gọi LLM.
- Reading status="missing" vẫn phải nằm trong bundle.
- Không viết migration, không Dockerfile prod, không test E2E.
- Ưu tiên chạy được hơn đẹp.
```
