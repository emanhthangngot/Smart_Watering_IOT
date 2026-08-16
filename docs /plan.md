# AquaBroker — Kế hoạch thi SEAL Hackathon Summer 2026 (Track B: Smart Agriculture)

> **Bản v2 — 16/08/2026 08:18.** Viết lại từ 3 báo cáo trong `plans/reports/`.
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
| A2 | ≥ 3 Agent, ≥ 1 tác vụ cần ≥ 2 Agent phối hợp | Agent Constellation hiện 5 agent trong 1 request |
| A3 | ≥ 1 quyết định dùng dữ liệu MQTT | Decision Card kèm evidence chips bấm được |
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

### Hook 3 — Sensor Trust Score (0–100 mỗi device)

Bắt cả sensor *chết* lẫn sensor *nói dối*.

| Tín hiệu | Cách đo | Trừ |
|---|---|---|
| Stale | `age = now − event_time` vượt ngưỡng | theo bậc dưới |
| **Stuck-at** | `std(window) == 0` qua ≥ 3 window liên tiếp | −40 |
| **Out-of-range** | ngoài miền vật lý (pH ∉ [0,14], moisture ∉ [0,100]) | −60 |
| **Spike vô lý** | `\|z\| > 5` mà không sensor nào khác đổi | −25 |
| **Bất đồng chéo** | `SOIL_01.temperature` vs `WEATHER_01.temperature` lệch > 8°C | −30 |

Bậc staleness: `FRESH` (age < 30s) · `STALE` (30s–300s, cấm auto-approve) · `DEAD` (≥ 300s, loại khỏi suy luận + ticket).

Quyết định **có trọng số theo trust**. Trust < 50 → tự sinh ticket kiểm tra sensor, đánh dấu evidence chip cảnh báo.

> *"Soil moisture đứng đúng 45.0% suốt 6 giờ là sensor kẹt, không phải đất ổn định."*

---

## 4. Kiến trúc

```
BTC MQTT stream
      │
      ▼
[chaos hook] ──── W1 Fault Injection Panel (override ở tầng normalize)
      │
  normalize (device_id, event_time, metrics)
      │
  WatermarkManager      max(event_time) − 5s        ← repo mẫu
  WindowManager         tumbling 60s + sliding 300s/60s   ← repo mẫu
  feature: current mean min max std delta slope z_score
      │
      ▼
            [Coordinator Agent]
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  [Field IoT Agent]      [Diagnosis Agent]
  đọc 6 device,          IsolationForest per-device
  window, feature,       + water-balance + time-to-wilt
  Sensor Trust           + feature-deviation → RCA
        └───────────┬───────────┘
                    ▼
          [Resource/Broker Agent]
          phân bổ nước hữu hạn theo ưu tiên
                    ▼
        [Safety Layer — deterministic, KHÔNG LLM]
                PASS / REJECT
                    ▼
          [Autonomy Gate]  AUTO / ASSIST / ESCALATE
                    ▼
          [Human Approval — UI mobile]
                    ▼
            [Action Agent]  Tool/API → SQLite + Telegram
                    ▼
            [Verification]  đọc lại API + đối chiếu MQTT → VERIFIED
```

### Vai trò agent

| Agent | Vai trò | Lý do tồn tại độc lập |
|---|---|---|
| **Coordinator** | nhận yêu cầu, chia tác vụ, tổng hợp, xin approve | điểm hội tụ duy nhất, giữ toàn bộ trace |
| **Field IoT** | đọc 6 device, normalize, window, feature, trust | duy nhất chạm dữ liệu thô; cô lập lỗi MQTT |
| **Diagnosis** | anomaly + water-balance + forecast + RCA | nơi ML chạy; tách khỏi planning để test riêng |
| **Resource/Broker** | phân bổ nước theo ràng buộc | tối ưu có ràng buộc, khác bản chất chẩn đoán |
| **Action** | gọi Tool/API, verification read-back | ranh giới side-effect duy nhất, dễ audit |

Tác vụ "lập kế hoạch tưới trong ngày" đi qua cả 5 → thoả A2 dư sức.

### Safety Layer (rule cứng, chạy SAU LLM)

```python
REJECT nếu:
  tank_level < 15%                       → ticket cấp nước
  ph ngoài [5.5, 7.5]                    → ticket xử lý nước
  lux đỉnh AND temperature > 35°C        → hoãn tưới (phí nước do bốc hơi)
  bất kỳ device liên quan STALE/DEAD     → cấm auto-approve, bắt buộc người duyệt
  tổng nước phân bổ > nước khả dụng      → cắt theo thứ tự ưu tiên
  pump power cao AND flow ≈ 0            → dừng bơm, ticket khẩn (SOP-03)
```

LLM đề xuất. Layer này phủ quyết. Không thương lượng.

### Action state machine (A5)

```
PROPOSED → SAFETY_CHECKED → AWAITING_APPROVAL → APPROVED
        → EXECUTING → VERIFIED ✅ | FAILED ❌ | REJECTED 🚫
```

Mỗi chuyển trạng thái ghi audit row: `timestamp, actor (agent/người), payload, evidence_ids`.
Verification = đọc lại API + đối chiếu MQTT sau N giây → mới set `VERIFIED`.

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
         → SQLite (tasks, plans, audit)
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

### Device map (Track B)

