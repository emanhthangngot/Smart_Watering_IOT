# Phân tích repo mẫu BTC — `Pen1112003/AI-Driven-Smart-Operations...`

**Thời điểm:** 16/08/2026 08:15. Còn ~3h45 tới freeze 12:00.
**Kết luận nhanh:** repo này **tiết kiệm ~2–2.5 giờ** ở tầng đường ống, nhưng **phần AI của nó sẽ trượt tiêu chí của chính cuộc thi**. Lấy pipeline, viết lại bộ não.

---

## 0. Trả lời câu hỏi treo 3 vòng báo cáo

**CÓ. Repo weather demo là thật.** Đây chính là thứ ChatGPT nhắc tới (*"repo demo ban đầu của bạn"* có Kafka, event-time, watermark, windowing). Mục 10 của đoạn chat ChatGPT (*"Repo cần đổi như thế nào"*) được viết về **đúng repo này**.

Kèm theo repo còn có `SLIDES_DECK.marp.md`, `WORKSHOP_PRESENTATION_SCRIPT_AND_SLIDES.md`, `WORKSHOP_AI_DRIVEN_SMART_OPERATIONS_SLIDE_DECK.docx` → xác nhận đây là **tài liệu workshop chính thức của BTC**, không phải repo cá nhân ngẫu nhiên.

---

## 1. Source manifest

| | |
|---|---|
| Repo | `Pen1112003/AI-Driven-Smart-Operations-Turning-Real-Time-IoT-Data-into-Intelligent-Actions` |
| Branch | `main` · push cuối **2026-08-13** (3 ngày trước thi) |
| Ngôn ngữ | Python 122KB · JS 13.8KB · HTML 11.7KB · CSS 14.6KB |
| Domain | **Thời tiết / trạm quan trắc** — KHÔNG phải nông nghiệp |
| Hạ tầng | Redpanda · Mosquitto · Docker Compose 6 service |

## 2. Kiến trúc thực tế

```
simulator ──MQTT──> mosquitto ──> mqtt_bridge ──> Redpanda[weather-raw]
          └─CoAP──> coap_gateway ──────────────────────┘
                                                        │
                                    stream_engine/processor.py
                                    ├── WatermarkManager   (max_event_time − 5s)
                                    ├── WindowManager      (tumbling 60s + sliding 300s/60s)
                                    ├── aggregate_window_records → metrics + anomalies
                                    └── AIWeatherForecaster → Gemini → OpenAI → Fallback
                                                        │
                        Redpanda[weather-aggregated | -forecasts | -alerts]
                                                        │
                        backend/main.py  FastAPI + WebSocket + static dashboard :8000
```

Đúng pipeline brief mục 3. Chạy được. Có Docker Compose.

---

## 3. PHÁT HIỆN QUAN TRỌNG NHẤT — repo mẫu tự nó không đạt tiêu chí AI

Quy chế 4.1: *"Sản phẩm chỉ trực quan hóa dữ liệu hoặc **cảnh báo bằng điều kiện cố định** sẽ không được xem là đáp ứng đầy đủ yêu cầu về AI."*

Toàn bộ "AI" của repo mẫu:

**`aggregators.py` — anomaly hoàn toàn là threshold:**
```python
if pressure_trend <= -2.0 or avg_pressure < 995.0: anomalies.append("RAPID_BAROMETRIC_DROP_STORM_SURGE")
if max_wind > 17.0:                                anomalies.append("GALE_FORCE_WIND_GUST")
if heat_index >= 41.0:                             anomalies.append("DANGEROUS_HEAT_INDEX")
```

**`decision_rules.py` — chuỗi if/elif dài, action text hardcode sẵn tiếng Việt:**
```python
if rainfall > 40.0 or "HEAVY_TORRENTIAL_RAIN" in anomalies:
    decisions.append({... "automated_command": "EXEC_DRAINAGE_PUMPS_MAX_POWER"})
elif rainfall > 15.0: ...
```

**`forecaster.py` — LLM chỉ viết văn** từ metrics đã tổng hợp, trả `risk_score`, `synoptic_analysis`, `forecast_horizons`.

**Không có một dòng ML nào.** `requirements.txt` chỉ có `numpy` — không sklearn, không model, không baseline học được, không anomaly score thống kê.

