# AquaBroker — Kế hoạch thi SEAL Hackathon Summer 2026 (Track B: Smart Agriculture)

> **Bản v3 — 16/08/2026.** Viết lại từ 3 báo cáo trong `plans/reports/`; tích hợp kiến trúc Trust-Tiered Autonomy từ `docs /BUILD_SPEC.md` (DCS/tier thay Sensor Trust Score + Autonomy Gate rời rạc).
> Thi 07:00–14:00. **Freeze feature 12:00.** Sơ loại 8 phút (5 trình bày + 3 hỏi).

---

## 1. Contract

**Outcome**
Hệ thống Multi-Agent AI điều hành nông trại, chạy trên live MQTT stream của BTC, đủ chu trình
`Nhận yêu cầu → Đọc IoT → Phân công Agent → Phối hợp → Tool/API → Verification → Báo cáo`,
giao diện mobile-first cho phép duyệt kế hoạch và truy vết bằng chứng.

**Constraints**
- Còn ~3h40 code tới freeze 12:00.
- Không điều khiển ngược thiết bị thật. Action = ticket / lịch / thông báo / simulated action.
- Mọi LLM output là structured JSON, đi qua safety layer deterministic trước khi thành action.
- Không bịa giá trị sensor khi dữ liệu stale hoặc trust thấp.
- Code trên GitHub/GitLab (quy chế 4.1).
- Kế thừa repo mẫu BTC — phải khai báo minh bạch trong README.

**Non-goals**
- Không auth / multi-tenant / user management.
- Không mobile native. Responsive web là đủ.
- Không train deep learning. Không feature store. Không K8s. Không TimescaleDB.
- Không tối ưu độ chính xác model — baseline chạy được + giải thích được là đủ.
- Không test tự động ngoài smoke test end-to-end.

**Acceptance criteria** (bám mục 9 đề Track B)

| # | Tiêu chí | Bằng chứng demo |
|---|---|---|
| A1 | Nhận + hiển thị ≥ 4/6 thiết bị | Dashboard 6 device kèm giá trị + tuổi dữ liệu |
| A2 | ≥ 3 Agent, ≥ 1 tác vụ cần ≥ 2 Agent phối hợp | Agent Constellation hiện 7 agent trong 1 request |
| A3 | ≥ 1 quyết định dùng dữ liệu MQTT | Decision Card kèm evidence chips bấm được → mở Evidence Graph (`/explain/{id}`) |
| A4 | Tool/API tạo lịch tưới / ticket / thông báo | Ticket #N trong SQLite, hiện trên UI + Telegram |
| A5 | Verification sau hành động | Badge "đã đọc lại từ API lúc HH:MM" + state `VERIFIED` |
| A6 | Không vỡ layout điện thoại | Mở demo ở 390px, không scroll ngang |
| A7 | Partial mode khi mất dữ liệu | Ngắt sensor → banner STALE + kế hoạch hạ cấp, không bịa số |

---

## 2. Quyết định đã chốt

Chốt dưới giả định, **không chờ trả lời thêm**. Nếu giả định sai, xử lý theo cột cuối.

| # | Quyết định | Lý do | Nếu giả định sai |
|---|---|---|---|
| D1 | **Fork repo mẫu BTC** `Pen1112003/AI-Driven-Smart-Operations...` làm nền | Có sẵn MQTT + watermark + windowing + WebSocket. Tiết kiệm ~2–2.5h | — |
| D2 | **Orchestrator async tự viết**, không LangGraph, không ADK | Chưa xác nhận ai ship LangGraph thật. Quy chế cho phép "công cụ tương đương". Tất định, dễ emit event cho W3 | Nếu có người thạo LangGraph → timebox 40′, 09:00 chưa chạy thì quay lại async |
| D3 | **Giữ Kafka/Redpanda nếu `docker compose up` xanh trước 08:40** | Đã dựng sẵn, miễn phí, nói được "partition key = device_id" | Không xanh → xóa 2 service, thay `asyncio.Queue` in-process (~25′) |
| D4 | **Ghim `paho-mqtt==1.6.1`** | Code repo mẫu dùng API v1, `requirements.txt` ghi `>=2.0.0` → crash | — |
| D5 | **Cắt SHAP**, dùng feature-deviation (z-score đóng góp) | SHAP chậm trên IsolationForest, cài tốn giờ. Deviation trả lời đúng câu BGK | — |
| D6 | **Cắt hệ số ETo tự chế**, dùng `compute_heat_index` có sẵn trong repo mẫu | Công thức Rothfusz NOAA — có căn cứ khoa học, không bịa | — |
| D7 | **Water-balance không cần dung tích tank** | Đề chỉ cho `TANK_01.level` đơn vị %. Dùng nhất quán hướng + tỉ lệ slope | — |
| D8 | **Người thứ 5 = Demo & Wow Owner**, không chia lại việc 4 người kia | Lợi thế lớn nhất so với đội khác | — |
| D9 | **SOP là dict hardcode**, không vector DB / RAG | 6h không đủ cho RAG. Dict cho grounding tương đương | — |
| D10 | **Trust = Data Confidence Score (DCS) + Tier**, thay "Sensor Trust Score 0–100" + "Autonomy Gate" rời rạc bằng một điểm số duy nhất `DCS = 0.45F+0.35C+0.20K` quyết định tier `AUTO/PROPOSE/INVESTIGATE`, ép ở **tool decorator** chứ không ở prompt | Vay từ `BUILD_SPEC.md` (kiến trúc "Trust-Tiered Autonomy"). Một con số duy nhất dễ giải thích trước BGK hơn hai cơ chế song song, và ép quyền ở code loại hẳn rủi ro LLM "quên" luật | Nếu 08:35 vẫn rối, giữ tạm Trust Score 0–100 cũ, quy đổi tuyến tính sang tier lúc 10:00 |

---

## 3. Ý tưởng cốt lõi

Nước trong `TANK_01` là **ngân sách khan hiếm**. Hệ thống không chỉ lập lịch tưới mà **phân bổ** lượng nước hữu hạn theo rủi ro héo dự báo, rồi **tự kiểm chứng** bằng cân bằng nước — và **tự nghi ngờ chính cảm biến của mình**.

### Hook 1 — Water-Balance Mismatch (cross-sensor physics)

Không dùng dung tích tuyệt đối. Kiểm tra **nhất quán hướng + tỉ lệ**:

