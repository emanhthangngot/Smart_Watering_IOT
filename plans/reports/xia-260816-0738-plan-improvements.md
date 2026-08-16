# Báo cáo cải thiện `docs /plan.md` — đối chiếu ChatGPT analysis + repo tham khảo + WOW layer

**Nguồn:** ChatGPT share `6a8105bb` ("Phân tích yêu cầu đề bài"), đọc đầy đủ qua browser 16/08/2026 07:42.
**Cập nhật 07:53:** thêm WOW layer cho **team 5 người**, ngân sách còn ~6h.
**Mode:** `--improve`.

---

## 1. Điểm hội tụ — plan hiện tại đã đúng hướng

ChatGPT phân tích độc lập, **kết luận trùng khớp** với hook số 1 của plan:

> Máy bơm đang bật nhưng lưu lượng nước gần bằng 0, độ ẩm đất vẫn tiếp tục giảm → tắc đường ống hoặc bơm mất nước → risk CRITICAL → dừng bơm tránh chạy khô + ticket kiểm tra khu A.

Đây chính là **Hook 1 — Water-Balance Mismatch**. Hai phân tích độc lập cùng chọn incident này → xác nhận mạnh. **Giữ nguyên, đây là xương sống.**

Trùng khớp thêm: feature engineering trước AI; Isolation Forest + baseline per-device khi không có label; output phải là `What → Why → Root cause → Risk → Action`.

---

## 2. Bốn thiếu sót kỹ thuật

### GAP-1 (nghiêm trọng) — Water-balance đang giả định biết dung tích tank

Plan viết `Δlevel × tank_capacity`. Đề Track B chỉ cho `TANK_01.level` đơn vị **%**. Không có dung tích lít. Công thức tuyệt đối **sập** trên schema thật.

**Fix — kiểm tra nhất quán hướng + tỉ lệ, không cần dung tích:**

```
Khi pump_on AND flow_rate > 0, kỳ vọng đồng thời:
   slope(tank_level)      < 0        (tank phải giảm)
   slope(soil_moisture)   > 0        (đất phải tăng)
   ratio = |slope(tank)| / slope(soil)   ổn định quanh baseline học được

Vi phạm:
   slope(soil) ≈ 0 mà slope(tank) < 0   → nước rời tank không tới đất (rò rỉ)
   slope(tank) ≈ 0 mà flow_rate > 0     → sensor flow sai hoặc nguồn khác
   ratio lệch > 2σ so baseline          → thất thoát một phần
   flow ≈ 0 mà power cao                → dry-run / tắc (không cần tank)
```

Baseline `ratio` học từ warm-up hoặc 2–3 phiên tưới đầu. **Ưu tiên số 1.** 20′.

### GAP-2 (cao) — Chỉ phát hiện sensor *chết*, không phát hiện sensor *nói dối*

Plan mới có Data-Health Gate theo `age`. ChatGPT chỉ ra lớp lỗi khác: dữ liệu **tươi nhưng sai**.

> Soil moisture giữ nguyên chính xác 45.0% trong 6 giờ → sensor kẹt, không phải đất ổn định.

**Sensor Trust Score (0–100/device):**

| Tín hiệu | Cách đo | Trừ |
|---|---|---|
| Stale | `age` vượt ngưỡng | theo bậc |
| **Stuck-at** | `std(window) == 0` qua ≥ N window | −40 |
| **Out-of-range** | ngoài miền vật lý (pH ∉ [0,14], moisture ∉ [0,100]) | −60 |
| **Spike vô lý** | `\|z\| > 5` mà không sensor nào khác đổi | −25 |
| **Bất đồng chéo** | SOIL_01.temperature vs WEATHER_01.temperature lệch > 8°C | −30 |

Quyết định có trọng số theo trust. Trust < 50 → tự sinh ticket kiểm tra sensor. 45′.

### GAP-3 (trung bình) — Action chưa có vòng đời