→ Công thức repo mẫu = **`threshold + LLM văn`**. Đây đúng thứ brief mục 18 nói *không phải*: *"Không phải: IoT + ChatGPT"*.

### Hệ quả chiến lược

Nhiều đội sẽ fork repo này, đổi tên biến weather → soil, và nộp. **Họ sẽ giống nhau và cùng yếu ở tiêu chí AI 30%.**

Đội mình lấy pipeline (tiết kiệm 2h) rồi đổ toàn bộ thời gian tiết kiệm vào đúng phần họ thiếu: IsolationForest, water-balance cross-sensor, Sensor Trust, verification. **Đây là cách tách top ra khỏi đám đông.**

---

## 4. LỖI CHẶN — phải sửa trong 20 phút đầu

### 4.1 `paho-mqtt 2.x` sẽ crash ngay khi khởi động 🔴

`requirements.txt` ghi `paho-mqtt>=2.0.0`, nhưng code dùng API v1:

```python
# src/ingestion/mqtt_bridge.py — SẼ NÉM LỖI với paho 2.x
self.mqtt_client = mqtt.Client(client_id="weather-mqtt-bridge", protocol=mqtt.MQTTv311)
def on_connect(self, client, userdata, flags, rc):   # chữ ký VERSION1
```

paho-mqtt 2.0 bắt buộc tham số đầu là `CallbackAPIVersion`. Sửa:

```python
self.mqtt_client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION1,
    client_id="weather-mqtt-bridge",
    protocol=mqtt.MQTTv311,
)
```

Chỗ khác cùng lỗi: `src/backend/main.py` → `mqtt_ctrl_client = mqtt.Client(client_id="backend-controller", ...)`.

Hoặc ghim `paho-mqtt==1.6.1` trong requirements. **Chọn cách ghim version — nhanh hơn, ít rủi ro hơn.**

### 4.2 CORS cấu hình không hợp lệ

```python
allow_origins=["*"], allow_credentials=True   # trình duyệt từ chối tổ hợp này
```
Đặt `allow_credentials=False`. 1 dòng.

### 4.3 Late event bị **vứt bỏ im lặng**

```python
else:
    logger.info(f"[LATE DATA DROPPED FROM NORMAL WINDOW] ...")   # rồi thôi
```

Track B chấm *"hệ thống có tránh kết luận quá mức khi thiếu dữ liệu hay không"*. Vứt dữ liệu trễ mà không báo là điểm trừ.
**Sửa:** đẩy vào side-output, đếm, và **hiện lên UI** (`late_percentage` đã có sẵn trong `WatermarkManager.get_stats()` — chỉ cần expose ra API). ~10′, ăn điểm trực tiếp.

### 4.4 `@app.on_event("startup")` đã deprecated
FastAPI mới cảnh báo. Không chặn, để nguyên.

### 4.5 Đặt tên sai trong `aggregators.py`
`total_rain = sum(rains) / len(rains)` — tên là "total" nhưng là **mean**. Không phải bug logic (comment ghi `# rate`) nhưng dễ gây hiểu nhầm khi 5 người cùng đọc. Đổi tên `avg_rain`.

---

## 5. Vàng — lấy nguyên, tiết kiệm ~2–2.5 giờ

| Lấy | File | Tiết kiệm | Ghi chú |
|---|---|---|---|
| **WatermarkManager** | `stream_engine/watermark.py` (60 dòng) | 40′ | `watermark = max(event_time) − 5s`, đếm late/on-time sẵn. Dùng gần như nguyên |
| **WindowManager** | `stream_engine/windowing.py` | **60′** | Tumbling + sliding, đóng window theo watermark, evict buffer. Phần khó nhất, đã xong |
| **Vòng lặp processor** | `stream_engine/processor.py` | 25′ | `process_raw_event → assign → advance → handle` |
| **MQTT bridge** | `ingestion/mqtt_bridge.py` | 20′ | enrich `event_time` + `ingestion_timestamp`, key theo device |
| **Chuỗi fallback LLM** | `ai_intelligence/forecaster.py` | 25′ | Gemini → OpenAI → heuristic tất định. **Chính là hàm `llm()` mình định viết, đã có sẵn** |
| **State + WebSocket** | `backend/main.py` | 30′ | `latest_telemetry/aggregations/forecasts/alerts` + `/api/state` |
| **Dashboard skeleton** | `backend/static/*` (40KB) | 30′ | Có sẵn HTML/CSS/JS. **Phải làm lại responsive mobile** — đề bắt buộc |