```
Khi pump_on AND flow_rate > 0, kỳ vọng đồng thời:
   slope(tank_level)    < 0                       tank phải giảm
   slope(soil_moisture) > 0                       đất phải tăng
   ratio = |slope(tank)| / slope(soil)            ổn định quanh baseline học được

Vi phạm → chẩn đoán:
   slope(soil) ≈ 0  mà slope(tank) < 0   → nước rời tank không tới đất (rò rỉ ống/vòi tắc)
   slope(tank) ≈ 0  mà flow_rate > 0     → sensor flow sai hoặc nguồn nước khác
   ratio lệch > 2σ so baseline           → thất thoát một phần
   flow ≈ 0 mà power cao                 → dry-run / tắc lọc (không cần tank)
   soil tăng khi pump off                → mưa hoặc rò van
```

Baseline `ratio` fit từ warm-up 10–15 phút hoặc 2–3 phiên tưới đầu. Threshold đơn lẻ không suy ra được.

### Hook 2 — Time-to-Wilt Forecast

```
et_proxy       = compute_heat_index(temp, humidity)      # từ repo mẫu, Rothfusz NOAA
depletion_rate = -slope(soil_moisture, window=15m) hiệu chỉnh theo et_proxy và lux
time_to_wilt   = (soil_current - WILT_POINT) / depletion_rate
```

Output: *"Khu A chạm ngưỡng héo sau ~3.4h (khoảng 2.8–4.1h)"*, ghi rõ giả định **"giữ nguyên điều kiện hiện tại"**. Đây là **dự báo**, không phải cảnh báo — dùng làm điểm ưu tiên phân bổ nước.

### Hook 3 — Data Confidence Score (DCS) & Trust Tier

*(Thành phần vay từ `BUILD_SPEC.md` — kiến trúc "Trust-Tiered Autonomy". Xem D10.)*

Không dừng ở "trust % mỗi device". Gộp mọi tín hiệu chất lượng dữ liệu của **cả một tác vụ** (scope) thành một con số duy nhất, rồi ép quyền hành động trực tiếp bằng con số đó — không qua prompt.

```
DCS = 0.45·F + 0.35·C + 0.20·K

F (Freshness)    = trung bình freshness(age, ttl) có trọng số theo REGISTRY[scope]
                    freshness = 1.0 nếu age ≤ ttl; giảm tuyến tính về 0 tại age ≥ 3·ttl
C (Completeness)  = tỉ lệ trọng số các reading KHÔNG "missing" trong scope
K (Knowledge)     = 1 − Σ(penalty của rule đã cháy), sàn 0

tier = AUTO         nếu DCS ≥ 0.85
       PROPOSE       nếu DCS ≥ 0.50
       INVESTIGATE   nếu thấp hơn

cap cứng (ghi đè DCS xuống, không thương lượng):
   thiết bị BẮT BUỘC của scope missing/freshness=0   → DCS ≤ 0.40
   K < 0.5 (nhiều rule cháy cùng lúc)                 → DCS ≤ 0.55
```

`K` bắt cả sensor *chết* lẫn sensor *nói dối*, tái dùng đúng các rule vật lý của Hook 1 cộng tín hiệu bất thường mỗi device:

| Rule | Điều kiện | Phạt K |
|---|---|---|
| `pump_on_soil_flat` | PUMP chạy nhưng SOIL gần như không tăng | −0.35 |
| `tank_drain_no_pump` | TANK giảm nhưng PUMP không chạy | −0.30 |
| **Stuck-at** | `std(window) == 0` qua ≥ 3 window liên tiếp | −0.40 |
| **Out-of-range** | ngoài miền vật lý (pH ∉ [0,14], moisture ∉ [0,100]) | −0.60 |
| **Spike vô lý** | `\|z\| > 5` mà không sensor nào khác đổi | −0.25 |
| **Bất đồng chéo** | `SOIL_01.temperature` vs `WEATHER_01.temperature` lệch > 8°C | −0.30 |

Mỗi rule là hàm thuần `(bundle) -> bool`, không bao giờ ném exception — thiếu dữ liệu thì tự bỏ qua (`val()`/`delta()` trả `None` → rule = False), không phải try/except rải khắp nơi.

**Theo scope, không theo toàn trại.** `A:irrigation_plan`, `A:session_check`, `tank:water_quality` tính DCS **độc lập** — PUMP_01 chết làm `session_check` rơi xuống `INVESTIGATE` nhưng `irrigation_plan` vẫn có thể `AUTO`/`PROPOSE` nếu không cần PUMP_01. Đây chính là cơ chế A7 "partial mode": không phải một cờ toàn cục "hệ thống đang lỗi", mà lỗi cô lập đúng phạm vi ảnh hưởng.

Tier ép ở **tool decorator** (mục 4, Trust Tier Enforcement), không phải ở prompt hay if/else rải rác — LLM có gợi ý sai thế nào, tool cũng từ chối nếu tier chưa đủ.

> *"Soil moisture đứng đúng 45.0% suốt 6 giờ không phải đất ổn định — đó là `stuck-at`, K giảm, DCS rơi, tier hạ xuống `INVESTIGATE`."*

---

## 4. Kiến trúc

### Bốn luật kiến trúc (vay từ `BUILD_SPEC.md`)

Vi phạm luật nào là bug luật đó — dùng để review chéo lúc code, không chỉ lúc pitch:

1. **Dữ liệu đi một chiều.** `MQTT → normalize → bundle → trust → agents → tools → verify → api → ui`. Không module nào gọi ngược lên trên.
2. **Quyền hành động là hàm của DCS/tier**, cưỡng chế ở **tool layer bằng decorator**, không bằng prompt.
3. **Agent nào không cần suy luận thì không có LLM.** Chỉ **Planning** và **Reporting** gọi model.
4. **Mọi decision phải nối được về ít nhất một reading có thật.** Ép bằng `assert_grounded()` ở code.