```
PROPOSED → SAFETY_CHECKED → AWAITING_APPROVAL → APPROVED
        → EXECUTING → VERIFIED ✅ | FAILED ❌ | REJECTED 🚫
```

Mỗi chuyển trạng thái ghi audit: `timestamp, actor, payload, evidence_ids`. Verification = đọc lại API + đối chiếu MQTT rồi mới set `VERIFIED`. Ăn thẳng *độ hoàn thiện 30%* vòng chung kết. 30′.

### GAP-4 (trung bình) — Thiếu external side effect

**Telegram bot** sau Approve: risk score, RCA rút gọn, ticket ID. Giơ điện thoại lên sân khấu, tin nhắn tới thật. 20′.

---

## 3. Hai thứ nên CẮT

| Cắt | Lý do | Thay bằng |
|---|---|---|
| **SHAP** | chậm trên IsolationForest, cài đặt tốn giờ, dễ vỡ | **Feature deviation** — z-score đóng góp từng feature so baseline. Trả lời đúng câu BGK hỏi. −30′ |
| **Hệ số ETo (Hook 2)** | cần loại cây/đất/giai đoạn — đề không cho, bịa sẽ bị hỏi vặn | **Ngoại suy slope thuần + khoảng tin cậy**, ghi rõ giả định. Trung thực hơn. −20′ |

---

## 4. SOP grounding — rẻ mà sang

**Không dựng vector DB.** Dict hardcode 6–8 rule, LLM bắt buộc trích `sop_id`:

```python
SOP = {
  "SOP-01": "Độ ẩm đất < 20% giai đoạn ra hoa → kiểm tra hệ thống tưới, cấp nước trong 30 phút",
  "SOP-03": "Bơm chạy mà lưu lượng ≈ 0 quá 60s → dừng bơm ngay, tránh chạy khô",
  "SOP-05": "pH ngoài [5.5, 7.5] → ngừng tưới, xử lý nước trước",
}
```

Recommendation hiện: *"Dừng bơm PUMP_01 — **theo SOP-03**"*. Chống hallucination ở tầng nội dung. 15′.

---

## 5. Repo tham khảo (đã lọc theo ràng buộc thi SE, không hardware)

| Hạng | Repo | Lấy gì | Dùng ở đâu |
|---|---|---|---|
| 1 | `calvinmclean/automated-garden` (Go, 35★) | action queue, mock controller, REST API | GAP-3 |
| 2 | `xmmmmmovo/SmartGreenhouse` (70★, archived) | phân tầng MQTT→backend→cache→DB→frontend | chia module backend |
| 3 | `Chinukapoor/Smart-Agriculture-using-IoT-and-ML` (78★) | formulation `detection → cause → prevention` | Diagnosis Agent |

**Cảnh báo bảo mật:** README của SmartGreenhouse tự ghi nhận lỗi ghép chuỗi SQL. Không copy backend nguyên trạng — dùng ORM/parameterized query, không commit secret. Quy chế 4.2 cấm đạo nhái: lấy pattern, tự viết.

Loại khỏi tầm ngắm: `farmOS` (1.3k★ nhưng quản lý hồ sơ, không real-time), `AgriSync` (scope quá lớn, có blockchain/marketplace), mọi repo ESP32/Arduino.

---

# 6. WOW LAYER — thiết kế cho 5 người / 6 giờ

## 6.1 Ràng buộc chọn wow

Team 5 người → **người thứ 5 là Demo & Wow Owner**, không chia lại việc của 4 người kia. Đây là lợi thế lớn nhất: hầu hết đội khác không có ai chuyên lo phần "làm BGK ồ lên".

Mỗi ý tưởng wow phải qua 3 cửa:

1. **Nhìn thấy được trên máy chiếu trong 15 giây** — BGK ngồi xa, 5 phút, không đọc chữ nhỏ.
2. **Không thể fake** — phải chứng minh hệ thống thật đang chạy.
3. **Chi phí ≤ 60 phút** và **fail-safe** — hỏng thì tắt đi, demo vẫn sống.

