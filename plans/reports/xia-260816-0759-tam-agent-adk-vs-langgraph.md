# Xỉa `TAM-agent/backend-agent` + quyết định LangGraph vs Google ADK

**Thời điểm:** 16/08/2026 08:05. Còn ~4h build trước freeze 12:00.
**Mode:** `--compare` (không port nguyên, chỉ lấy plumbing).

---

## 1. Source manifest

| | |
|---|---|
| Repo | `TAM-agent/backend-agent` (public, 5★) |
| Mô tả | *"Multi-agent intelligent irrigation system using Google Gemini ADK"* |
| Ngôn ngữ | Python · FastAPI · **google-adk >= 1.0.0** |
| Push cuối | 2026-04-18 |
| Topics | agentic-ai, agriculture, fastapi, gemini-ai, iot, irrigation, telegram-bot, vertex-ai |
| Quy mô | ~55 file, phần agent ~90KB code |

Trùng đề tới mức đáng ngờ: multi-agent + tưới tiêu + explainable + Telegram + WebSocket. **Nhưng nó thiếu đúng những thứ ăn điểm.**

## 2. Giải phẫu

```
main.py                     FastAPI + background monitoring loop (30–60s) + WebSocket
api/routers/                plants, gardens, agriculture, audio
api/websocket.py            realtime push (11KB)
irrigation_agent/
  agent.py                  root Agent → irrigation_orchestrator → 4 sub_agents  (14.6KB, ~80% là prompt)
  sub_agents/               sensor_monitor · nutrient_analyzer · alert_manager · optimization_agent
  tools/                    _base · sensors · control · analysis · gardens · notifications
  service/                  firebase(19.8KB) · weather(18KB) · telegram · tts · stt · image
prompts/                    agent_decision · garden_advisor · garden_chat · websocket_chat
```

Pattern ADK thực tế trong `agent.py`:

```python
irrigation_orchestrator = Agent(
    name="irrigation_orchestrator",
    model=config.worker_model,              # gemini-2.5-flash
    sub_agents=[sensor_monitor_agent, nutrient_analyzer_agent,
                alert_manager_agent, optimization_agent],
    tools=[FunctionTool(get_system_status), FunctionTool(send_notification)],
    instruction="""...~250 dòng prompt...""",
    output_key="irrigation_management",
)
root_agent = intelligent_irrigation_agent
```

Khai báo multi-agent tốn **6 dòng**. Đó là điểm mạnh thật của ADK.

## 3. Phát hiện quan trọng nhất

**Repo này sẽ TRƯỢT tiêu chí AI của cuộc thi nếu nộp nguyên trạng.**

Quy chế 4.1: *"Sản phẩm chỉ trực quan hóa dữ liệu hoặc cảnh báo bằng điều kiện cố định sẽ không được xem là đáp ứng đầy đủ yêu cầu về AI."*

Repo có gì: threshold cứng (`< 30%` critical, `< 45%` low) + LLM viết văn giải thích.
Repo **không** có: MQTT, event-time, watermark, windowing, feature engineering, anomaly model, cross-sensor physics, sensor trust, verification loop.

Toàn bộ "trí tuệ" nằm trong prompt tiếng Anh dài 250 dòng nhồi cho Gemini. Đúng cái brief mục 11 cảnh báo: *đừng đẩy raw vào LLM*.

→ **Lấy đường ống, không lấy bộ não.**

## 4. Dependency matrix

| Thành phần nguồn | Local | Quyết |
|---|---|---|
| Telegram service + priority gate | NEW | **LẤY** — thay GAP-4 |
| `tools/` chia theo domain + `_base.py` | NEW | **LẤY** — khớp 5 agent |
| `prompts/` tách khỏi logic | NEW | **LẤY** — chống merge conflict 5 người |
| FastAPI + WebSocket + background loop | NEW | **LẤY pattern** |
| `USE_SIMULATION` flag | NEW | **LẤY** — hợp chaos panel W1 |
| Template Assessment/Evidence/Explanation/Recommendation | NEW | **LẤY** — làm schema RCA JSON |
| ADK `Agent(sub_agents=[...])` | CONFLICT | mục 6 |
| Firestore (19.8KB) | CONFLICT | **BỎ** — dùng SQLite |
| Vertex AI + Cloud Run | CONFLICT | **BỎ** — không deploy |
| USDA Quick Stats · ElevenLabs TTS/STT · audio router | — | **BỎ** — scope creep |
| Prompt 250 dòng/agent | CONFLICT | **BỎ** — latency + token, trái brief mục 11 |

## 5. Ba thứ đáng lấy ngay (tổng ~35 phút)

**5.1 — Telegram có thanh bar trực quan.** README cho thấy format:

```
⚠️ DECISIÓN DEL AGENTE
💧 Humedad Actual: 25%
🟥🟥🟥⬜⬜⬜⬜⬜⬜⬜ 25%
```

