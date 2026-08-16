# AquaBroker — Kế hoạch thi SEAL Hackathon Summer 2026 (Track B: Smart Agriculture)

> Ngày thi: 16/08/2026, 07:00–14:00 (7 giờ code). Thuyết trình sơ loại 8 phút (5 trình bày + 3 hỏi).

---

## 1. Contract

**Outcome**
Hệ thống Multi-Agent AI điều hành nông trại, chạy trên live MQTT stream của BTC, thực hiện đủ chu trình:
`Nhận yêu cầu → Đọc IoT → Phân công Agent → Phối hợp → Tool/API → Verification → Báo cáo`,
với giao diện mobile-first cho phép người quản lý duyệt kế hoạch và truy vết bằng chứng dữ liệu.

**Constraints**
- 7 giờ code, freeze feature lúc 12:00.
- Không điều khiển ngược thiết bị thật. Action = ticket / lịch / thông báo / simulated action.
- Không dựng Kafka, K8s, TimescaleDB. In-memory + SQLite.
- Mọi LLM output phải là structured JSON, đi qua safety layer deterministic trước khi thành action.
- Không bịa giá trị sensor khi dữ liệu stale.
- Code phải nằm trên GitHub/GitLab (quy chế 4.1).

**Non-goals**
- Không làm auth / multi-tenant / user management.
- Không làm mobile app native — responsive web là đủ.
- Không train deep learning. Không dựng feature store.
- Không tối ưu độ chính xác model. Baseline chạy được + giải thích được là đủ.
- Không viết test tự động ngoài smoke test end-to-end.

**Acceptance criteria** (bám đúng mục 9 đề Track B)
| # | Tiêu chí | Bằng chứng demo |
|---|---|---|
| A1 | Nhận + hiển thị ≥ 4/6 thiết bị | Dashboard hiện 6 device kèm giá trị và tuổi dữ liệu |
| A2 | ≥ 3 Agent, ≥ 1 tác vụ cần ≥ 2 Agent phối hợp | Agent trace timeline hiện 5 agent trong 1 request |
| A3 | ≥ 1 quyết định dùng dữ liệu MQTT | Decision Card kèm evidence chips bấm được |
| A4 | Tool/API tạo lịch tưới / ticket / thông báo | Ticket #N tồn tại trong SQLite, hiện trên UI |
| A5 | Verification sau hành động | Badge "đã đọc lại từ API lúc HH:MM" |
| A6 | Không vỡ layout trên điện thoại | Mở demo ở 390px width, không scroll ngang |
| A7 | Partial mode khi mất dữ liệu | Rút 1 sensor → banner STALE + kế hoạch hạ cấp, không bịa số |

---

## 2. Ý tưởng cốt lõi

Nước trong `TANK_01` là **ngân sách khan hiếm**. Hệ thống không chỉ lập lịch tưới, mà **phân bổ lượng nước hữu hạn** cho các khu theo rủi ro héo dự báo, rồi **tự kiểm chứng** bằng cân bằng nước.

Ba hook kỹ thuật tạo khác biệt:

### Hook 1 — Water-Balance Mismatch (cross-sensor physics check)

Trong mỗi phiên tưới, so ba đại lượng:
- Nước bơm ra: `flow_rate × duration` (PUMP_01)
- Nước rời tank: `Δlevel × tank_capacity` (TANK_01)
- Nước đất nhận: `Δsoil_moisture` quy đổi (SOIL_01)

| Triệu chứng | Nguyên nhân suy ra | Action |
|---|---|---|
| tank giảm đúng, soil không tăng | rò rỉ ống / vòi tắc | ticket kiểm tra đường ống |
| flow giảm, power giữ cao | bơm nghẹt lọc | ticket vệ sinh lọc, giảm tải |
| flow ≈ 0, power cao | dry-run, hút cạn | dừng bơm ngay, ticket khẩn |
| soil tăng khi pump off | mưa hoặc rò van | hoãn lịch tưới, xác minh van |

Threshold đơn lẻ không suy ra được. Đây là phần "AI hiểu nguyên nhân".

### Hook 2 — Time-to-Wilt Forecast

Slope suy giảm `soil_moisture` trên sliding window 15 phút, hiệu chỉnh bốc hơi từ `WEATHER_01` (temperature, humidity) và `SUN_01` (lux):