## 6.2 Ba tier ý tưởng

### TIER S — làm bằng mọi giá

---

#### W1 — Fault Injection Panel: *"Mời BGK phá hệ thống của em"* ★★★★★ · 45′

Một panel nhỏ (route `/chaos`, ẩn khỏi UI chính) cho phép **chèn lỗi vào tầng normalize** — không đụng stream của BTC:

| Nút | Hiệu ứng | Hệ thống phải phản ứng |
|---|---|---|
| 🔌 Ngắt SOIL_01 | dừng forward packet | STALE → partial mode |
| 📌 Ghim SOIL_01 = 45.0% | ghi đè giá trị, giữ event_time tươi | Trust rơi → "nghi sensor kẹt" |
| 📈 Spike WEATHER_01 = 85°C | ghi đè 1 packet | Out-of-range → loại + ticket |
| 🚱 Tank về 8% | ghi đè level | Safety REJECT mọi lệnh tưới |
| 🔧 Bơm tắc: flow 40→5, power giữ | ghi đè 2 field | Water-balance mismatch → CRITICAL |

**Vì sao đây là wow số 1:** mọi đội đều demo kịch bản dựng sẵn. Đưa điều khiển cho BGK là tuyên bố *"hệ thống em chịu được thứ em không dự đoán trước"*. BGK sẽ nhớ đội này.

**Câu nói khi demo:** *"Thầy chọn giúp em một lỗi bất kỳ."*

**Fail-safe:** chỉ mời BGK bấm ở phần Q&A (3 phút), sau khi 5 phút chính đã chạy xong an toàn. Tự bấm trước 1 nút trong phần chính để chứng minh nó hoạt động. Có nút Reset.

---

#### W2 — Ghost Farm: đường **dự đoán** vs đường **thực tế** ★★★★★ · 60′

Chạy song song một **twin vật lý tối giản** dự đoán `soil_moisture` nên diễn biến thế nào:

```
soil_pred(t+1) = soil(t) + k_in · flow_rate(t) − k_out · evap(temp, humidity, lux)
```

`k_in`, `k_out` fit online từ 10–15 phút đầu (least squares 2 tham số — không phải ML nặng).

**Visual:** một chart, hai đường.
- Xanh nét liền = thực tế
- Tím nét đứt = twin dự đoán
- Khi tách nhau → **tô vùng đỏ giữa hai đường** + nhãn `DIVERGENCE 12.4%`

**Vì sao wow:** đây là Hook 1 nhưng **thành hình ảnh**. BGK ngồi xa vẫn thấy ngay "hai đường tách ra = có chuyện". Không cần đọc số. Và nó nâng pitch từ *"em phát hiện bất thường"* lên *"em có mô hình về nông trại, sự cố là chỗ thực tế lệch khỏi mô hình"*.

**Câu chốt pitch:** *"Hệ thống không so với ngưỡng. Nó so với chính kỳ vọng của nó."*

**Fail-safe:** nếu fit không hội tụ, hardcode `k_in`, `k_out` từ quan sát 10 phút đầu. Vẫn ra hình đúng.

---

#### W3 — Agent Constellation: nhìn thấy multi-agent chạy ★★★★ · 50′

SVG 5 node agent. Khi request chạy, node **sáng lên theo thứ tự**, đường nối có dot chạy, mỗi node hiện `latency` + `số evidence đã dùng`. Node đang chờ approve nhấp nháy vàng.

**Vì sao wow:** đề Track B chấm *"cách phối hợp Agent"*. Đa số đội sẽ **nói** là có multi-agent. Đội này **cho thấy** nó, real-time, trên máy chiếu. Đây là bằng chứng trực quan cho tiêu chí A2, không phải lời khai.

Bonus rẻ: click node → xem prompt/response JSON của agent đó. BGK hỏi "agent này thật sự làm gì?" → mở ra ngay.

**Fail-safe:** nếu animation lỗi, degrade thành list tĩnh có timestamp. Vẫn đủ A2.