```
BTC MQTT stream
      │
      ▼
[chaos hook] ──── W1 Fault Injection Panel (override ở tầng normalize)
      │
  normalize (device_id, event_time, metrics)
  → Reading{id do SERVER sinh "r_xxxxxx", status fresh/stale/missing}   ← Luật 4
      │
  WatermarkManager      max(event_time) − 5s        ← repo mẫu
  WindowManager         tumbling 60s + sliding 300s/60s   ← repo mẫu
  feature: current mean min max std delta slope z_score
      │
      ▼
            [Coordinator Agent]  state machine, KHÔNG LLM
                    │
                    ▼
          [Field IoT Agent]  KHÔNG LLM
          get_bundle(scope) → ReadingBundle (kể cả reading "missing")
                    │
                    ▼
          [Trust Engine]  code thuần, KHÔNG LLM, KHÔNG chạm DB (trừ ghi snapshot)
          DCS = 0.45F + 0.35C + 0.20K → TrustVerdict{dcs, tier, blocked_capabilities}
                    │
        tier == INVESTIGATE? ──yes──→ bỏ qua Diagnosis/Planning, đi thẳng Action
                    │ no
                    ▼
        ┌───────────┴───────────┐
        ▼                       ▼
  [Diagnosis Agent]       [Resource/Broker Agent]
  IsolationForest per-device   phân bổ nước hữu hạn
  + water-balance + time-to-wilt  theo ưu tiên (water_budget)
  + feature-deviation → RCA
        └───────────┬───────────┘
                    ▼
          [Planning Agent]  CÓ LLM
          build_context (redact stale/missing) → LLM → validate
          → assert_grounded (evidence ⊆ reading id có thật)         ← Luật 4
          → IrrigationPlan / TicketRequest
                    ▼
            [Action Agent]  KHÔNG LLM, map plan → tool call
                    ▼
      [Tool layer — decorator TOOL_MIN_TIER, deterministic, KHÔNG prompt]   ← Luật 2
      tier < min_tier(tool) → TIER_DENIED → downgrade (schedule→draft→ticket, tối đa 2 vòng)
      tier ≥ min_tier(tool) → PASS → ghi SQLite (idempotency key)
                    ▼
          [Human Approval — UI mobile]  (tier PROPOSE → draft chờ duyệt)
                    ▼
            Tool/API → SQLite + Telegram
                    ▼
            [Verification]  readback + assertion (water_budget, no_overlap, within_window) → VERIFIED
                    ▼
          [Reporting Agent]  CÓ LLM — đọc trace → FarmReport (bản quản lý + bản kỹ thuật)
```

### Vai trò agent

| Agent | LLM? | Vai trò | Lý do tồn tại độc lập |
|---|---|---|---|
| **Coordinator** | Không | nhận yêu cầu, chia tác vụ, state machine, xin approve | điểm hội tụ duy nhất, giữ toàn bộ trace |
| **Field IoT** | Không | đọc 6 device, normalize, window, feature, `get_bundle(scope)` | duy nhất chạm dữ liệu thô; cô lập lỗi MQTT |
| **Diagnosis** | Không | anomaly + water-balance + forecast + RCA + feature-deviation | nơi ML/rule vật lý chạy; tách khỏi planning để test riêng |
| **Resource/Broker** | Không | phân bổ nước hữu hạn theo ràng buộc (water_budget) | tối ưu có ràng buộc, khác bản chất chẩn đoán |
| **Planning** | **Có** | sinh `IrrigationPlan`/`TicketRequest` có `evidence[]`, `sop_id` | nơi duy nhất "sáng tạo"; luôn qua `assert_grounded` + fallback tất định |
| **Action** | Không | map plan → tool call qua decorator, verification read-back | ranh giới side-effect duy nhất, dễ audit |
| **Reporting** | **Có** | đọc trace → 2 bản tóm tắt (quản lý / kỹ thuật) | tách khỏi Planning để đổi văn phong không ảnh hưởng quyết định |

Tác vụ "lập kế hoạch tưới trong ngày" đi qua cả 7 → thoả A2 dư sức. Chỉ 2/7 gọi LLM (Luật 3) — 5 agent còn lại tất định, dễ test, dễ giải thích trước BGK.

### Trust Tier Enforcement (thay Safety Layer — ép ở tool layer, KHÔNG ở prompt)

Mỗi tool khai báo **tier tối thiểu**; decorator kiểm tra trước khi hàm thật chạy — LLM đề xuất sai cỡ nào, tool cũng từ chối nếu tier chưa đủ:

```python
TOOL_MIN_TIER = {
  "create_irrigation_schedule": "AUTO",         # ghi lịch thật — cần tin cậy cao nhất
  "propose_irrigation_plan":    "PROPOSE",       # tạo draft chờ người duyệt
  "create_inspection_ticket":   "INVESTIGATE",   # luôn được phép — lối thoát an toàn
  "notify":                     "INVESTIGATE",
  "generate_report":            "INVESTIGATE",
}

# @tool("create_irrigation_schedule") wrapper:
#   ORDER[tier] < ORDER[min_tier] → ActionResult(ok=False, error="TIER_DENIED", hint=...)
#   ngược lại → ghi SQLite với idempotency_key = sha1(trace_id|tool|params)
```

Các REJECT tất định cũ (tank<15%, pH ngoài [5.5,7.5], lux đỉnh+nhiệt>35°C, pump power cao mà flow≈0) **không biến mất** — chúng trở thành **rule cháy trong K** (bảng Hook 3), kéo DCS xuống INVESTIGATE, nên tool bị chặn đúng bằng cơ chế tier chứ không phải một lớp if/else song song. Một cơ chế phủ quyết duy nhất, không hai.

Khi tool từ chối, Coordinator **hạ cấp** thay vì bỏ cuộc: `create_irrigation_schedule` (AUTO) → `propose_irrigation_plan` (PROPOSE) → `create_inspection_ticket` (INVESTIGATE, không bao giờ bị từ chối). Tối đa 2 vòng lặp — hệ thống không có trạng thái "không làm được gì".

### Action state machine (A5)

```
PROPOSED → TIER_CHECKED → (AUTO: bỏ qua duyệt | PROPOSE: AWAITING_APPROVAL) → APPROVED
        → EXECUTING → VERIFIED ✅ | FAILED ❌ | TIER_DENIED (hạ cấp, xem trên) | REJECTED 🚫
```

Mỗi chuyển trạng thái ghi audit row: `timestamp, actor (agent/người), payload, evidence_ids`.
Verification = đọc lại API + đối chiếu MQTT sau N giây → mới set `VERIFIED`.

### Evidence Graph — lineage reading → decision → action → verify

Luật 4 ("mọi decision phải nối được về ít nhất một reading có thật") không dừng ở một field `evidence[]` rời rạc trong JSON — nó trở thành **dữ liệu truy vấn được**. Một bảng SQLite duy nhất, `edges(src, dst, rel, trace_id)`, ghi cạnh ở đúng 4 điểm nối trong pipeline (mục 4):

| Bước pipeline | Ai ghi | Cạnh | `rel` |
|---|---|---|---|
| Planning nhận evidence đã qua `assert_grounded` | Planning | `reading_id → decision_id` | `supports` |
| Diagnosis/RCA làm căn cứ cho một plan item | Diagnosis → Planning | `decision_id → decision_id` | `derived_from` |
| Action map plan item → tool call | Action | `decision_id → action_id` | `produced` |
| Verify đọc lại API/MQTT | Verify | `action_id → verification_id` | `verified_by` |