```
et_factor = f(temp, humidity, lux)          # xấp xỉ ETo đơn giản
depletion_rate = -slope(soil_moisture) * et_factor
time_to_wilt  = (soil_current - WILT_POINT) / depletion_rate
```

Output: *"Khu A chạm ngưỡng héo sau ~3.4h (khoảng 2.8–4.1h)"* → dùng làm điểm ưu tiên phân bổ nước.

Đây là **dự báo**, không phải cảnh báo. Ăn thẳng tiêu chí "AI tạo giá trị gì hơn threshold".

### Hook 3 — Data-Health Gate (chế độ partial)

Mỗi device có `age = now - event_time`:

| Trạng thái | Ngưỡng | Hành vi hệ thống |
|---|---|---|
| FRESH | age < 30s | dùng bình thường |
| STALE | 30s ≤ age < 300s | dùng có ghi chú, cấm auto-approve |
| DEAD | age ≥ 300s | loại khỏi suy luận, tạo ticket kiểm tra sensor |

Khi có DEAD, Coordinator **tách phần xử lý được và phần cần xác minh**, Reporting ghi rõ giới hạn dữ liệu. Đây là Kịch bản 3 của đề — chỗ đa số đội sẽ hallucinate.

---

## 3. Kiến trúc Agent

```
                    [Coordinator Agent]
                     nhận yêu cầu, route, tổng hợp
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
      [Field IoT Agent]           [Diagnosis Agent]
      MQTT, normalize,            IsolationForest,
      window, feature,            water-balance,
      data-health                 time-to-wilt, RCA
              └─────────────┬─────────────┘
                            ▼
                  [Resource/Broker Agent]
                  phân bổ nước hữu hạn theo
                  ưu tiên + ràng buộc pH/tank
                            ▼
                  [Safety Layer — deterministic]
                        PASS / REJECT
                            ▼
                  [Human Approval — UI]
                            ▼
                    [Action Agent]
                  Tool/API tạo task
                            ▼
                    [Verification]
                  đọc lại API + MQTT
```

| Agent | Vai trò | Lý do tồn tại độc lập |
|---|---|---|
| **Coordinator** | nhận yêu cầu, chia tác vụ, tổng hợp, xin approve | điểm hội tụ duy nhất, giữ toàn bộ trace |
| **Field IoT** | đọc 6 device, normalize, windowing, feature, data-health | duy nhất chạm dữ liệu thô; cô lập lỗi MQTT |
| **Diagnosis** | anomaly score + water-balance + forecast + RCA | nơi ML thật chạy; tách khỏi planning để test riêng |
| **Resource/Broker** | phân bổ nước theo ràng buộc | bài toán tối ưu có ràng buộc, khác bản chất với chẩn đoán |
| **Action** | gọi Tool/API, verification read-back | ranh giới side-effect duy nhất; dễ audit |

Tác vụ "lập kế hoạch tưới trong ngày" đi qua cả 5 agent → thoả A2 dư sức.

### Safety Layer (rule cứng, chạy SAU LLM)

```python
REJECT nếu:
  tank_level < 15%                      → ticket cấp nước
  ph ngoài [5.5, 7.5]                   → ticket xử lý nước
  lux ở đỉnh AND temperature > 35°C     → hoãn tưới (phí nước do bốc hơi)
  bất kỳ device liên quan là STALE/DEAD → cấm auto-approve, bắt buộc người duyệt
  tổng nước phân bổ > nước khả dụng     → cắt theo thứ tự ưu tiên
  pump power cao AND flow ≈ 0           → dừng bơm, ticket khẩn
```

LLM có thể hallucinate. Layer này là deterministic, không thương lượng.

---

## 4. Stack

```
paho-mqtt  →  asyncio ingest  →  deque ring buffer (in-memory, per device)
           →  pandas rolling window (tumbling 1m + sliding 5m/slide 1m)
           →  sklearn IsolationForest + rule physics + shap
           →  LLM (Gemini / OpenAI, structured JSON output)
           →  SQLite (tasks, plans, audit trail)
           →  FastAPI + WebSocket
           →  Next.js / React + shadcn/ui, mobile-first
```

**Cố ý không dùng:** Kafka/Redpanda, Kubernetes, TimescaleDB, Redis, Neo4j, deep learning.
Lý do: brief mục 14 nói rõ. Pipeline đơn giản chạy được > hạ tầng đẹp chưa chạy.

