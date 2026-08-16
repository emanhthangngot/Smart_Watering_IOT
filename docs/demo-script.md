# Kịch bản demo — FarmOps AI

**Owner:** dev
**Mục tiêu:** chứng minh vòng khép kín SENSE → REASON → PLAN → APPROVE → ACT → VERIFY → OBSERVE → REPLAN chạy thật, không phải kịch bản dựng sẵn.
**Thời lượng:** ~6-7 phút nói + demo.
**Data nguồn:** simulator nhân quả (`sim/world.py`, `ACTUATION_TARGET=sim`), không phải MQTT farm thật — nói rõ điều này nếu giám khảo hỏi (mục "Nếu bị hỏi" cuối file). Downstream (Postgres, trust engine, agents, verification) chạy 100% thật trên data đó.

---

## 0. Trước khi lên demo — checklist môi trường

```bash
# Postgres local
docker ps --filter name=farmops --format "{{.Names}} {{.Status}}"
# phải thấy: vamos-farmops-postgres-1   Up ... (healthy)
# nếu không: docker compose -f store/docker-compose.yml up -d --wait

# Backend
ss -ltnp | grep :8000
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
# status phải "ok", batchPeriodSeconds phải có số thật (không null)

# Frontend
ss -ltnp | grep :5173
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/health
# phải 200 (nếu 404 → vite proxy stale, xem mục "Sự cố thường gặp")
```

Mở sẵn: `http://127.0.0.1:5173` trên trình chiếu, zoom trình duyệt đủ lớn để giám khảo đọc được số.

Nhập operator token 1 lần trước khi lên: góc dưới trái → bánh răng "Quyền vận hành" → `dev-local-token` → Lưu cho session.

---

## 1. Mở màn — vấn đề (30s nói, không thao tác)

> "Tưới tự động phổ biến hiện nay là: đọc một threshold, bơm. Vấn đề: cảm biến kẹt, bơm chạy không hiệu quả, hay ngừng-chạy vẫn trông 'bình thường' trên dashboard nếu chỉ nhìn giá trị tức thời. Hệ tụi em không tin một con số — nó đối chiếu chéo nhiều cảm biến, tính điểm tin cậy theo từng scope, và **từ chối tự hành động** khi bằng chứng không đủ."

Chuyển sang màn hình Tổng quan.

---

## 2. Live Farm Overview (45s)

Trỏ vào các phần theo thứ tự:

1. Badge **LIVE** góc phải header — dữ liệu tự làm mới, không phải ảnh tĩnh.
2. Banner cảnh báo đỏ trên cùng (nếu đang có, vd `CRITICAL — Inspect PH_01 — stuck_at DCS=0.20`) — nói: "Đây không phải cảnh báo giả lập cho demo, nó sinh ra từ trust engine đang chạy real-time bên dưới."
3. Khối "Live Farm / Area A": 6 thiết bị thật (SOIL, TANK, PUMP, WEATHER, SUN, PH), mỗi cái có trạng thái freshness riêng (FRESH/STALE/...).
4. Khối "Sức khỏe dữ liệu" + "Độ tin cậy (DCS)" — chỉ vào số DCS hiện tại, tier (AUTO/PROPOSE/INVESTIGATE).

> "Mỗi con số này tính theo công thức DCS = 0.45·Freshness + 0.35·Completeness + 0.20·K, tách riêng hard-fail (cảm biến hỏng hẳn) khỏi soft-penalty (mâu thuẫn chéo cảm biến). Không phải một threshold đơn."

---

## 3. Gửi yêu cầu vận hành (30s thao tác)

Khối "Bắt đầu workflow":
- Ý định: `Lập kế hoạch tưới`
- Phạm vi: `Khu A`
- Nội dung: gõ trực tiếp trước giám khảo, ví dụ *"Tưới Khu A, giữ tank reserve an toàn"*
- Bấm **Gửi yêu cầu cho Coordinator**

> "Coordinator không tự quyết — nó gọi Field Evidence lấy bằng chứng, Diagnosis và Resource phản biện song song, rồi Planner (LLM chỉ diễn giải, số liệu do allocator tất định tính) mới tạo plan."

Plan card xuất hiện ngay (vài trăm ms) — chỉ vào:
- `planRevisionId` (VD `PLAN-XXXX-V1`)
- Assumption gắn evidence ref cụ thể (`r_...#soil_moisture`) — không phải câu văn suông
- DCS + tier của chính plan này

---