---

### TIER A — làm nếu đúng tiến độ

#### W4 — Autonomy Level: *AI tự biết khi nào phải hỏi người* ★★★★ · 25′

Mỗi quyết định gắn 1 trong 3 mức, hiện badge to:

| Mức | Điều kiện | Hành vi |
|---|---|---|
| 🟢 **AUTO** | confidence > 0.8 · mọi trust > 80 · rủi ro thấp · SOP rõ | tự thực thi, báo sau |
| 🟡 **ASSIST** | confidence 0.5–0.8 **hoặc** có trust < 80 | đề xuất, chờ duyệt |
| 🔴 **ESCALATE** | confidence < 0.5 **hoặc** trust < 50 **hoặc** safety REJECT | dừng, nêu rõ **cần người xác minh cái gì** |

Badge luôn kèm **một dòng lý do**: *"ESCALATE — SOIL_01 trust 35, không đủ căn cứ tưới khu A."*

**Vì sao wow:** trả lời trước câu BGK chắc chắn hỏi *"nếu AI sai thì sao?"*. Hệ thống **tự điều chỉnh mức tự chủ theo chất lượng bằng chứng**. Rất ít đội sinh viên nghĩ tới. Chi phí gần như bằng 0 vì trust + confidence đã có sẵn.

#### W5 — Water Saved counter ★★★ · 20′

Panel góc: **"Hôm nay tiết kiệm 340 L (18%)"** so với baseline lịch tưới cố định mô phỏng (tưới đủ 3 lần/ngày bất kể điều kiện).

**Vì sao wow:** BGK chấm *"ứng dụng thực tế 20%"*. Một con số tài nguyên tiết kiệm được đáng giá hơn ba slide kiến trúc. Rẻ: chỉ cần cộng dồn `flow × duration` của kế hoạch AI vs baseline.

---

### TIER B — chỉ khi dư giờ sau 11:30

#### W6 — Time Machine scrubber · 70′
Thanh trượt kéo lùi 30 phút, dashboard + quyết định + evidence tái hiện đúng lúc đó. Chứng minh audit trail thật. BGK: *"cho tôi xem lúc 9:15 hệ thống nghĩ gì."*
**Đánh giá:** wow thật nhưng tốn state snapshot. **Chỉ làm nếu W1–W5 xong trước 11:30.**

#### W7 — What-if slider · 60′
Kéo *"nếu không tưới khu A"* → time-to-wilt cập nhật live. Tương tác cao nhưng dễ lộ chỗ mô hình yếu nếu BGK kéo tới biên. **Rủi ro phản tác dụng — không khuyến nghị trong 6h.**

## 6.3 Ma trận quyết định

| Ý tưởng | Chi phí | Wow | Không-fake-được | Rủi ro nếu hỏng | Quyết |
|---|---|---|---|---|---|
| W1 Fault Injection | 45′ | ★★★★★ | ★★★★★ | thấp (có Reset) | **LÀM** |
| W2 Ghost Farm | 60′ | ★★★★★ | ★★★★ | thấp (hardcode k) | **LÀM** |
| W3 Agent Constellation | 50′ | ★★★★ | ★★★★★ | thấp (degrade list) | **LÀM** |
| W4 Autonomy Level | 25′ | ★★★★ | ★★★ | rất thấp | **LÀM** |
| W5 Water Saved | 20′ | ★★★ | ★★ | rất thấp | **LÀM** |
| W6 Time Machine | 70′ | ★★★★ | ★★★★ | trung bình | stretch |
| W7 What-if | 60′ | ★★★ | ★★ | **cao — dễ lộ điểm yếu** | **BỎ** |

Tổng TIER S+A: **200 phút**, dồn phần lớn vào M5 + M4.

---

## 7. Phân công 5 người