Ghi cạnh là **hệ quả**, không phải nguồn sự thật — `assert_grounded()` đã chặn ở input (mục 5): evidence không tồn tại trong bundle thì bị `UngroundedClaim` reject trước khi có cơ hội thành cạnh. Không có "cạnh treo" (dangling edge) trỏ tới reading không thật.

```python
def explain(decision_id: str) -> list[dict]:
    """BFS ngược theo rel ∈ {supports, derived_from} về tới node reading.
    Trả reading kèm age_s TẠI THỜI ĐIỂM ra quyết định (từ trust_snapshots),
    không phải tuổi hiện tại — người xem cần biết hệ thống ĐÃ THẤY GÌ lúc đó."""
```

`GET /explain/{decision_id} → [{reading, value, age_s, device}, ...]` là **API duy nhất** phục vụ mọi nơi trong UI cần trả lời "vì sao": evidence chip trên Decision Card (A3), click node trong W3 Agent Constellation, và nút chaos panel khi BGK tự bấm ở Q&A. Một hàm, nhiều điểm gọi — không code riêng "giải thích" ở từng màn hình.

**Tương tác với các thành phần khác:**
- **Field IoT** sinh node lá của đồ thị — mỗi `Reading.id` do server sinh (mục 5) là một node `reading` không thể LLM đoán được.
- **Trust Engine** không ghi cạnh (không suy luận factual mới), nhưng `TrustVerdict.snapshot_id` là mốc thời gian mà `explain()` dùng để tính lại `age_s` lịch sử.
- **Planning** là điểm ghi cạnh đầu tiên — chỉ ghi sau khi `assert_grounded` pass, nên đồ thị không bao giờ chứa evidence bịa.
- **Action** nối `decision → action`; nếu tool trả `TIER_DENIED` và Coordinator hạ cấp (schedule→draft→ticket), plan **mới** vẫn trỏ `derived_from` về plan cũ — chuỗi hạ cấp cũng truy vết được, không mất dấu.
- **Verify** đóng cạnh cuối `action → verify`; đến đây một quyết định mới có đường đi trọn vẹn reading → decision → action → verify.
- **UI (M4)** không tự dựng cây bằng chứng — chỉ gọi `/explain/{id}` và render danh sách phẳng đã BFS sẵn.

### SOP grounding

```python
SOP = {
  "SOP-01": "Độ ẩm đất < 20% giai đoạn ra hoa → kiểm tra hệ thống tưới, cấp nước trong 30 phút",
  "SOP-03": "Bơm chạy mà lưu lượng ≈ 0 quá 60s → dừng bơm ngay, tránh chạy khô",
  "SOP-05": "pH ngoài [5.5, 7.5] → ngừng tưới, xử lý nước trước",
  "SOP-07": "Sensor không đổi giá trị quá 3 window → nghi kẹt, tạo phiếu kiểm tra",
  "SOP-09": "Tank < 15% → ngừng mọi lệnh tưới, ưu tiên cấp nước",
}
```

LLM **bắt buộc** trích `sop_id` trong recommendation: *"Dừng bơm PUMP_01 — theo SOP-03"*.

---

## 5. Stack & contract

```
BTC MQTT → paho-mqtt 1.6.1 → normalize → [Kafka/Redpanda HOẶC asyncio.Queue]
         → WatermarkManager + WindowManager (kế thừa repo mẫu)
         → pandas/numpy feature → sklearn IsolationForest per-device
         → llm() wrapper: Gemini → OpenAI → fallback tất định (kế thừa repo mẫu)
         → SQLite WAL (readings, trust_snapshots, decisions, actions, verifications, edges, schedules, drafts, tickets, notifications, reports)
         → FastAPI + WebSocket
         → Frontend responsive mobile-first
```

### Schema normalize — **M3 chốt bằng tay 08:25, KHOÁ lúc 09:30**

```json
{
  "device_id": "SOIL_01",
  "event_time": "2026-08-16T09:41:12Z",
  "ingest_time": "2026-08-16T09:41:13Z",
  "metrics": { "soil_moisture": 34.2, "temperature": 29.1 },
  "trust": 92,
  "health": "FRESH"
}
```

Xử lý time-series bằng `event_time`, không dùng `ingest_time`. Watermark = `max(event_time) − 5s`. Dedupe theo `(device_id, event_time)`.

**Grounding (Luật 4):** mỗi reading khi ghi DB được cấp `id` **do server sinh** (`r_a3f9c1`, không đoán được), theo `contracts.Reading{id, device, metric, value, unit, ts, age_s, freshness, status}`. Reading `status="missing"` vẫn nằm trong bundle — không lọc bỏ, nếu không Trust Engine không phân biệt được "ngoài scope" và "thiết bị chết". Đây là cơ chế bắt hallucination: LLM không đoán được mã reading, nên `evidence[]` chỉ đúng khi trích đúng id đã thấy trong context.

### Device Registry (Track B) — TTL, đơn vị, trọng số theo scope

`registry/specs.py` — nguồn sự thật cho TTL (dùng trong `freshness()`, Hook 3) và trọng số mỗi scope (dùng trong F, C). Cần cắt gấp thì sửa đúng file này.

| Device.metric | TTL | Đơn vị | Trọng số theo scope | Bắt buộc trong scope |
|---|---|---|---|---|
| `SOIL_01.soil_moisture` | 300s | % | irrigation_plan:3 · session_check:3 | irrigation_plan, session_check |
| `SOIL_01.temperature` | 300s | °C | irrigation_plan:1 | — |
| `WEATHER_01.temperature` | 600s | °C | irrigation_plan:1 | — |
| `WEATHER_01.humidity` | 600s | % | irrigation_plan:2 | — |
| `PUMP_01.flow_rate` | 30s | L/min | irrigation_plan:2 · session_check:3 | session_check |
| `PUMP_01.power` | 30s | W | session_check:1 | — |
| `PH_01.ph` | 900s | pH | tank_water_quality:3 | tank_water_quality |
| `TANK_01.level` | 120s | % | irrigation_plan:3 · session_check:2 · tank_water_quality:2 | irrigation_plan |
| `SUN_01.lux` | 300s | lx | irrigation_plan:1 | — |

Ba scope: `A:irrigation_plan`, `A:session_check`, `tank:water_quality`. `wsum` mỗi scope = tổng trọng số các dòng có scope đó — dùng thẳng trong công thức F, C ở Hook 3.