| Device | Metrics | Đơn vị |
|---|---|---|
| `SOIL_01` | soil_moisture, temperature | %, °C |
| `WEATHER_01` | temperature, humidity | °C, % |
| `PUMP_01` | flow_rate, power | L/min, W |
| `PH_01` | ph | pH |
| `TANK_01` | level | % |
| `SUN_01` | lux | lx |

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
  "recommended_actions": [{"type": "inspection_ticket", "target": "PUMP_01", "priority": "high"}],
  "data_limitations": []
}
```

**Bọc lời gọi model sau `async def llm(prompt, schema) -> dict`** — hết quota Gemini giữa giờ thì đổi provider 1 dòng.

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
| `OperationalDecisionEngine` (if/elif) | **Safety Layer** — cùng vị trí, khác bản chất |

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

SVG 5 node. Request chạy → node sáng theo thứ tự, dot chạy trên đường nối, mỗi node hiện latency + số evidence. Node chờ approve nhấp nháy vàng. Click node → xem prompt/response JSON.

Đề chấm *"cách phối hợp Agent"*. Đa số đội **nói** có multi-agent; đội này **cho thấy** nó.
**Fail-safe:** degrade thành list tĩnh có timestamp — vẫn đủ A2.

### W4 — Autonomy Level · 25′ · ★★★★

| Mức | Điều kiện | Hành vi |
|---|---|---|
| 🟢 **AUTO** | confidence > 0.8 · mọi trust > 80 · rủi ro thấp · SOP rõ | tự thực thi, báo sau |
| 🟡 **ASSIST** | confidence 0.5–0.8 **hoặc** có trust < 80 | đề xuất, chờ duyệt |
| 🔴 **ESCALATE** | confidence < 0.5 **hoặc** trust < 50 **hoặc** safety REJECT | dừng, nêu rõ **cần người xác minh cái gì** |

Badge luôn kèm 1 dòng lý do. Trả lời trước câu *"AI sai thì sao?"*. Gần như miễn phí vì trust + confidence đã có.

### W5 — Water Saved counter · 20′ · ★★★

*"Hôm nay tiết kiệm 340 L (18%)"* so baseline lịch tưới cố định mô phỏng. Ăn *ứng dụng thực tế 20%*.

### Bỏ hẳn
**What-if slider** — dễ lộ điểm yếu mô hình khi BGK kéo tới biên. Phản tác dụng.
**Time Machine scrubber** — chỉ làm nếu W1–W5 xong trước 11:30.

---

## 8. Phân công 5 người

| Người | Vai | Sở hữu | Không đụng |
|---|---|---|---|
| **M1** | IoT / Streaming | fork repo, sửa B1–B4, MQTT, normalize, remap schema, **mở chaos hook**, `/api/devices`, quyết định Kafka | AI, UI |
| **M2** | AI / Data | feature (std/slope/z), IsolationForest per-device, **Hook 1** water-balance, **Hook 3** Sensor Trust, feature-deviation, **W2 twin fit** | UI, action |
| **M3** | Backend / Decision | **chốt schema 08:25**, orchestrator async, `llm()` wrapper, safety layer, SOP dict, action state machine, **W4**, WebSocket | AI model, UI |
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
| 08:35–08:50 | `docker compose up` → **quyết định Kafka (D3)** | — | phổ biến contract cho cả team | — | — |
| 08:50–09:45 | remap weather→agriculture, `devices.json`, MQTT topic, **mở chaos hook** | feature std/slope/z + IsolationForest | orchestrator async + `llm()` wrapper | **layout responsive** + WebSocket | chaos panel khung |
| 09:45–10:30 | `/api/devices`, event-time, **B3 late_percentage** | **Hook 1** water-balance | safety layer + SOP dict | Decision Card + evidence chips | **W1** hoàn thiện |
| 10:30–11:30 | ổn định stream, hỗ trợ | **Hook 3 Sensor Trust** + feature-deviation | action state machine + **W4** | **W2 chart** | **W3 constellation** |
| 11:30–12:00 | — | **W2 twin fit** | verification read-back | trust panel + polish | **W5** + Telegram |
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
| 2:45–3:15 | Badge **🟡 ASSIST**. Operator Approve trên **điện thoại** | W4 | domain/UX 20% |
| 3:15–3:45 | State machine → **VERIFIED ✅**. **Telegram tới điện thoại thật**, giơ lên | A4, A5 | hoàn thiện |
| 3:45–4:30 | **Đòn kết:** bấm **📌 ghim SOIL_01 = 45.0%**. Dữ liệu **vẫn tươi**. Trust 92→35. Hệ thống tự nói *"nghi sensor kẹt (SOP-07), quyết định này không dùng SOIL_01"* + badge **🔴 ESCALATE** + ticket | W1 + Hook 3 + W4 | A7, demo 20% |
| 4:30–5:00 | Water Saved **340 L (18%)**. Chốt: *"Không so với ngưỡng. So với chính kỳ vọng của nó — và biết khi nào phải hỏi người."* | W5 | idea 20% |
| **Q&A** | *"Mời thầy chọn giúp em một lỗi bất kỳ."* Đưa chaos panel | W1 | phản biện 20% |

Nhịp 3:45 mạnh nhất: chứng minh trung thực **ngay cả khi dữ liệu trông hoàn toàn bình thường**.

---

## 11. Chuẩn bị Q&A

| Câu hỏi | Đáp | Mở gì |
|---|---|---|
| *"AI khác gì if/else?"* | *"Threshold so với hằng số. Twin của em so với kỳ vọng vật lý học online từ chính nông trại này. Và water-balance cần 3 sensor cùng lúc mới suy ra được nguyên nhân."* | W2 |
| *"Feature nào ảnh hưởng mạnh nhất?"* | chỉ đúng feature + đóng góp % | feature-deviation panel |
| *"LLM nói sai thì sao?"* | *"LLM chỉ đề xuất. Rule cứng phủ quyết. Bằng chứng yếu thì hệ thống tự hạ xuống ESCALATE."* | W4 + safety layer |
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