| Người | Vai | Sở hữu | Không đụng |
|---|---|---|---|
| **M1** | IoT / Streaming | MQTT, normalize, ring buffer, window, event-time, `/api/devices` | AI, UI |
| **M2** | AI / Data | feature, IsolationForest per-device, **GAP-1** water-balance, **GAP-2** Sensor Trust, feature-deviation, **W2 twin fit** | UI, action |
| **M3** | Backend / Decision | agent graph, LLM JSON, safety layer, **SOP dict**, **GAP-3** state machine, **W4** autonomy, WebSocket | AI model, UI |
| **M4** | Frontend | layout mobile-first, Decision Card, evidence chips, approve bar, **W2 chart render**, data-health banner | backend logic |
| **M5** | **Demo & Wow** | **W1 chaos panel**, **W3 constellation**, **W5 counter**, **GAP-4 Telegram**, slide, kịch bản, quay video backup | core pipeline |

**Nguyên tắc chống dẫm chân:** M5 chỉ đọc API/WebSocket đã có, **không sửa file của M1–M3**. Chaos panel là middleware độc lập cắm vào tầng normalize qua một hook duy nhất — M1 mở sẵn hook đó lúc 09:00 rồi thôi.

**Tận dụng ChatGPT Plus:** mỗi người chạy song song ở tab riêng để sinh boilerplate (SVG animation, chart config, pydantic schema, docker-compose). Nhưng **contract giữa các module do M3 chốt bằng tay lúc 07:30** — không để AI của 5 người tự nghĩ ra 5 schema khác nhau. Đây là rủi ro lớn nhất của team đông + AI nhanh.

---

## 8. Timeline sửa lại

| Giờ | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|
| 07:50–08:15 | **Cả team: chốt schema normalize + API contract + tên topic. M3 viết ra file, mọi người bám theo.** ||||
| 08:15–09:30 | MQTT + normalize + buffer + **mở chaos hook** | feature window | agent skeleton + LLM JSON | layout + WebSocket | dựng chaos panel khung |
| 09:30–10:30 | `/api/devices` + event-time | **GAP-1** + IsolationForest | safety + SOP dict | Decision Card + evidence chips | **W1** hoàn thiện |
| 10:30–11:30 | hỗ trợ, ổn định stream | **GAP-2 Trust** + feature-deviation | **GAP-3** state machine + **W4** | **W2 chart** | **W3 constellation** |
| 11:30–12:00 | — | **W2 twin fit** | verification read-back | trust panel + polish | **W5** + Telegram |
| **12:00** | **FREEZE FEATURE — không ai commit tính năng mới** ||||
| 12:00–12:45 | Cả team chạy end-to-end 3 kịch bản + bấm thử toàn bộ nút chaos ||||
| 12:45–13:30 | Tập demo 3 lượt bấm giờ. M5 dẫn, mọi người bắt lỗi ||||
| 13:30–14:00 | **Quay video backup toàn bộ demo.** Dự phòng ||||

Nếu 11:30 mà W1–W5 đã xong → M5 làm **W6 Time Machine**. Nếu chậm → cắt theo thứ tự ngược: W5 → W3 → Telegram.

---

## 9. Kịch bản demo v2 — 5 phút + 3 phút Q&A

