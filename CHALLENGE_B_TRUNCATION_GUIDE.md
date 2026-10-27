# Challenge B: hai chế độ compact

Phạm vi: `/challenge-b` và `/api/challenge-b/*`. Không thay namespace A hay API
compact chung. Tên file được giữ để các liên kết cũ tiếp tục hoạt động.

## Cách đổi chế độ

Ô chọn cạnh nút Compact có Structured compaction (mặc định giao diện) và Truncation.
Lựa chọn lưu trong trình duyệt, có thể đổi trước mỗi lần chạy; chọn chế độ không tự
cắt, không gọi model, không reset chat. Khi đang xử lý thì khóa lựa chọn.

- Truncation: giữ N lượt gần nhất, chỉnh N trong ⓘ; 0 API ở cả Offline và Provider.
- Structured + Provider: model trong .env tạo checkpoint; lượt gọi phát sinh usage.
- Structured + Offline: OfflineCompactor trích xuất theo mẫu; 0 API, không phải LLM.

Đổi chế độ không khôi phục dữ liệu đã bỏ khỏi active. Nạp lại phiên mẫu cho từng
phép thử để so sánh trên cùng history. Archive vẫn giữ riêng, không tự đọc lại.

## B1: chạy thử

1. Chọn Offline nếu muốn thử không tốn API; Provider nếu cần kiểm tra model thật.
2. Nạp phiên dài mẫu: có lỗi 401, ràng buộc /refresh và không log token, cách tăng
   timeout thất bại, bằng chứng auth.py:184 / race.log:7 và kế hoạch concurrency test.
3. Chọn Truncation, giữ 2 lượt và chạy. Kiểm tra thông tin ở lượt đầu bị mất.
4. Nạp phiên mẫu mới, chọn Structured compaction và chạy. Mở Xem checkpoint.
5. Hỏi bước kế tiếp, ràng buộc và cách đã thử. So sánh với history gốc và số đo.

Offline chỉ kiểm tra trích xuất có quy tắc/data flow. Provider mới kiểm tra khả năng
model tạo checkpoint và tiếp tục công việc. Không tự chạy Provider để kiểm thử UI.

## Hai cơ chế

Truncation giữ prefix system/developer và N lượt human-led hoàn chỉnh; không ghép
summary hoặc giữ riêng constraint cũ. Kiểm tra tool pairing trước/sau; từ chối nếu
history chưa hoàn tất, số lượt không đủ hoặc context không nhỏ hơn.

Structured tái sử dụng WorkingContext.compact: giữ các human/system/developer
messages (trừ checkpoint/index cũ được thay), kế hoạch AI cuối nếu không có tool
calls và dài tối đa 2.000 ký tự; tạo checkpoint JSON có goal, current_state,
constraints, findings, failed_attempts, files, next_action, open_questions. Thay các
AI/tool messages còn lại bằng checkpoint. Schema hợp lệ, tối đa 12.000 bytes và
working context phải nhỏ hơn trước mới ghi thay đổi. Giữ nhiều human messages làm
hạn chế mức giảm khi log dài nằm trong user input. Schema không kiểm chứng ngữ nghĩa.

Timeline phân biệt hai kỹ thuật. Structured có checkpoint mở rộng, phương pháp
model/offline và usage. Usage cộng dồn cả lượt compact Provider đã gọi nhưng bị từ
chối vì checkpoint sai hoặc lớn hơn. Thiếu usage được ghi unknown, không gán 0.

## API và tương thích

`POST /api/challenge-b/chat/compact` hoặc `/api/challenge-b/b1/compact`:

```json
{"thread_id":"b1-...", "technique":"structured", "keep_turns":2}
```

`technique` là `truncation` hoặc `structured`; bỏ trường này vẫn dùng truncation để
không phá client cũ. `keep_turns` từ 1–50, chỉ tác động truncation. Structured trả
checkpoint, measurement và summary_method; truncation trả số lượt/messages đã bỏ.
Cả hai trả before/after ước lượng; không coi đó là usage thật hoặc tiền tiết kiệm.

## Kiểm thử

```powershell
python -m pytest -q --basetemp=data/pytest-b
```

Dùng model giả/dữ liệu tạm, kiểm tra hai mode, continuation, archive, usage thành
công/thất bại/thiếu, lựa chọn frontend và request đúng kỹ thuật; không gọi API thật.