### Lưu trữ (`store/`) — SQLite, WAL, một schema

```sql
CREATE TABLE readings (
  id TEXT PRIMARY KEY, device TEXT, metric TEXT, value REAL, unit TEXT,
  ts TIMESTAMP, received_at TIMESTAMP);
CREATE INDEX idx_readings_lookup ON readings(device, metric, received_at DESC);

CREATE TABLE trust_snapshots (id TEXT PRIMARY KEY, scope TEXT, dcs REAL, tier TEXT,
  breakdown TEXT, fired_rules TEXT, created_at TIMESTAMP);

CREATE TABLE decisions (id TEXT PRIMARY KEY, trace_id TEXT, statement TEXT, scope TEXT,
  tier_at_time TEXT, trust_snapshot_id TEXT, agent TEXT, created_at TIMESTAMP);

CREATE TABLE actions (id TEXT PRIMARY KEY, trace_id TEXT, tool TEXT, params TEXT,
  idempotency_key TEXT UNIQUE, result TEXT, created_at TIMESTAMP);

CREATE TABLE verifications (id TEXT PRIMARY KEY, action_id TEXT, method TEXT,
  expected TEXT, observed TEXT, passed INTEGER, detail TEXT);

CREATE TABLE edges (src TEXT, dst TEXT, rel TEXT, trace_id TEXT);
CREATE INDEX idx_edges_dst ON edges(dst);

CREATE TABLE schedules (id TEXT PRIMARY KEY, zone TEXT, start TEXT, duration_min INTEGER,
  priority INTEGER, status TEXT, created_at TIMESTAMP);
CREATE TABLE drafts (id TEXT PRIMARY KEY, payload TEXT, status TEXT, dcs REAL, created_at TIMESTAMP);
CREATE TABLE tickets (id TEXT PRIMARY KEY, title TEXT, devices TEXT, reason TEXT,
  assignee TEXT, priority INTEGER, status TEXT, created_at TIMESTAMP);
CREATE TABLE notifications (id TEXT PRIMARY KEY, channel TEXT, body TEXT, created_at TIMESTAMP);
CREATE TABLE reports (id TEXT PRIMARY KEY, trace_id TEXT, payload TEXT, created_at TIMESTAMP);
```

`PRAGMA journal_mode=WAL` — MQTT ingest ghi liên tục và API đọc liên tục (UI poll 5s) không khóa nhau.

**Đường ghi:** `ingest/mqtt_client.py` — mỗi message MQTT → `write_reading(device, metric, value)` → 1 row `readings`, `id` **do server sinh** (`"r_" + uuid4().hex[:6]`), dùng `received_at` của server chứ **không tin `ts` trong payload** (chống lệch múi giờ hoặc payload bị làm giả lúc chaos test). Metric không khai báo trong Device Registry → bỏ qua, không crash.

**Đường đọc:** `store/bundle.py::get_bundle(scope)` — quét Device Registry, với mỗi `(device, metric)` thuộc scope: lấy reading mới nhất trong 30 phút; không có → `Reading(status="missing", freshness=0)`; có → tính:

```python
def freshness(age_s, ttl):
    if age_s <= ttl: return 1.0
    if age_s >= 3 * ttl: return 0.0
    return 1.0 - (age_s - ttl) / (2 * ttl)
```

`window_stats(scope, minutes=10)` trả `delta/min/max/n` mỗi metric — đầu vào cho rule `pump_on_soil_flat`, `tank_drain_no_pump` (Hook 1 + Hook 3). Reading `status="missing"` **luôn nằm trong bundle**, không bị lọc — lỗi dễ mắc nhất khi code vội là lọc bỏ nó, rồi Trust Engine không còn phân biệt được "ngoài scope" và "thiết bị chết".

### LLM contract

LLM **không** nhận raw packet. Nhận: `features đã xử lý + anomaly evidence + water-balance result + trust scores + SOP`.

```json
{
  "risk_score": 87,
  "severity": "CRITICAL",
  "why": ["flow_rate giảm 45% trong 6 phút", "power giữ nguyên 750W", "water-balance mismatch 12.4%"],
  "likely_cause": "Tắc lọc bơm hoặc rò đường ống nhánh A2",
  "confidence": 0.72,
  "sop_id": "SOP-03",
  "evidence": ["r_a3f9c1", "r_88f0e2"],
  "recommended_actions": [{"type": "inspection_ticket", "target": "PUMP_01", "priority": "high"}],
  "data_limitations": []
}
```

`evidence` **bắt buộc** chứa mã reading `[r_xxxxxx]` đã xuất hiện trong context đưa cho model — validate bằng `assert_grounded(plan, bundle)`: mã nào không thuộc `{r.id cho r trong bundle nếu status != "missing"}` → `UngroundedClaim`, retry tối đa 2 lần rồi rơi về `fallback_plan()` tất định (xấu nhưng luôn chạy — cứu demo nếu API LLM chết đúng lúc pitch).

**Bọc lời gọi model sau `async def llm(prompt, schema) -> dict`** — hết quota Gemini giữa giờ thì đổi provider 1 dòng.

### Fixtures — hợp đồng thử nghiệm (viết trước khi có model)

Ba file JSON cố định làm chuẩn cho Trust Engine và demo A7, dựng ngay sau khi schema khoá (~08:35), độc lập với MQTT thật:

| File | Tình huống | Tier kỳ vọng |
|---|---|---|
| `bundle_healthy.json` | mọi reading tươi, không rule nào cháy → DCS ≈ 0.92 | `AUTO` |
| `bundle_stale.json` | `SOIL_01` cũ 14′, `WEATHER_01` cũ 25′ → F giảm, DCS ≈ 0.71 | `PROPOSE` |
| `bundle_broken.json` | `SOIL_01`+`PH_01` missing, bơm chạy mà đất không tăng (`pump_on_soil_flat` cháy) → K=0.65 và thiết bị bắt buộc missing → cap 0.40 | `INVESTIGATE` |

`test_trust.py` chạy 3 file này ra đúng 3 tier **trước khi giao Trust Engine cho người khác dùng** — fixture sai thì cả team mất cả tiếng đi theo hướng sai. Cùng bộ fixture dùng lại thẳng cho kịch bản demo A7 (mục 10).

---

## 6. Kế thừa repo mẫu BTC

### 6.1 Lỗi chặn — sửa trong 15 phút đầu