**Orchestration:** LangGraph nếu team đã quen. Chưa quen thì dùng `async def` + typed state dict — an toàn hơn trong 7 giờ.

### Normalize schema (chốt sớm, mọi module bám vào)

```json
{
  "device_id": "SOIL_01",
  "event_time": "2026-08-16T09:41:12Z",
  "ingest_time": "2026-08-16T09:41:13Z",
  "metrics": { "soil_moisture": 34.2, "temperature": 29.1 }
}
```

Xử lý time-series bằng `event_time`, không dùng `ingest_time`. Watermark = `max(event_time) - 5s`. QoS 1 + dedupe downstream theo `(device_id, event_time)`.

### Feature set (mỗi device, mỗi window)

`current`, `mean`, `min`, `max`, `std`, `delta`, `slope`, `z_score`

Không đưa raw sensor vào AI. `temperature = 40°C` chưa chắc bất thường; `25 → 40°C trong 1 phút` mới nguy hiểm.

### LLM contract

LLM **không** nhận raw packet. LLM nhận:
`processed features + anomaly evidence + water-balance result + domain context + SOP`

LLM trả JSON:
```json
{
  "risk_score": 87,
  "severity": "CRITICAL",
  "why": ["flow_rate giảm 45% trong 6 phút", "power giữ nguyên 750W"],
  "likely_cause": "Tắc lọc bơm hoặc rò đường ống nhánh A2",
  "confidence": 0.72,
  "recommended_actions": [
    {"type": "inspection_ticket", "target": "PUMP_01", "priority": "high"}
  ],
  "data_limitations": []
}
```

---

## 5. Timeline 7 giờ

| Giờ | Việc | Owner |
|---|---|---|
| 07:00–07:30 | Trả lời WHO / PROBLEM / DATA / AI / WHY / ACTION. Chốt scope. Tạo repo + skeleton + **chốt schema normalize**. Test LLM key + rate limit. | Cả team |
| 07:30–09:00 | MQTT connect, normalize, ring buffer, `/api/devices` trả live | M1 (IoT/Streaming) |
| 07:30–09:00 | Frontend shell + WebSocket + layout mobile | M4 (Frontend) |
| 09:00–10:30 | Feature window + IsolationForest + water-balance + time-to-wilt | M2 (AI/Data) |
| 09:00–10:30 | Agent graph + LLM structured JSON + safety rules | M3 (Backend) |
| 10:30–11:30 | Tool/API tạo task + verification read-back + SQLite audit | M3 |
| 10:30–11:30 | SHAP explanation cho anomaly score | M2 |
| 10:30–12:00 | Decision Card + evidence chips + approve bar + agent trace | M4 |
| **12:00** | **FREEZE FEATURE.** Không viết tính năng mới. | Cả team |
| 12:00–12:45 | Chạy end-to-end 3 kịch bản Track B. Fix bug chặn demo. | Cả team |
| 12:45–13:30 | Dựng kịch bản demo incident + slide + tập nói 5 phút | Cả team |
| 13:30–14:00 | Dự phòng. **Quay video backup demo.** | Cả team |

Quy tắc cứng: sau 12:00, mỗi thay đổi code phải trả lời được "cái này có làm demo hỏng không?". Không chắc thì không sửa.

---

## 6. Kịch bản demo (kể 1 incident, 5 phút)

| Bước | Nội dung | Ăn tiêu chí |
|---|---|---|
| 1 | NORMAL — 6 device FRESH, kế hoạch tưới khu A lúc 09:00 đã duyệt | A1, realtime 30% |
| 2 | Phiên tưới chạy. `PUMP_01.flow_rate` tụt 40 → 22 L/min, `power` giữ 750W | realtime |
| 3 | Diagnosis Agent: anomaly score 0.87. Water balance — tank giảm 120L, soil chỉ +2%. **Mismatch 68L** | AI 30% |
| 4 | RCA: "Nghi tắc lọc hoặc rò nhánh A2. Bằng chứng: flow↓ power→ (bơm gắng sức), nước rời tank không tới đất." SHAP hiện feature đóng góp | AI 30% |
| 5 | Broker cắt phân bổ khu A, giữ nước cho khu ưu tiên. Time-to-wilt khu A còn 3.4h → vẫn an toàn | idea 20% |
| 6 | Safety layer PASS. Operator bấm Approve trên điện thoại | domain/UX 20% |
| 7 | Action Agent tạo ticket #12 + thông báo. **Verify**: đọc lại API → ✅ tồn tại | A4, A5 |
| 8 | **Đòn kết** — ngắt SOIL_01 → banner STALE → hệ thống tự chuyển partial mode, tạo ticket kiểm tra sensor, ghi rõ giới hạn dữ liệu, **không bịa số** | A7, demo 20% |