## 4. Mở & duyệt plan — điểm wow thật sự (90s)

Bấm **Xem kế hoạch & phê duyệt**. Trỏ vào:
- Water budget: `availableDrawdownPct` / `requestedDrawdownPct` — có sổ cái nước, không bịa số lít khi chưa biết dung tích tank.
- Actions: `create_irrigation_schedule` với tham số thật (`pumpId`, `startAt/endAt`, `plannedPumpMinutes`).
- Expected outcomes: ngưỡng + tolerance + observation window tường minh, không phải "gần đúng".

Cuộn xuống khối duyệt, bấm **Phê duyệt revision**.

**Hai nhánh có thể xảy ra — chuẩn bị nói cả hai:**

### Nhánh A — DCS đủ cao (tier ≥ PROPOSE)
Action thật thực thi: `create_irrigation_schedule` → schedule runner claim → sim actuator bơm → outcome verification đối chiếu soil moisture thật tăng hay không.
> "Đây là closed-loop thật: lệnh không dừng ở 200 OK, hệ thống còn quay lại đo kết quả thực tế."

### Nhánh B — tier INVESTIGATE (vd cảm biến đang stuck)
Tool layer **tự hạ cấp**: `create_irrigation_schedule` → `create_inspection_task`. Verification-1 báo FAIL đúng nghĩa (kỳ vọng lịch tưới, thực tế nhận được task kiểm tra).
> "Hệ thống không tự tưới liều khi bằng chứng không đủ tin cậy. Nó hạ quyền hành động xuống mức an toàn nhất — tạo task người vận hành đi kiểm tra — thay vì giả vờ mọi thứ ổn."

**Nhánh B mạnh hơn cho giám khảo** — nếu môi trường đang ở tier AUTO/PROPOSE, có thể chủ động trỏ vào lịch sử stuck sensor trước đó (mục 6) để kể lại câu chuyện tương tự đã xảy ra thật trong phiên chạy.

---

## 5. Nhiệm vụ / Inspection tasks (30s)

Tab **Nhiệm vụ**. Chỉ vào:
- Task `Inspect PH_01` (hoặc thiết bị tương ứng), priority HIGH, trạng thái unread.
- Nội dung task nêu rõ device, reason (`Trust rule(s) fired: stuck_at`), evidence ref, hướng dẫn kiểm tra thủ công.

> "Đây là 'safe action hạng nhất' — không phải log ẩn, operator thấy ngay banner + badge, xác nhận đọc rồi đóng khi xử lý xong."

---

## 6. Trace & Explain — trả lời câu hỏi khó nhất (60s)

Tab **Lịch sử & Trace**. Dán trace ID của plan vừa tạo (lấy từ response lúc submit, hoặc):

```bash
curl -s http://127.0.0.1:8000/farm/plan/<PLAN_REVISION_ID> \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['traceId'])"
```

Mở trace, cuộn qua timeline: `FARM_REQUESTED → PLAN_PROPOSED → APPROVED/DOWNGRADED → ...`.

> "Câu hỏi operator luôn cần trả lời được: AI dùng evidence nào, ai phản đối gì, vì sao plan đổi. Đây chính là câu trả lời — replay đầy đủ, không phải log rời rạc phải tự ráp."

Nếu muốn, mở thêm `/explain/<decisionId>` để show evidence node graph (traced ngược `Reading → Evidence → Assumption → Plan → Action`).

---

## 7. Chốt (30s)

> "Ba điều tụi em muốn giám khảo nhớ: một, hệ thống không tin một con số — nó đối chiếu chéo và có điểm tin cậy theo scope. Hai, nó tự hạ quyền hành động khi bằng chứng yếu, không bao giờ giả vờ chắc chắn. Ba, mọi quyết định trace được ngược về evidence gốc — không hộp đen."

---

## Bộ số liệu thật đã capture (dùng khi demo, khỏi gõ tay)

Chạy lúc `2026-08-16T07:29:38Z`, qua HTTP trực tiếp vào backend đang sống lúc viết script này. Nhánh B (INVESTIGATE → tự hạ cấp) — đúng câu chuyện wow ở mục 4.