**Đặc biệt — W1 Fault Injection đã có sẵn 80%:**

```python
@app.post("/api/simulator/scenario")   # normal | typhoon | heatwave | flood | cold_front
    mqtt_ctrl_client.publish("iot/simulator/control", json.dumps({"scenario": req.scenario}))
```

Pattern control-topic đã dựng. Chỉ cần thay bộ scenario nông nghiệp: `sensor_stuck`, `sensor_dead`, `pump_clog`, `tank_low`, `value_spike`.

⚠️ **Lưu ý:** ngày thi BTC cấp stream thật, simulator có thể không dùng. Nên **áp override ở tầng normalize** (như khuyến nghị W1 báo cáo trước), giữ pattern control-topic này làm giao diện.

---

## 6. Phải đổi — remap domain weather → agriculture

Schema hiện tại hoàn toàn là thời tiết:

| Repo mẫu | Track B cần |
|---|---|
| `station_id` | `device_id` (SOIL_01, PUMP_01, TANK_01, PH_01, WEATHER_01, SUN_01) |
| `temp`, `humidity`, `pressure`, `wind_speed`, `rainfall_mm_h`, `pm25`, `uv_index` | `soil_moisture`, `flow_rate`, `power`, `ph`, `level`, `lux`, `temperature`, `humidity` |
| topic `weather-raw` / `iot/weather/#` | `iot/farm/#` (chờ BTC cấp topic thật) |
| `compute_heat_index`, `compute_dew_point` | **giữ** — dùng cho ước lượng bốc hơi (SUN_01 + WEATHER_01) |
| `anomalies` threshold khí tượng | thay bằng ML + water-balance + trust |
| `OperationalDecisionEngine` (if/elif) | thay bằng **Safety Layer** — cùng vị trí kiến trúc, khác bản chất |
| `station_map`, `stations.json` | `devices.json` theo khu |

**Đừng viết lại `aggregate_window_records` từ đầu** — giữ khung, thay danh sách metric. Thêm `std`, `slope`, `z_score`, `delta` (repo mới có mean/min/max/trend).

`compute_heat_index` (công thức Rothfusz NOAA) là quà miễn phí: dùng làm proxy áp lực bốc hơi cho Hook 2 time-to-wilt, thay cho hệ số ETo mình đã cắt. **Có căn cứ khoa học, không bịa.**

---

## 7. Quyết định Kafka/Redpanda

Brief mục 5: *"nếu BTC không yêu cầu Kafka, không nên mất hàng giờ tự dựng"*. Nhưng ở đây **đã dựng sẵn và chạy được**.

**Quy tắc timebox:**

```
08:20  docker compose up -d
08:40  Redpanda + Mosquitto healthy?
       ├── CÓ    → giữ nguyên Kafka. Miễn phí, và nói được "partition key = device_id"
       └── KHÔNG → xóa redpanda + redpanda-console khỏi compose,
                   thay KafkaProducer bằng asyncio.Queue in-process.
                   processor đọc queue thay vì consumer. ~25 phút.
```

Redpanda cấu hình `--memory 512M --smp 1` — nhẹ, khả năng chạy được cao. Nhưng **không tranh cãi quá 20 phút**.

---

## 8. Timeline sửa lại — tiết kiệm 2h, dồn vào AI

| Giờ | Việc | Ai |
|---|---|---|
| 08:15–08:25 | clone, `pip install`, **ghim `paho-mqtt==1.6.1`**, sửa CORS | M1 |
| 08:25–08:40 | `docker compose up` — quyết định Kafka theo mục 7 | M1 |
| 08:25–08:45 | **Cả team chốt schema `device_id` + metrics + topic. M3 ghi ra file, khoá lúc 09:30** | tất cả |
| 08:45–09:45 | remap weather→agriculture trong `aggregators` + `stations.json`→`devices.json` + MQTT topic | M1 |
| 08:45–10:30 | **IsolationForest per-device + GAP-1 water-balance + GAP-2 Sensor Trust + feature std/slope/z** | M2 |
| 08:45–10:30 | tầng agent (thay `forecaster` + `decision_rules`) + Safety Layer + SOP dict + GAP-3 state machine | M3 |
| 08:45–11:00 | **làm lại dashboard responsive mobile** (bắt buộc) + Decision Card + evidence chips | M4 |
| 08:45–11:30 | chaos scenarios nông nghiệp + W3 Constellation + Telegram | M5 |
| 10:30–11:30 | W2 Ghost Farm (twin + chart) | M2 + M4 |
| 11:30–12:00 | expose `late_percentage` + trust panel + W4 autonomy + W5 water saved | M3 + M5 |
| **12:00** | **FREEZE** | |
| 12:00–14:00 | test 3 kịch bản · tập demo 3 lượt · **quay video backup** | tất cả |