| # | Lỗi | Sửa |
|---|---|---|
| **B1** 🔴 | `requirements.txt` ghi `paho-mqtt>=2.0.0` nhưng code dùng API v1 → **crash lúc khởi động**. Dính `ingestion/mqtt_bridge.py` và `backend/main.py` | Ghim `paho-mqtt==1.6.1` |
| **B2** | CORS `allow_origins=["*"]` + `allow_credentials=True` — trình duyệt từ chối | `allow_credentials=False` |
| **B3** | Late event **bị vứt im lặng** (`LATE DATA DROPPED`) | Side-output + expose `late_percentage` (đã có sẵn trong `WatermarkManager.get_stats()`) lên UI. **10′, ăn điểm A7 trực tiếp** |
| **B4** | `total_rain = sum(rains)/len(rains)` — tên là "total" nhưng là mean | Đổi tên `avg_rain` |

### 6.2 Lấy nguyên (~2–2.5h tiết kiệm)

| Lấy | File | Tiết kiệm |
|---|---|---|
| `WindowManager` — tumbling + sliding, đóng theo watermark, evict buffer | `stream_engine/windowing.py` | **60′** (phần khó nhất) |
| `WatermarkManager` — 60 dòng, đếm late/on-time sẵn | `stream_engine/watermark.py` | 40′ |
| Vòng lặp `process_raw_event → assign → advance → handle` | `stream_engine/processor.py` | 25′ |
| MQTT bridge — enrich `event_time` + `ingest_time`, key theo device | `ingestion/mqtt_bridge.py` | 20′ |
| Chuỗi fallback Gemini → OpenAI → heuristic | `ai_intelligence/forecaster.py` | 25′ (= hàm `llm()`) |
| State dicts + `/api/state` + WebSocket | `backend/main.py` | 30′ |
| `compute_heat_index` (Rothfusz NOAA) | `stream_engine/aggregators.py` | thay ETo tự chế |
| `/api/simulator/scenario` + control topic | `backend/main.py` | **W1 đã có 80%** |

### 6.3 Remap weather → agriculture

| Repo mẫu | Đổi thành |
|---|---|
| `station_id` | `device_id` |
| `temp`/`humidity`/`pressure`/`wind_speed`/`rainfall_mm_h`/`pm25`/`uv_index` | `soil_moisture`/`flow_rate`/`power`/`ph`/`level`/`lux`/`temperature`/`humidity` |
| topic `iot/weather/#`, `weather-raw` | `iot/farm/#`, `farm-raw` (chờ BTC cấp topic thật) |
| `stations.json` | `devices.json` |
| `anomalies` threshold khí tượng | **IsolationForest + water-balance + trust** |
| `OperationalDecisionEngine` (if/elif) | **Trust Tier Enforcement** (tool decorator) — cùng vị trí, khác bản chất |

Giữ khung `aggregate_window_records`, chỉ thay danh sách metric. **Thêm `std`, `slope`, `z_score`, `delta`** (repo mới có mean/min/max/trend).

### 6.4 Bỏ hẳn
Firestore · Vertex AI · Cloud Run · USDA Quick Stats · ElevenLabs TTS/STT · audio router · prompt 250 dòng.

### 6.5 Minh bạch

README ghi rõ:
> *"Pipeline ingestion/windowing kế thừa từ repo mẫu workshop BTC. Tầng AI (IsolationForest, water-balance, Sensor Trust), multi-agent, safety layer, verification và UI do đội tự phát triển."*

Nói thẳng trong pitch: ***"Repo mẫu dừng ở threshold + LLM viết văn. Đội em thay toàn bộ tầng quyết định bằng ML + cross-sensor physics + safety tất định."***

---

## 7. WOW layer

Mỗi ý tưởng qua 3 cửa: **nhìn thấy trên máy chiếu trong 15 giây** · **không thể fake** · **≤ 60 phút, hỏng thì tắt được**.

### W1 — Fault Injection Panel: *"Mời thầy chọn giúp em một lỗi bất kỳ"* · 45′ · ★★★★★

Panel ẩn `/chaos`, override ở **tầng normalize** (không đụng stream BTC). Kế thừa pattern control-topic của repo mẫu.

| Nút | Hiệu ứng | Phản ứng kỳ vọng |
|---|---|---|
| 🔌 Ngắt SOIL_01 | dừng forward packet | STALE → partial mode |
| 📌 Ghim SOIL_01 = 45.0% | ghi đè, `event_time` vẫn tươi | Trust rơi → "nghi sensor kẹt" (SOP-07) |
| 📈 Spike WEATHER_01 = 85°C | ghi đè 1 packet | Out-of-range → loại + ticket |
| 🚱 Tank về 8% | ghi đè level | Safety REJECT mọi lệnh tưới (SOP-09) |
| 🔧 Bơm tắc: flow 40→5, power giữ | ghi đè 2 field | Water-balance mismatch → CRITICAL |

Mọi đội demo kịch bản dựng sẵn. Đưa điều khiển cho BGK = *"hệ thống chịu được thứ em không dự đoán trước"*.
**Fail-safe:** chỉ mời BGK bấm ở Q&A, sau khi 5 phút chính đã an toàn. Có nút Reset.

### W2 — Ghost Farm: dự đoán vs thực tế · 60′ · ★★★★★

Twin vật lý 2 tham số, fit online least-squares từ 10–15 phút đầu:

```
soil_pred(t+1) = soil(t) + k_in · flow_rate(t) − k_out · et_proxy(temp, humidity, lux)
```

**Visual:** một chart, hai đường — xanh nét liền (thực tế), tím nét đứt (twin). Khi tách → **tô vùng đỏ** + nhãn `DIVERGENCE 12.4%`.

Hook 1 **thành hình ảnh**. Câu chốt: ***"Hệ thống không so với ngưỡng. Nó so với chính kỳ vọng của nó."***
**Fail-safe:** fit không hội tụ → hardcode `k_in`, `k_out` từ 10 phút quan sát.

### W3 — Agent Constellation · 50′ · ★★★★

SVG 7 node (Coordinator, Field IoT, Diagnosis, Resource/Broker, Planning, Action, Reporting). Request chạy → node sáng theo thứ tự, dot chạy trên đường nối, mỗi node hiện latency + số evidence. Node chờ approve nhấp nháy vàng. Click node → xem prompt/response JSON; click số evidence trên node → mở Evidence Graph (`/explain/{id}`), thấy đúng chuỗi reading → decision → action → verify của node đó.

Đề chấm *"cách phối hợp Agent"*. Đa số đội **nói** có multi-agent; đội này **cho thấy** nó.
**Fail-safe:** degrade thành list tĩnh có timestamp — vẫn đủ A2.

