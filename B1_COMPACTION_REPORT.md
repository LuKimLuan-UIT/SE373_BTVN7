# B1 – Lựa chọn và thực hiện compact

## Mục đích thử nghiệm truncation

Nhóm sử dụng truncation làm phương pháp đối chứng để quan sát sự đánh đổi giữa
kích thước context và khả năng duy trì thông tin. Phương pháp giữ các lượt hội thoại
gần nhất và bỏ những lượt cũ, không tạo summary hay checkpoint. Ảnh thử nghiệm
trước ghi nhận working context ước lượng giảm từ 5.493 xuống 792 token (85,58%),
nhưng model chỉ nhớ lại một phần nội dung gần nhất. Kết quả cho thấy cắt giảm token
thành công chưa đủ để đáp ứng mục tiêu bảo toàn trạng thái công việc của B1.
Các số này thuộc thử nghiệm truncation đã chụp, không phải số đo của structured.

Ưu điểm của truncation là đơn giản, thực hiện nhanh, kết quả xác định theo history
và số lượt giữ, không phát sinh lượt gọi model. Nhược điểm là không đánh giá ý nghĩa
nội dung: lỗi đang điều tra, ràng buộc, bằng chứng hoặc cách đã thử có thể bị mất
nếu nằm trong các lượt bị cắt. Archive vẫn còn nhưng không tự được đưa lại model.

## Phương pháp được lựa chọn cho B1

Nhóm chọn **structured compaction bằng checkpoint có cấu trúc** làm phương án
chính để đánh giá B1; truncation được giữ làm đối chứng. Đây cũng là lựa chọn mặc
định trên giao diện mới, người dùng có thể đổi trước mỗi lần compact.

Lý do lựa chọn là B1 cần agent không chỉ giảm context mà còn nhớ lỗi đang điều tra,
các cách đã thử và bước kế tiếp. Checkpoint biểu diễn trực tiếp những thông tin này
qua các trường goal, current_state, constraints, findings, failed_attempts, files,
next_action và open_questions. Cấu trúc rõ ràng giúp kiểm tra thông tin bị thiếu và
đối chiếu với lịch sử gốc. Cơ chế được tái sử dụng từ project hiện có.

## Ưu điểm và hạn chế

Ưu điểm là có thể thay output AI/tool dài bằng trạng thái công việc ngắn hơn, giữ
ràng buộc và kết luận quan trọng từ các lượt trước trong checkpoint. Instructions
và user messages được giữ nguyên; kế hoạch AI ngắn gần nhất cũng được giữ để hạn
chế mất đường dẫn và thứ tự hành động. Lịch sử gốc còn trong archive để đối chiếu.

Hạn chế là Provider cần thêm lượt gọi model, làm tăng thời gian và usage ban đầu.
Model có thể tóm tắt thiếu hoặc sai, ngay cả khi JSON hợp lệ. Việc giữ toàn bộ user
messages cũng hạn chế mức giảm nếu người dùng đưa log dài trực tiếp vào tin nhắn.
Vì vậy, schema hợp lệ và context nhỏ hơn chưa đủ để kết luận đạt B1; phải kiểm tra
continuation. Giảm working context không đồng nghĩa giảm tổng chi phí cả phiên.

## Cách thực hiện

1. Tạo snapshot active context và giữ nguyên archive. Chỉ xử lý phần active hiện
   tại, không tự đưa lại dữ liệu đã bị truncation.
2. Với Provider, gửi instructions cùng active history cho model để tạo checkpoint
   JSON. Yêu cầu giữ lỗi chưa giải quyết, constraints, bằng chứng có nguồn, cách
   đã thử, đường dẫn và thứ tự bước tiếp theo; không biến giả thuyết thành kết luận.
3. Kiểm tra schema, giới hạn checkpoint 12.000 bytes và kích thước context mới.
   Nếu model lỗi, checkpoint không hợp lệ hoặc context không giảm, giữ nguyên
   history. Usage đã tiêu thụ vẫn được ghi nhận khi provider cung cấp.
4. Tạo active context mới gồm user/system/developer messages còn hiệu lực, kế
   hoạch AI ngắn gần nhất (nếu đủ điều kiện) và checkpoint thay thế output AI/tool.
5. Hiển thị context trước/sau, checkpoint và usage, sau đó yêu cầu agent tiếp tục.
   Đối chiếu lỗi, ràng buộc, cách đã thử và bước tiếp theo với history gốc.

Offline dùng bộ trích xuất theo mẫu, không gọi LLM, chỉ phục vụ demo và kiểm tra
luồng dữ liệu; không dùng kết quả này để khẳng định chất lượng tóm tắt của model.
Để so sánh hai chế độ, nạp hai phiên mẫu giống nhau. Đổi từ truncation sang structured
trên history đã cắt không thể phục hồi thông tin đã mất.