Thanh emoji đọc được từ xa trên điện thoại giơ lên sân khấu. Tốt hơn text thuần. Port sang tiếng Việt + thêm risk score, sop_id, ticket ID. **15′.**

**5.2 — Priority gate chống spam.** `notifications.py` chỉ bắn Telegram khi `priority in ["high","critical"]`, email khi `critical`. Đây là **quyết định thiết kế đáng nói với BGK**, không phải code. Cộng thêm `alert_cooldown_minutes` trong `config.py` — chống alert fatigue. **10′.**

**5.3 — Tách `prompts/` thành module riêng.** Với 5 người sửa song song, prompt nằm trong file logic = merge conflict liên tục. Repo này tách sẵn `prompts/agent_decision.py`. **Áp dụng ngay từ 08:15.** **10′.**

---

# 6. LangGraph vs Google ADK vs orchestrator tự viết

## 6.1 Năm câu challenge

| # | Câu hỏi | ADK | LangGraph | Tự viết |
|---|---|---|---|---|
| 1 | **Setup mất bao lâu tới "hello agent"?** | Vertex AI cần `gcloud auth application-default login` + GCP project + bật API. AI Studio key thì nhanh hơn nhưng `google-cloud-aiplatform[adk,agent-engines]` kéo về rất nặng | `pip install langgraph` + 1 API key | 0 |
| 2 | **Thứ tự agent có cố định giữa các lần chạy không?** | `sub_agents=[...]` là **LLM tự quyết chuyển giao** → có thể khác nhau mỗi lần. `SequentialAgent`/`ParallelAgent` thì cố định | Graph tường minh → cố định | Cố định tuyệt đối |
| 3 | **Chèn safety layer deterministic giữa 2 bước dễ không?** | Phải bọc thành tool hoặc node workflow riêng | Một node thường | Một hàm |
| 4 | **Phát event từng bước cho W3 Agent Constellation?** | Qua callback/event stream ADK — phải học | `astream_events` sẵn có, hoặc emit thủ công trong node | `await ws.send(...)` 1 dòng |
| 5 | **Human approval giữa chừng?** | Tự dựng | `interrupt()` + checkpointer — sinh ra cho việc này | Tự dựng (dễ, vì đã có state machine GAP-3) |

## 6.2 Ma trận quyết định

| Tiêu chí | Google ADK | LangGraph | Async tự viết |
|---|---|---|---|
| Thời gian tới first-run | ⚠️ 40–70′ (auth GCP là bom hẹn giờ) | 🟡 25–40′ | 🟢 5′ |
| Ổn định demo | ⚠️ LLM-transfer không tất định | 🟢 tất định | 🟢 tất định |
| Emit event cho Constellation | 🟡 phải học event API | 🟢 `astream_events` | 🟢 tự do |
| Human approval gate | 🟡 tự dựng | 🟢 `interrupt()` | 🟢 đã có state machine |
| Safety layer chen giữa | 🟡 | 🟢 | 🟢 |
| Freebie: UI trace sẵn | 🟢 `adk web` | ❌ | ❌ |
| Rủi ro version-hell trong 4h | 🔴 cao (deps GCP nặng) | 🟡 vừa | 🟢 không |
| Nghe "xịn" với BGK | 🟢 | 🟢 | 🟡 |

## 6.3 Khuyến nghị

**Chọn theo năng lực thật của team, không theo tên framework:**

> **Nếu ≥1 người đã ship LangGraph thật → LangGraph.**
> **Nếu không ai từng dùng cả hai → orchestrator async tự viết.**
> **ADK: chỉ chọn khi team đã có sẵn GCP project chạy được và ≥1 người đã dùng ADK.**

### Vì sao **không** khuyến nghị ADK trong tình huống này

1. **Auth là bom hẹn giờ.** `GOOGLE_GENAI_USE_VERTEXAI=True` cần ADC + GCP project + bật Vertex API. Ở hội trường, mạng lạ, quota lạ. Mất 1 giờ ở đây là mất 25% ngân sách.
2. **`sub_agents=[...]` để LLM tự chọn chuyển giao.** Demo 5 phút chạy 3 lần ra 3 thứ tự khác nhau = ác mộng. Có thể ép bằng `SequentialAgent`, nhưng khi đã ép tất định thì lợi thế "agent tự phối hợp" của ADK biến mất — còn lại chỉ là boilerplate.
3. **Deps nặng.** `google-cloud-aiplatform[adk,agent-engines]` + `google-adk[eval]` + `agent-starter-pack`. Cài lâu, dễ đụng version.
4. Điểm cộng duy nhất — `adk web` cho trace UI sẵn — **đội mình đã tự làm đẹp hơn** bằng W3 Agent Constellation.

### Vì sao LangGraph nếu có người biết

