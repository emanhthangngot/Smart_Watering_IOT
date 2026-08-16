**TRACK B: SMART AGRICULTURE**

**Multi-Agent Farm Operations & Resource Coordination**

**1\. Bối cảnh Domain**

Một nông trại sử dụng cảm biến đất, thời tiết, bồn nước và máy bơm để hỗ trợ hoạt động tưới tiêu và quản lý tài nguyên.

Người quản lý cần phối hợp giữa điều kiện canh tác, lịch tưới, nguồn nước, thiết bị và nhân sự ngoài hiện trường.

Đội thi xây dựng một sản phẩm Multi-Agent AI có khả năng:

Quan sát điều kiện canh tác qua MQTT.

Phối hợp nhiều Agent để lập kế hoạch hoặc xử lý công việc.

Tạo nhiệm vụ tưới, yêu cầu kiểm tra, lịch làm việc hoặc thông báo qua Tool/API.

Kiểm tra kết quả và trình bày rõ dữ liệu đã sử dụng.

**2\. Persona mục tiêu**

**Persona chính \- Người quản lý nông trại**

Thường sử dụng điện thoại hoặc máy tính bảng.

Cần thông tin nhanh, dễ đọc ngoài hiện trường.

Quan tâm đến khu vực, tài nguyên và công việc cần ưu tiên.

**Persona phụ \- Kỹ sư nông nghiệp**

Cần xu hướng độ ẩm đất, thời tiết, lưu lượng và mực nước.

Cần bằng chứng để điều chỉnh vận hành.

Cần biết kế hoạch nào đã được tạo và ai chịu trách nhiệm.

**3\. Thiết bị và dữ liệu**

| Device code | Thiết bị | Metric | Đơn vị |
| ----- | ----- | ----- | ----- |
| **SOIL\_01** | Cảm biến đất khu A | soil\_moisture, temperature | %, °C |
| **WEATHER\_01** | Trạm thời tiết | temperature, humidity | °C, % |
| **PUMP\_01** | Bơm tưới khu A | flow\_rate, power | L/min, W |
| **PH\_01** | Cảm biến pH bồn | ph | pH |
| **TANK\_01** | Bồn nước chính | level | % |
| **SUN\_01** | Cảm biến nắng khu A | lux | lx |

 

Xây dựng một hệ thống Multi-Agent AI hỗ trợ điều hành nông trại. Sản phẩm có thể tập trung vào lập kế hoạch tưới, quản lý nguồn nước, phối hợp công việc ngoài hiện trường, quản lý thiết bị hoặc tạo báo cáo canh tác.

Sản phẩm phải thể hiện được chu trình:

| Nhận yêu cầu → Đọc dữ liệu IoT → Phân công Agent → Phối hợp → Tool/API → Verification → Báo cáo |
| :---- |

**5\. Cấu trúc Agent gợi ý**

**Farm Coordinator Agent** \- Nhận yêu cầu, chia tác vụ và tổng hợp quyết định.

**Field IoT Agent** \- Đọc dữ liệu đất, thời tiết, bơm, pH, bồn nước và ánh sáng.

**Irrigation Planning Agent** \- Đề xuất kế hoạch tưới hoặc thứ tự ưu tiên công việc.

**Resource Agent** \- Kiểm tra nguồn nước, nhân sự hoặc tài nguyên mô phỏng.

**Farm Action Agent** \- Tạo lịch tưới, nhiệm vụ kiểm tra, thông báo hoặc báo cáo qua Tool/API.

Đội thi được tự do thay đổi tên, số lượng và kiến trúc Agent, miễn đáp ứng yêu cầu tối thiểu chung và chứng minh mỗi Agent có vai trò thực sự cần thiết.

**6\. Kịch bản tác vụ đơn giản**

**Kịch bản 1 \- Lập kế hoạch tưới trong ngày**

**Yêu cầu:** *“Hãy chuẩn bị kế hoạch tưới cho khu A trong hôm nay và giải thích dữ liệu đã sử dụng.”*

Cách xử lý gợi ý:

1\. Field IoT Agent đọc SOIL\_01, WEATHER\_01, TANK\_01, SUN\_01 và PUMP\_01.

2\. Irrigation Agent đề xuất thời điểm và mức ưu tiên.

3\. Resource Agent kiểm tra nguồn nước hoặc ràng buộc tài nguyên.

4\. Coordinator tổng hợp kế hoạch và yêu cầu người quản lý xác nhận nếu cần.

5\. Action Agent tạo lịch tưới trong hệ thống và đọc lại để verification.

BTC quan sát:

Không chấm một công thức tưới duy nhất.

Chấm cách phối hợp Agent, sử dụng dữ liệu và giá trị của kế hoạch.

**Kịch bản 2 \- Kiểm tra hoạt động tưới**

**Yêu cầu:** *“Hãy kiểm tra phiên tưới hiện tại và chuẩn bị công việc cần thực hiện nếu kết quả không như mong đợi.”*

Cách xử lý gợi ý:

1\. Field IoT Agent tổng hợp PUMP\_01, SOIL\_01 và TANK\_01.

2\. Irrigation Agent xác định thông tin cần kiểm tra thêm.

3\. Resource hoặc Maintenance Agent đề xuất nhiệm vụ ngoài hiện trường.

4\. Action Agent tạo phiếu kiểm tra hoặc gửi thông báo.

5\. Hệ thống xác minh phiếu kiểm tra đã tồn tại.

BTC quan sát:

Dữ liệu MQTT có được sử dụng để chọn nội dung công việc hay không.

Hệ thống có tránh kết luận quá mức khi thiếu dữ liệu hay không.

**Kịch bản 3 \- Dữ liệu hiện trường bị gián đoạn**

**Yêu cầu:** *“Dữ liệu một số cảm biến vừa ngừng cập nhật. Hãy tiếp tục lập kế hoạch công việc cho đội ngoài hiện trường.”*

Cách xử lý gợi ý:

1\. Field IoT Agent xác định thiết bị có dữ liệu cũ.

2\. Coordinator tách phần có thể xử lý và phần cần xác minh.

3\. Action Agent tạo nhiệm vụ kiểm tra cảm biến hoặc kết nối.

4\. Reporting Agent ghi rõ giới hạn dữ liệu trong kế hoạch.

BTC quan sát:

Không bịa giá trị mới.

Có khả năng tiếp tục tác vụ ở chế độ partial.

Có hành động kiểm tra phù hợp.

**7\. Yêu cầu UX**

Giao diện responsive cho điện thoại hoặc máy tính bảng.

Hiển thị trạng thái kết nối và độ mới của dữ liệu.

Hiển thị kế hoạch, nhiệm vụ và người/Agent chịu trách nhiệm.

Thể hiện rõ dữ liệu IoT đã ảnh hưởng đến quyết định nào.

Có khu vực phê duyệt kế hoạch hoặc hành động quan trọng.

Thể hiện kết quả Tool/API và verification.

**8\. User stories**

Là người quản lý nông trại, tôi muốn AI phối hợp để tạo kế hoạch tưới có căn cứ.

Là người vận hành, tôi muốn hệ thống tạo nhiệm vụ kiểm tra khi cần.

Là kỹ sư nông nghiệp, tôi muốn xem dữ liệu IoT mà các Agent đã sử dụng.

Là người dùng ngoài hiện trường, tôi muốn giao diện dễ đọc trên màn hình nhỏ.

Là người quản lý, tôi muốn biết khi dữ liệu không còn mới và cần xác minh thủ công.

**9\. Điều kiện chấp nhận theo Track**

Nhận và hiển thị hoặc truy xuất dữ liệu tối thiểu 04/06 thiết bị.

Có tối thiểu 03 Agent và một tác vụ cần ít nhất 02 Agent phối hợp.

Có ít nhất một kế hoạch hoặc quyết định sử dụng dữ liệu MQTT.

Có Tool/API tạo lịch tưới, nhiệm vụ kiểm tra, thông báo hoặc báo cáo.

Có verification sau hành động.

Giao diện không vỡ layout trên màn hình điện thoại.

