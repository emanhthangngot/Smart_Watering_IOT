# **SEAL Hackathon Summer 2026 – Team Brief**

## **1\. Mục tiêu của cuộc thi**

Chủ đề là:

**AI-Driven Smart Operations: Turning Real-Time IoT Data into Intelligent Actions**

Điều BTC muốn thấy không phải chỉ là:

IoT → Dashboard → Biểu đồ

mà nên tiến tới:

IoT Data  
→ Xử lý real-time  
→ AI phát hiện / phân tích  
→ Giải thích  
→ Đưa ra quyết định / hành động

Workshop nhấn mạnh hệ thống AI Smart Operations phải đi xa hơn cảnh báo bằng `if/else`, hướng tới phát hiện sớm, hiểu nguyên nhân và hỗ trợ xử lý.

---

# **2\. Điều cần biết về dữ liệu ngày thi**

BTC sẽ cung cấp **live IoT data stream**. Team không cần tự kết nối sensor vật lý; dữ liệu được đưa qua hệ thống/port do BTC cung cấp.

Ngày nhận Track, chúng ta chưa chắc biết trước:

* sensor nào;  
* field nào;  
* có label hay không;  
* domain cụ thể.

Vì vậy đừng chuẩn bị riêng một app Weather. Demo Weather trong workshop chỉ là ví dụ kiến trúc, **không phải đề thi chính thức**.

---

# **3\. Pipeline nên hiểu và chuẩn bị**

Kiến trúc tổng quát:

IoT Sensor / BTC Stream  
        ↓  
MQTT / CoAP  
        ↓  
Ingestion / Normalize Data  
        ↓  
Kafka / Redpanda (nếu cần)  
        ↓  
Stream Processing  
        ↓  
Window \+ Feature Engineering  
        ↓  
ML / AI  
        ↓  
RCA / Explanation  
        ↓  
LLM Recommendation  
        ↓  
Dashboard / Action Workflow

Workshop chia kiến trúc thành ingestion → distributed buffer → stream processing → storage/AI.

---

# **4\. MQTT / CoAP**

### **MQTT**

Port: 1883 TCP  
Model: Publish / Subscribe

Các khái niệm cần biết:

Broker  
Topic  
Publisher  
Subscriber  
QoS

Workshop khuyến nghị tư duy **QoS 1 \+ event\_time**, sau đó xử lý duplicate downstream.

### **CoAP**

Port: 5683 UDP

Phù hợp thiết bị nhẹ, tiết kiệm pin.

Dù data đến từ MQTT hay CoAP, backend nên **normalize về một format chung**.

Ví dụ:

{  
  "device\_id": "M01",  
  "event\_time": "...",  
  "metrics": {  
    "temperature": 80,  
    "vibration": 3.2  
  }  
}

---

# **5\. Kafka / Redpanda dùng để làm gì?**

Vai trò chính:

IoT gửi data rất nhanh  
        ↓  
Kafka / Redpanda giữ stream  
        ↓  
Backend / AI xử lý theo tốc độ của mình

→ tránh bottleneck và tách producer khỏi consumer.

Nếu dùng Kafka/Redpanda:

key \= station\_id / device\_id

để dữ liệu của cùng một thiết bị giữ đúng thứ tự. Workshop nhấn mạnh nếu không dùng ID làm partition key thì ordering có thể bị sai.

**Nhưng:** nếu BTC không yêu cầu Kafka, không nên mất hàng giờ tự dựng Kafka chỉ để có kiến trúc đẹp.

---

# **6\. Event Time rất quan trọng**

Phân biệt:

Event Time  
\= lúc sensor thực sự đo.

Processing Time  
\= lúc server nhận được.

IoT có thể gặp network delay nên event đến trễ hoặc sai thứ tự.

Workshop nhấn mạnh nên xử lý time-series bằng **event time**, không dựa hoàn toàn vào thời gian server nhận packet.

---

# **7\. Watermark \+ Windowing**

### **Watermark**

Ví dụ:

watermark \= max(event\_time) \- 5s

→ cho phép dữ liệu đến trễ một khoảng nhất định.

### **Tumbling Window**

1 phút / window  
không overlap

Dùng để tính:

average  
min  
max  
sum

### **Sliding Window**

Ví dụ workshop:

Window \= 5 phút  
Slide \= 1 phút

Dùng để phát hiện:

trend  
rate of change  
sự thay đổi bất thường

Đây là phần rất hữu ích cho AI.

---

# **8\. Không đưa raw sensor trực tiếp vào AI**

Ví dụ:

Temperature \= 40°C

chưa chắc bất thường.

Nhưng:

25°C → 40°C trong 1 phút

có thể rất nguy hiểm.

Workshop nhấn mạnh cần **Feature Engineering trước AI**.

Các feature nên thử:

current  
mean  
min / max  
std  
delta  
slope / rate of change  
z-score

Nếu có vibration/audio/waveform:

FFT

có thể hữu ích.

---

# **9\. AI nên làm thế nào?**

Nếu **không có label**:

Isolation Forest

là lựa chọn rất phù hợp:

* nhanh;  
* chạy CPU;  
* không cần label;  
* dễ làm trong hackathon.

Nếu **có labeled data**:

Random Forest  
XGBoost  
LightGBM

có thể phù hợp hơn.

Không nên phụ thuộc vào việc BTC chắc chắn cung cấp labeled dataset vì workshop/Q\&A không xác nhận điều đó.