### W4 — Trust Tier Badge · 25′ · ★★★★

| Mức | Điều kiện (DCS) | Hành vi | Tool tối thiểu |
|---|---|---|---|
| 🟢 **AUTO** | DCS ≥ 0.85 | tự thực thi `create_irrigation_schedule`, báo sau | AUTO |
| 🟡 **PROPOSE** | DCS ≥ 0.50 | tạo draft, chờ người duyệt trên UI | PROPOSE |
| 🔴 **INVESTIGATE** | DCS < 0.50, hoặc thiết bị bắt buộc missing, hoặc K < 0.5 | dừng planning, sinh `inspection_ticket`, nêu rõ **cần người xác minh cái gì** | INVESTIGATE |

Badge luôn kèm `reason_vi` (mục 3, `reasons.py`) — 1 dòng, không chỉ màu. Trả lời trước câu *"AI sai thì sao?"*: không phải "chúng em tin AI", mà "tier ép ở tool layer, AI đề xuất sai cỡ nào cũng không ghi được lịch tưới thật nếu DCS chưa đủ". Gần như miễn phí vì Trust Engine (Hook 3) đã tính sẵn DCS + tier.

### W5 — Water Saved counter · 20′ · ★★★

*"Hôm nay tiết kiệm 340 L (18%)"* so baseline lịch tưới cố định mô phỏng. Ăn *ứng dụng thực tế 20%*.

### Bỏ hẳn
**What-if slider** — dễ lộ điểm yếu mô hình khi BGK kéo tới biên. Phản tác dụng.
**Time Machine scrubber** — chỉ làm nếu W1–W5 xong trước 11:30.

---

## 8. Phân công 5 người

| Người | Vai | Sở hữu | Không đụng |
|---|---|---|---|
| **M1** | IoT / Streaming | fork repo, sửa B1–B4, MQTT, normalize, remap schema, **store schema.sql (WAL) + Device Registry**, **mở chaos hook**, `/api/devices`, quyết định Kafka | AI, UI |
| **M2** | AI / Data | feature (std/slope/z), IsolationForest per-device, **Hook 1** water-balance, **Hook 3** Trust Engine (DCS/tier), feature-deviation, **W2 twin fit** | UI, action |
| **M3** | Backend / Decision | **chốt schema + contracts.py 08:25**, orchestrator async, `llm()` wrapper, **tool decorator (TOOL_MIN_TIER)**, **Evidence Graph** (`edges`/`explain`/`assert_grounded`), SOP dict, action state machine + downgrade, **W4**, WebSocket | AI model, UI |
| **M4** | Frontend | **làm lại responsive mobile**, Decision Card, evidence chips, approve bar, trust panel, **W2 chart**, data-health banner | backend logic |
| **M5** | **Demo & Wow** | **W1 chaos**, **W3 constellation**, **W5 counter**, Telegram, slide, kịch bản, **quay video backup** | core pipeline |

**Chống dẫm chân:**
- M5 chỉ đọc API/WebSocket đã có, **không sửa file của M1–M3**. Chaos panel cắm qua **đúng một hook** M1 mở lúc 09:00 rồi thôi.
- Mỗi người sở hữu thư mục riêng. PR nhỏ. Không ai sửa file người khác.
- Prompt tách thành module `prompts/` riêng — 5 người sửa song song không conflict.

**Tận dụng ChatGPT Plus:** mỗi người 1 tab sinh boilerplate (SVG animation, chart config, pydantic schema). Nhưng **contract do M3 chốt bằng tay** — rủi ro lớn nhất của team đông + AI nhanh là **5 tab sinh ra 5 schema khác nhau**.

---

## 9. Timeline

| Giờ | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|
| 08:20–08:35 | fork repo, `pip install`, **ghim paho 1.6.1**, sửa CORS | đọc `aggregators.py` | **chốt schema + API contract, ghi ra file** | đọc `static/` | dựng slide khung |
| 08:35–08:50 | `docker compose up` → **quyết định Kafka (D3)**, dựng `store/schema.sql` (WAL) | — | phổ biến contract cho cả team | — | — |
| 08:50–09:45 | remap weather→agriculture, `devices.json`, MQTT topic, **mở chaos hook** | feature std/slope/z + IsolationForest | orchestrator async + `llm()` wrapper | **layout responsive** + WebSocket | chaos panel khung |
| 09:45–10:30 | `/api/devices`, event-time, **B3 late_percentage** | **Hook 1** water-balance | **tool decorator** (TOOL_MIN_TIER) + SOP dict | Decision Card + evidence chips | **W1** hoàn thiện |
| 10:30–11:30 | ổn định stream, hỗ trợ | **Hook 3** Trust Engine (DCS/tier) + feature-deviation | action state machine (downgrade) + Evidence Graph edges + **W4** | **W2 chart** | **W3 constellation** |
| 11:30–12:00 | — | **W2 twin fit** | verification read-back + `explain()` API | trust panel + polish | **W5** + Telegram |
| **12:00** | **FREEZE FEATURE — không ai commit tính năng mới** ||||
| 12:00–12:45 | Cả team: end-to-end 3 kịch bản Track B + bấm thử **toàn bộ** nút chaos ||||
| 12:45–13:30 | Tập demo 3 lượt bấm giờ. M5 dẫn, cả team bắt lỗi ||||
| 13:30–14:00 | **Quay video backup toàn bộ demo.** Dự phòng ||||

**Cắt scope theo thứ tự ngược khi chậm:** W5 → Telegram → W3 → W2 → Hook 2.
**Giữ bằng mọi giá:** Hook 1, Hook 3, A5 verification, A6 responsive.
Nếu 11:30 xong hết → M5 làm Time Machine scrubber.

---

## 10. Kịch bản demo — 5 phút + 3 phút Q&A