**2 giờ tiết kiệm được đổ hết vào M2 (AI) và M5 (wow)** — đúng hai chỗ ăn điểm nhất.

---

## 9. Ma trận quyết định

| Hạng mục | Repo mẫu làm | Mình làm | Quyết |
|---|---|---|---|
| Ingestion MQTT | paho + bridge sang Kafka | như vậy | **giữ**, ghim paho 1.6.1 |
| Event-time / watermark | `max(et) − 5s` | như vậy | **giữ nguyên** |
| Windowing | tumbling 60s + sliding 300/60 | như vậy | **giữ nguyên** |
| Feature | mean/min/max/trend | **thêm std, slope, z_score, delta** | mở rộng |
| Anomaly | threshold cứng | **IsolationForest per-device + water-balance** | **thay** |
| Chất lượng dữ liệu | không có | **Sensor Trust Score** | **thêm** |
| Giải thích | LLM viết văn | feature-deviation + LLM có SOP | **thay** |
| Quyết định | if/elif hardcode | Broker + **Safety Layer tất định** | **thay** |
| Verification | **không có** | read-back API + đối chiếu MQTT | **thêm** |
| Multi-agent | **không có** | 5 agent + trace | **thêm** |
| Late data | vứt im lặng | side-output + hiện `late_percentage` | **sửa** |
| Dashboard | desktop | **responsive mobile** (bắt buộc) | **làm lại** |
| Kafka | Redpanda | theo timebox mục 7 | có điều kiện |

**Điểm rủi ro:** repo mẫu có 0/3 thứ đề Track B bắt buộc — không multi-agent, không verification, không Tool/API tạo task. Fork nguyên = trượt điều kiện chấp nhận.

---

## 10. Cảnh báo đạo nhái

Quy chế 4.2 cấm đạo nhái, nhưng đây là **repo mẫu BTC phát cho thí sinh** kèm tài liệu workshop → dùng là hợp lệ.

**Vẫn nên:** ghi rõ trong README *"Pipeline ingestion/windowing kế thừa từ repo mẫu workshop BTC; tầng AI, multi-agent, verification và UI do đội tự phát triển"*. Chủ động khai báo trước khi BGK hỏi = điểm cộng về minh bạch, không phải điểm trừ.

Và **nói thẳng trong pitch**: *"Repo mẫu dừng ở threshold + LLM. Đội em thay toàn bộ tầng quyết định bằng ML + cross-sensor physics + safety tất định."* Đây là câu chuyện mạnh, không phải điểm yếu.

---

## 11. Câu hỏi còn lại

1. ~~Repo weather demo có thật không?~~ → **CÓ, đã xác nhận.**
2. BTC ngày thi cấp **MQTT topic gì**, broker host/port nào? Ảnh hưởng trực tiếp `MQTT_TOPIC_WEATHER` và `mqtt_bridge`.
3. Có ai đã ship LangGraph thật chưa? → quyết định mục 6 báo cáo trước. **Nếu chưa trả lời trong 10′ nữa, mặc định orchestrator async tự viết.**
4. `docker compose up` có chạy được trên máy thi không? → quyết định giữ/bỏ Kafka.
5. Ai nhận M5 Demo & Wow?

---

**Một dòng:** repo mẫu cho mình **đường ống miễn phí trị giá 2 giờ** và **một lỗi paho-mqtt sẽ crash trong 20 phút đầu**; phần AI của nó là `threshold + LLM văn` nên tự nó không đạt tiêu chí — đó chính là khoảng trống để đội mình thắng.