| Phút | Nội dung | Hiển thị | Ăn tiêu chí |
|---|---|---|---|
| 0:00–0:30 | *"Nông trại này có 6 cảm biến. Nước là tài nguyên hữu hạn."* NORMAL, 6 device xanh | dashboard + trust bar | A1, realtime |
| 0:30–1:00 | Chỉ **Ghost Farm** — hai đường trùng khít | W2 chart | AI |
| 1:00–2:00 | Bấm chaos **🔧 bơm tắc**. Hai đường **tách ra**, vùng đỏ nở rộng | W2 + W1 | AI 30% |
| 2:00–2:45 | **Agent Constellation** sáng lần lượt. Diagnosis: mismatch 12.4%, RCA + feature deviation + **theo SOP-03** | W3 | A2, AI |
| 2:45–3:15 | Badge **🟡 ASSIST** — *"trust đủ cao nhưng rủi ro tài sản, cần người duyệt"*. Operator bấm Approve trên **điện thoại** | W4 | domain/UX 20% |
| 3:15–3:45 | Action chạy state machine → **VERIFIED ✅**. **Telegram tới điện thoại thật**, giơ lên | GAP-3 + GAP-4 | A4, A5 |
| 3:45–4:30 | **Đòn kết:** bấm **📌 ghim SOIL_01 = 45.0%**. Dữ liệu **vẫn tươi**. Trust rơi 92→35. Hệ thống tự nói *"nghi sensor kẹt, quyết định này không dùng SOIL_01"* + badge chuyển **🔴 ESCALATE** + ticket kiểm tra | W1 + GAP-2 + W4 | A7, demo 20% |
| 4:30–5:00 | Water Saved **340 L (18%)**. Chốt: *"Không so với ngưỡng. So với chính kỳ vọng của nó — và biết khi nào phải hỏi người."* | W5 | idea 20% |
| **Q&A** | *"Mời thầy chọn giúp em một lỗi bất kỳ."* Đưa chaos panel cho BGK | W1 | phản biện 20% |

Nhịp 3:45 là khoảnh khắc mạnh nhất: chứng minh hệ thống trung thực **ngay cả khi dữ liệu trông hoàn toàn bình thường**.

---

## 10. Ba câu BGK sẽ hỏi — đáp án gắn với wow

1. *"AI khác gì if/else?"* → mở W2. *"Threshold so với hằng số. Twin của em so với kỳ vọng vật lý học online từ chính nông trại này."*
2. *"Feature nào ảnh hưởng mạnh nhất?"* → feature deviation panel, chỉ đúng feature + đóng góp %.
3. *"LLM nói sai thì sao?"* → W4 + safety layer. *"LLM chỉ đề xuất. Rule cứng phủ quyết, và khi bằng chứng yếu hệ thống tự hạ mức xuống ESCALATE."*

---

## 11. Rủi ro của phương án 5 người + AI nhanh

| Rủi ro | Vì sao trầm trọng hơn khi đông người | Chặn |
|---|---|---|
| **5 schema khác nhau** do 5 tab ChatGPT sinh song song | cao nhất | M3 chốt contract **bằng tay** lúc 08:15, ghi ra file, cấm sửa sau 09:30 |
| Merge conflict | 5 người 1 repo | mỗi người 1 thư mục sở hữu, PR nhỏ, không ai sửa file người khác |
| M5 sửa core làm vỡ pipeline | wow phá mất nền | chaos panel là middleware độc lập, chỉ 1 hook |
| Code AI sinh ra không ai đọc | debug lúc 12:30 sẽ chết | ai commit người đó phải giải thích được; freeze 12:00 nghiêm |
| Demo phụ thuộc mạng (Telegram/LLM) | mất mạng = mất demo | cache LLM response; Telegram có thể tắt; **video backup 13:30** |

---

## 12. Câu hỏi cần chốt gấp

1. **Có repo weather demo sẵn không?** ChatGPT nhiều lần nhắc *"repo demo ban đầu của bạn"* đã có Kafka, event-time, watermark, windowing. Repo local chỉ có `docs/`. Nếu repo đó tồn tại → tiết kiệm ~1.5h ingestion, đổi hẳn timeline. **Trả lời trước khi code.**
2. Track B đã bốc trúng chưa?
3. Ai nhận vai M5 (Demo & Wow)? Nên là người nói tốt nhất — người này sẽ dẫn pitch.
4. LLM key nào có sẵn, đã test rate limit chưa?
5. Có tạo được Telegram bot token tại chỗ không (cần mạng ngoài)?

---

**Đề xuất tiếp:** duyệt mục 6 + 7 + 8 → mình patch thẳng vào `docs /plan.md`: sửa GAP-1, chèn GAP-2/3/4 + W1–W5, cắt SHAP + ETo, thay timeline 5 người, thay kịch bản demo v2.