| Phút | Nội dung | Hiển thị | Tiêu chí |
|---|---|---|---|
| 0:00–0:30 | *"Nông trại 6 cảm biến. Nước là tài nguyên hữu hạn."* NORMAL, 6 device xanh | dashboard + trust bar | A1, realtime 30% |
| 0:30–1:00 | Chỉ **Ghost Farm** — hai đường trùng khít | W2 | AI |
| 1:00–2:00 | Bấm chaos **🔧 bơm tắc**. Hai đường **tách ra**, vùng đỏ nở | W2 + W1 | AI 30% |
| 2:00–2:45 | **Agent Constellation** sáng lần lượt. Diagnosis: mismatch 12.4%, RCA + feature-deviation + **theo SOP-03** | W3 | A2, AI |
| 2:45–3:15 | Badge **🟡 PROPOSE** (DCS ~0.6–0.8). Operator Approve trên **điện thoại** | W4 | domain/UX 20% |
| 3:15–3:45 | State machine → **VERIFIED ✅**. **Telegram tới điện thoại thật**, giơ lên | A4, A5 | hoàn thiện |
| 3:45–4:30 | **Đòn kết:** bấm **📌 ghim SOIL_01 = 45.0%**. Dữ liệu **vẫn tươi**. `stuck-at` cháy, K rơi, DCS 0.92→0.38. Hệ thống tự nói *"nghi sensor kẹt (SOP-07), quyết định này không dùng SOIL_01"* + badge **🔴 INVESTIGATE** + ticket | W1 + Hook 3 + W4 | A7, demo 20% |
| 4:30–5:00 | Water Saved **340 L (18%)**. Chốt: *"Không so với ngưỡng. So với chính kỳ vọng của nó — và biết khi nào phải hỏi người."* | W5 | idea 20% |
| **Q&A** | *"Mời thầy chọn giúp em một lỗi bất kỳ."* Đưa chaos panel | W1 | phản biện 20% |

Nhịp 3:45 mạnh nhất: chứng minh trung thực **ngay cả khi dữ liệu trông hoàn toàn bình thường**.

---

## 11. Chuẩn bị Q&A

| Câu hỏi | Đáp | Mở gì |
|---|---|---|
| *"AI khác gì if/else?"* | *"Threshold so với hằng số. Twin của em so với kỳ vọng vật lý học online từ chính nông trại này. Và water-balance cần 3 sensor cùng lúc mới suy ra được nguyên nhân."* | W2 |
| *"Feature nào ảnh hưởng mạnh nhất?"* | chỉ đúng feature + đóng góp % | feature-deviation panel |
| *"LLM nói sai thì sao?"* | *"LLM chỉ đề xuất trong Planning/Reporting — hai agent duy nhất gọi model. Tier ép ở tool decorator, không ở prompt: DCS chưa đủ thì `create_irrigation_schedule` từ chối thẳng, không cần LLM 'nhớ' luật. Bằng chứng yếu thì hệ thống tự hạ xuống INVESTIGATE."* | W4 + Trust Tier Enforcement |
| *"Sao biết AI không bịa bằng chứng?"* | *"Mỗi reading có `id` do server sinh, LLM không đoán được. `evidence[]` phải trỏ đúng id đã thấy trong context — sai thì `assert_grounded()` reject, retry rồi rơi về plan tất định."* | `contracts.py` + `assert_grounded` |
| *"Truy vết một quyết định thế nào?"* | *"Mỗi bước ghi một cạnh vào Evidence Graph: reading → decision → action → verify. `/explain/{id}` BFS ngược, trả đúng tuổi dữ liệu tại thời điểm ra quyết định — không phải tuổi bây giờ."* | Evidence Graph, click node W3 |
| *"Sao dùng repo mẫu?"* | *"Kế thừa ingestion/windowing, ghi rõ trong README. Repo mẫu dừng ở threshold + LLM văn; em thay toàn bộ tầng quyết định."* | README |
| *"Dữ liệu trễ thì sao?"* | *"Watermark 5s, late event vào side-output, tỉ lệ hiện trên UI. Không vứt im lặng."* | `late_percentage` |

---

## 12. Rủi ro

| Rủi ro | Chặn |
|---|---|
| **5 tab ChatGPT sinh 5 schema khác nhau** | M3 chốt contract bằng tay 08:25, ghi ra file, **khoá 09:30** |
| paho-mqtt crash lúc khởi động | D4 ghim 1.6.1 — sửa ngay 08:20 |
| `docker compose` không lên | D3 timebox 08:40 → `asyncio.Queue`, 25′ |
| Bị hút vào cài LangGraph/ADK mất 1h | D2 async tự viết. Nếu thử LangGraph → timebox 09:00 cứng |
| MQTT BTC đổi schema | adapter layer tách rời; có replay JSONL demo offline |
| Hết quota LLM giữa giờ | `llm()` wrapper, đổi provider 1 dòng; cache response; fallback tất định |
| Không đủ dữ liệu fit IsolationForest | warm-up 5–10′; trước đó dùng rule physics (Hook 1 không cần train) |
| Thiếu device trong stream thật | chỉ cần 4/6. Ưu tiên `SOIL_01`, `PUMP_01`, `TANK_01`, `WEATHER_01` — đủ cả 3 hook |
| Quên ghi cạnh Evidence Graph ở một bước → chuỗi `explain()` đứt giữa chừng | ghi cạnh **ngay trong** hàm của từng agent (Planning/Action/Verify tự gọi `log_edge()`), không phải một job nền riêng dễ quên gọi; thiếu 1 cạnh vẫn demo được các cạnh còn lại |
| M5 sửa core làm vỡ pipeline | chaos panel là middleware độc lập, đúng 1 hook |
| Code AI sinh không ai đọc được | ai commit người đó phải giải thích được; freeze 12:00 nghiêm |
| Demo crash trên sân khấu | **quay video backup 13:30–14:00** |

---

## 13. Câu hỏi chưa chốt

1. **BTC cấp MQTT topic / broker host:port nào?** Ảnh hưởng `MQTT_TOPIC`, `mqtt_bridge`. Biết lúc nào cập nhật lúc đó — adapter layer đã tách sẵn nên không chặn.
2. Track B đã bốc trúng chưa, hay vẫn phòng hờ? Nếu track khác, Hook 1 port sang energy-balance / mass-balance.
3. Ai nhận M5? **Nên là người nói tốt nhất** — sẽ dẫn pitch.
4. `docker compose up` có lên trên máy thi không? → quyết D3 lúc 08:40.
5. Có tạo được Telegram bot token tại chỗ không (cần mạng ngoài)?

---

## Nguồn

- `plans/reports/xia-260816-0738-plan-improvements.md` — GAP-1..4, WOW layer, phân công 5 người
- `plans/reports/xia-260816-0759-tam-agent-adk-vs-langgraph.md` — quyết định orchestration
- `plans/reports/xia-260816-0808-btc-sample-repo-analysis.md` — phân tích repo mẫu BTC, lỗi chặn
- `docs /BUILD_SPEC.md` — kiến trúc Trust-Tiered Autonomy (DCS/tier, tool decorator, contracts.py, grounding) tích hợp vào mục 2 (D10), 3 (Hook 3), 4 (kiến trúc), 5 (contract + fixtures), 7 (W4)