Bước 8 chứng minh hệ thống trung thực. Đây là điểm phân biệt lớn nhất với các đội khác.

### Ba câu BGK nhiều khả năng hỏi — chuẩn bị sẵn

1. *"AI của em khác gì if/else?"*
   → Trả lời bằng Hook 1 + Hook 2. Threshold không suy ra được mismatch giữa 3 sensor, và không dự báo được time-to-wilt.

2. *"Feature nào ảnh hưởng mạnh nhất đến prediction?"*
   → Mở SHAP panel, chỉ đúng feature. Đây là câu brief cảnh báo trước (mục 10).

3. *"Nếu LLM nói sai thì sao?"*
   → Chỉ vào Safety Layer deterministic. LLM đề xuất, rule cứng phủ quyết.

---

## 7. UX — yêu cầu bắt buộc

- **Decision Card**: mỗi quyết định kèm hàng **evidence chip** — `SOIL_01 34% · 12s` bấm được, mở panel giá trị + window + agent nào đọc. Đáp thẳng "thể hiện rõ dữ liệu IoT ảnh hưởng quyết định nào".
- **Agent Trace timeline**: agent nào chạy, thứ tự, thời gian, dữ liệu đã dùng.
- **Approve / Reject sticky bar** ở đáy màn hình (vùng ngón cái).
- **Verification badge**: ✅ "Đã tạo task #12, đọc lại từ API lúc 09:41".
- **Data-health banner** toàn cục + chấm màu trạng thái MQTT.
- Test ở **390px width**. Không scroll ngang. Không bảng tràn.

---

## 8. Rủi ro & phương án dự phòng

| Rủi ro | Xác suất | Dự phòng |
|---|---|---|
| MQTT của BTC không kết nối được / đổi schema | Cao | Viết adapter layer tách rời. Có sẵn replay file JSONL để demo offline |
| LLM rate limit / mất mạng | Trung bình | Cache response. Fallback: template RCA từ rule engine, vẫn chạy được demo |
| Không đủ dữ liệu lịch sử để fit IsolationForest | Cao | Warm-up 5 phút đầu; trước đó dùng rule physics (Hook 1 không cần train) |
| Thiếu device nào đó trong stream thật | Trung bình | Chỉ cần 4/6. Ưu tiên SOIL_01, PUMP_01, TANK_01, WEATHER_01 — đủ chạy cả 3 hook |
| Frontend chưa xong lúc 12:00 | Trung bình | Fallback: dashboard 1 trang duy nhất, bỏ agent trace, giữ Decision Card + Approve |
| Demo crash trên sân khấu | Trung bình | **Quay video backup lúc 13:30–14:00** |

**Nguyên tắc ưu tiên khi cháy thời gian:** giữ Hook 1 (water-balance) và A5 (verification) bằng mọi giá. Bỏ SHAP, bỏ agent trace, bỏ Hook 2 trước.

---

## 9. Tham khảo (lấy pattern, không clone)

- **LangGraph** `examples/` — supervisor / multi-agent state graph pattern
- **eclipse/paho.mqtt.python** — MQTT client asyncio
- **scikit-learn** `IsolationForest` + **shap** `TreeExplainer` — anomaly + explanation
- **FastAPI + websockets** boilerplate — realtime push
- **shadcn/ui** — card / badge / sheet mobile sẵn, tiết kiệm 1–2h frontend

Quy chế 4.2 cấm đạo nhái. Copy pattern và tự viết, không copy nguyên repo.

---

## 10. Câu hỏi chưa chốt

1. Team mấy người, ai mạnh mảng nào? Timeline mục 5 giả định 4 người theo phân công brief mục 16.
2. Track B đã bốc trúng chưa, hay đây là chuẩn bị phòng hờ? Nếu track khác, Hook 1 port được sang energy-balance / mass-balance.
3. LLM nào có API key sẵn và đã test rate limit chưa?
4. Dung tích `TANK_01` (lít) — cần để tính water-balance. Nếu BTC không cung cấp, dùng hệ số tương đối thay vì tuyệt đối.