---

# **10\. AI không nên chỉ trả “Anomaly”**

Output tốt hơn:

Anomaly Score  
        ↓  
Why?  
        ↓  
Likely Root Cause  
        ↓  
Risk  
        ↓  
Recommended Action

Ví dụ:

Risk: 89/100 – CRITICAL

Why:  
\- Vibration increasing rapidly  
\- Temperature increasing

Possible Cause:  
Bearing degradation

Recommended:  
\- Reduce load  
\- Inspect bearing

Có thể dùng **SHAP** để giải thích feature nào ảnh hưởng mạnh đến prediction. Workshop đặc biệt nhấn mạnh đây là câu BGK có thể hỏi.

---

# **11\. LLM nên dùng ở đâu?**

Không nên:

Every sensor packet  
→ Gemini / GPT

Nên:

Sensor  
→ Window  
→ Features  
→ ML detection  
→ Significant event  
→ LLM

LLM nên nhận:

processed metrics  
\+ anomaly evidence  
\+ domain context  
\+ SOP

rồi làm:

explanation  
diagnosis  
recommendation

Nên bắt LLM trả **structured JSON** để backend/frontend dễ xử lý.

---

# **12\. Safety Guardrail**

Không nên để LLM tự quyết định mọi thứ.

Flow:

LLM Recommendation  
        ↓  
Hard Safety Rules  
        ↓  
PASS / REJECT

Ví dụ:

IF pressure \> safe\_limit  
AND AI recommends close\_valve  
→ REJECT

Workshop nhấn mạnh LLM có thể hallucinate nên action cần đi qua deterministic safety layer.

---

# **13\. Điều quan trọng: không điều khiển ngược thiết bị thật**

BTC nói hiện tại team **không tương tác chiều ngược trực tiếp với thiết bị**, chủ yếu là nhận stream rồi xử lý.

Vì vậy action có thể là:

AI Recommendation  
↓  
Approve / Reject  
↓  
Notification  
Ticket  
Telegram  
Simulated Action

BTC cũng gợi ý có thể tích hợp third-party service cho workflow/action.

---

# **14\. MVP nên làm trong 7 giờ**

Ưu tiên:

1\. Kết nối live IoT stream

2\. Normalize data

3\. Window \+ Feature Engineering

4\. AI model chạy thật

5\. Risk / Anomaly score

6\. Dashboard update realtime

7\. Explanation / RCA

8\. Recommended Action

9\. Safety / Human Approval

10\. Incident Timeline

Không ưu tiên sớm:

Kubernetes  
nhiều microservice  
Neo4j phức tạp  
LangGraph nhiều agent  
Flink nếu chưa biết  
Redis \+ TimescaleDB nếu chưa cần  
deep learning khi baseline chưa chạy

---

# **15\. Workflow ngay khi nhận Track**

Trước khi code, team trả lời:

WHO?  
Ai sử dụng hệ thống?

PROBLEM?  
Vấn đề vận hành là gì?

DATA?  
Sensor nào có?

AI?  
AI cần detect/predict gì?

WHY?  
AI tạo giá trị gì hơn threshold?

ACTION?  
Sau khi AI phát hiện thì người dùng làm gì?

Sau đó mới map vào pipeline.

---

# **16\. Chia team gợi ý**

### **Member 1 – IoT / Streaming**

MQTT/API  
schema  
event time  
window

### **Member 2 – AI/Data**

feature engineering  
model  
metrics  
SHAP

### **Member 3 – Backend/Decision**

FastAPI  
LLM  
RCA  
safety  
WebSocket

### **Member 4 – Frontend/Product**

dashboard  
incident UI  
action UI  
pitch

---

# **17\. Demo nên kể một Incident**

Đừng demo kiểu:

> Đây là chart temperature.

Hãy:

NORMAL  
↓  
Sensor bắt đầu thay đổi  
↓  
AI phát hiện anomaly  
↓  
Risk tăng  
↓  
AI giải thích tại sao  
↓  
Xác định tình huống / nguyên nhân  
↓  
Đề xuất action  
↓  
Operator approve / simulated action

Đây mới đúng tinh thần:

**Turning Real-Time IoT Data into Intelligent Actions.**

---

# **18\. Công thức cần nhớ**

IoT Stream  
\+  
Temporal Processing  
\+  
Feature Engineering  
\+  
AI  
\+  
Domain Knowledge  
\+  
Action  
\=  
Smart Operations

Không phải:

IoT \+ ChatGPT

---

# **Kết luận cho Team**

Ngày thi nên tập trung vào:

**1\. Nhận data thật ổn định.**

**2\. Xử lý time-series đúng.**

**3\. AI phải tạo giá trị thực, không chỉ threshold.**

**4\. AI phải giải thích được.**

**5\. Kết quả phải dẫn đến decision/action.**

**6\. Demo phải ổn định và kể được một câu chuyện rõ ràng.**

Kiến trúc mục tiêu:

IoT  
↓  
Normalize  
↓  
Window  
↓  
Features  
↓  
AI  
↓  
Explain  
↓  
Decision  
↓  
Action  
↓  
Dashboard

Nếu phải chọn giữa **hạ tầng rất phức tạp nhưng chưa chạy** và **pipeline đơn giản nhưng real-time \+ AI \+ demo tốt**, hãy chọn phương án thứ hai.