| Field | Giá trị |
|---|---|
| Trace ID | `trace_7bf5856ac7` |
| Plan lineage / revision | `PLAN-31015740` / `PLAN-31015740-V1` |
| Revision hash | `rh_1_09ca42760a36444e5bb0390e83a72520c8dbedaf092cf4931bcedc36412465aa` |
| Decision ID | `decision_PLAN-31015740-V1` |
| DCS / tier | `0.40` / `INVESTIGATE` |
| Evidence refs | `r_11996c05c9801f2f8b8b7cde#soil_moisture` (34.18%), `r_7b2a8510dff78f445eaba68a#level` (58.6%) |
| Water budget | available `38.6%`, requested `5.0%` |
| Kết quả duyệt | status → `NEEDS_REPLAN`; action `create_irrigation_schedule` **tự hạ cấp** thành `task_1a59434c89` — reason `"tier INVESTIGATE is below PROPOSE"`, priority `HIGH` |
| Timeline (5 event) | `FARM_REQUESTED → PLAN_PROPOSED → FARM_REQUEST_ACCEPTED → ACTION_EXECUTED → PLAN_NEEDS_REPLAN` |

**Câu nói sẵn khi trỏ vào task downgrade:**
> "DCS 0.40, tier INVESTIGATE. Hệ thống nhận lệnh tưới thật, nhưng thay vì bơm nước, nó tự đổi hành động thành `task_1a59434c89` — một task kiểm tra thiết bị, lý do ghi rõ: tier INVESTIGATE thấp hơn PROPOSE. Đây không phải try/except bắt lỗi — đây là chính sách hạ quyền có chủ đích trong tool layer."

Tra lại nguyên văn bất kỳ lúc nào (nếu plan này còn tồn tại trong session backend hiện tại):
```bash
curl -s http://127.0.0.1:8000/farm/plan/PLAN-31015740-V1 | python3 -m json.tool
curl -s http://127.0.0.1:8000/timeline/trace_7bf5856ac7 | python3 -m json.tool
curl -s http://127.0.0.1:8000/explain/decision_PLAN-31015740-V1 | python3 -m json.tool
```
Trên UI: dán `trace_7bf5856ac7` vào ô Trace ID ở tab "Lịch sử & Trace", hoặc mở thẳng `http://127.0.0.1:5173/plans/PLAN-31015740-V1`.

**Lưu ý:** số liệu này chỉ còn đúng khi backend chưa restart (world state simulator reset khi restart). Nếu đã restart, chạy lại mục 3-4 để có bộ số mới, hoặc dùng script này làm mẫu tường thuật còn số thật thay bằng plan mới.

---

## Backup — chạy song song bằng dòng lệnh (nếu UI lỗi giữa chừng)

```bash
cd /home/pearspringmind/Hackathon/vamos_su2026
OPERATOR_TOKEN=dev-local-token FARMOPS_API_URL=http://127.0.0.1:8000 \
  .venv/bin/python -m api.e2e_smoke
```

8 bước PASS/FAIL in ra terminal, kết thúc bằng plan đạt `DONE` hoặc `NEEDS_REPLAN` (cả hai đều là kết thúc hợp lệ — `NEEDS_REPLAN` nghĩa là outcome verification phát hiện thực tế lệch kỳ vọng, hệ thống tự sinh V2 thay vì im lặng coi như thành công).

---

## Sự cố thường gặp

**Frontend 404 mọi API call (proxy stale):**
```bash
pkill -f "vite --port 5173"
cd frontend && nohup npm run dev -- --port 5173 --host 127.0.0.1 > /tmp/vite.log 2>&1 & disown
```

**Muốn reset về baseline (PH_01 hết stuck, DCS cao lại) trước khi lên demo lần 2:**
```bash
ss -ltnp | grep :8000    # lấy PID uvicorn hiện tại
kill <PID>
cd /home/pearspringmind/Hackathon/vamos_su2026
nohup .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 & disown
```
Simulator world state khởi tạo lại từ đầu khi backend restart — mọi fault flag (stuck/leak/offline) reset.

---

## Nếu bị hỏi "data này thật hay giả"

Trả lời thẳng: nguồn telemetry hiện tại là **simulator nhân quả cục bộ** (`sim/world.py`), không phải cảm biến farm qua MQTT — vì `MQTT_HOST/USERNAME/PASSWORD` chưa cấu hình trong phiên demo này. Nhưng simulator **nhân quả thật** (bơm chạy → tank giảm + soil tăng cùng lúc, có fault flag) và ghi qua **đúng path ingest** mà MQTT thật sẽ dùng — nên toàn bộ downstream (Postgres, trust engine, agent, verification) chạy y hệt như khi có data farm thật. Chỉ cần set 5 biến MQTT trong `.env` rồi restart backend là chuyển sang consume broker thật, code không đổi.