- `interrupt()` + checkpointer là **đúng nguyên thủy** cho "Human Approval" mà đề bắt buộc. Tự dựng cũng được, nhưng đây là sẵn.
- `astream_events` bơm thẳng vào WebSocket → W3 Constellation gần như miễn phí.
- Graph tường minh = safety node chen giữa Broker và Action một cách tự nhiên.
- Nói với BGK "LangGraph StateGraph" nghe chắc tay, và quy chế liệt kê đích danh LangGraph.

### Vì sao tự viết vẫn hoàn toàn hợp lệ

Quy chế 4.1 ghi *"LangGraph **hoặc công cụ tương đương**"*. Đề Track B chấm **"mỗi Agent có vai trò thực sự cần thiết"**, không chấm tên thư viện. Cấu trúc tối thiểu đủ chứng minh:

```python
@dataclass
class AgentStep:
    agent: str; started_at: float; ended_at: float
    inputs: list[str]        # evidence_ids đã dùng
    output: dict
    
async def run_plan(request) -> Decision:
    trace = []
    obs   = await field_iot.run(request, trace)      # đọc MQTT, trust, window
    diag  = await diagnosis.run(obs, trace)          # anomaly + water-balance + RCA
    alloc = await broker.run(diag, trace)            # phân bổ nước
    safe  = safety_check(alloc, obs)                 # DETERMINISTIC, không LLM
    if not safe.ok: return Decision(ESCALATE, trace, safe.reason)
    return Decision(await coordinator.summarize(...), trace)
```

Mỗi `trace.append()` bắn 1 WebSocket event → node trong W3 sáng lên. **Toàn quyền, không phụ thuộc version ai.**

## 6.4 Quy tắc quyết định cuối — chốt trước 08:20

```
Có người đã ship LangGraph thật (không phải đọc tutorial)?
├── CÓ  → LangGraph. Timebox 40 phút. Không chạy được graph rỗng lúc 09:00 → bỏ, sang tự viết.
└── KHÔNG
     └── Team đã có GCP project chạy Vertex AI sẵn VÀ đã dùng ADK?
          ├── CÓ  → ADK, nhưng BẮT BUỘC SequentialAgent, cấm sub_agents= LLM-transfer
          └── KHÔNG → orchestrator async tự viết. Chốt luôn, không bàn thêm.
```

**Timebox là phần quan trọng nhất.** Bất kể chọn gì, nếu 09:00 chưa có một luồng 2 agent chạy end-to-end → chuyển sang tự viết ngay, không tiếc.

**Không phụ thuộc vào một nhà cung cấp LLM.** Bọc lời gọi model sau một hàm `async def llm(prompt, schema) -> dict`. Đổi Gemini ↔ OpenAI trong 1 dòng khi hết quota giữa giờ thi.

---

## 7. Điều repo này KHÔNG giải quyết được cho mình

| Cần | Repo có? |
|---|---|
| MQTT ingestion | ❌ (dùng Firestore + API) |
| Event-time, watermark, windowing | ❌ |
| Feature engineering trước AI | ❌ |
| Anomaly model (IsolationForest) | ❌ |
| Water-balance cross-sensor | ❌ |
| Sensor Trust / phát hiện sensor kẹt | ❌ |
| Verification read-back sau action | ❌ |
| Safety layer deterministic tách khỏi LLM | ❌ (an toàn nằm trong prompt) |

**Toàn bộ 8 dòng này là phần ăn điểm — và phải tự viết.** Repo chỉ tiết kiệm được ~35 phút ở tầng plumbing.

## 8. Rủi ro

| Rủi ro | Chặn |
|---|---|
| Bị hút vào cài ADK/GCP rồi mất 1h | Timebox 09:00 cứng |
| Copy prompt 250 dòng của repo | Cấm. Brief mục 11: LLM nhận feature đã xử lý, không nhận raw + không nhận tiểu thuyết |
| Copy nguyên code → nghi đạo nhái (quy chế 4.2) | Chỉ lấy pattern (chia module, priority gate, format bar). Tự viết. Ghi nguồn trong README |
| Hết quota Gemini giữa giờ | Bọc `llm()` sau 1 hàm, đổi provider 1 dòng |

## 9. Câu hỏi cần chốt — trước 08:20

1. **Có ai trong 5 người đã ship LangGraph thật chưa?** (đọc tutorial không tính) → quyết định toàn bộ mục 6.
2. Team đã có GCP project bật Vertex AI sẵn chưa?
3. Repo weather demo có Kafka/event-time/windowing — **có thật không?** (hỏi từ báo cáo trước, chưa trả lời, ảnh hưởng ~1.5h)
4. Track B đã bốc trúng chưa?
5. Ai nhận M5 Demo & Wow?

---

**Kết luận một dòng:** lấy Telegram-bar + priority gate + tách `prompts/` từ repo này (~35′), bỏ toàn bộ phần còn lại; và **đừng dùng ADK trừ khi GCP đã sẵn sàng từ trước** — chọn LangGraph nếu có người biết, không thì orchestrator async tự viết, timebox 09:00.
