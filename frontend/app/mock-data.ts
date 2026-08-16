export const devices = [
  { id: "SOIL_01", code: "SO", label: "Độ ẩm đất / Nhiệt độ", value: "31.8 / 28.4", unit: "% / °C", age: "6 giây", tone: "warning" },
  { id: "WEATHER_01", code: "WX", label: "Nhiệt độ / Độ ẩm", value: "32.6 / 71", unit: "°C / %", age: "9 giây", tone: "normal" },
  { id: "PUMP_01", code: "PU", label: "Lưu lượng / Công suất", value: "22.4 / 742", unit: "L/phút / W", age: "4 giây", tone: "warning" },
  { id: "PH_01", code: "PH", label: "Độ pH", value: "6.4", unit: "pH", age: "12 giây", tone: "normal" },
  { id: "TANK_01", code: "TK", label: "Mực nước", value: "63", unit: "%", age: "7 giây", tone: "normal" },
  { id: "SUN_01", code: "LX", label: "Cường độ sáng", value: "48,260", unit: "lx", age: "11 giây", tone: "normal" },
] as const;

export const agentSteps = [
  { code: "CO", agent: "Coordinator", action: "Mở nhiệm vụ và phân công", meta: "08:41:02", status: "done" },
  { code: "IO", agent: "Field IoT", action: "Đối chiếu PUMP_01, TANK_01, SOIL_01", meta: "08:41:08", status: "done" },
  { code: "DG", agent: "Diagnosis", action: "Đánh giá hiệu quả cấp nước", meta: "82% tin cậy", status: "done" },
  { code: "RS", agent: "Resource", action: "Kiểm tra ca trực và vật tư", meta: "Sẵn sàng", status: "done" },
  { code: "AC", agent: "Action", action: "Chờ phê duyệt tạo phiếu", meta: "Human gate", status: "active" },
] as const;

export const activity = [
  { time: "08:41", title: "Phát hiện sai lệch lưu lượng", detail: "Rule IRR-FLOW-04 · PUMP_01 giảm 42% so với nền 5 phút" },
  { time: "08:40", title: "Phiên tưới bắt đầu", detail: "Schedule IRR-A-0815 · van khu A mở theo kế hoạch" },
  { time: "08:36", title: "Kế hoạch đã được xác minh", detail: "TANK_01 đủ nước · không có cảnh báo thời tiết" },
] as const;
