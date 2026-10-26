# Challenge B hiện tại: Truncation

Phạm vi: web/API riêng `/challenge-b` và `/api/challenge-b/*`. Challenge A, API
compact chung, Word và báo cáo đã có được giữ nguyên. Báo cáo checkpoint cũ mô tả
phiên bản trước; không dùng các số đo đó để đánh giá bản truncation hiện tại.

## Cách thử không tốn API

1. Mở `/challenge-b`, chọn **Offline · 0 API**.
2. Bấm **Nạp phiên dài mẫu · B1**. Fixture có ba lượt user→assistant; ràng buộc,
   bằng chứng file/dòng và log dài nằm trong lượt đầu.
3. Mở ⓘ, chọn **giữ 2 lượt gần nhất**, bấm **Truncation** và xác nhận.
4. Đối chiếu context trước/sau, số lượt/messages bỏ và usage không tăng.
5. Nhắn “Tiếp tục: thông tin nào còn trong context hiện tại?”. Offline chỉ trích
   các message đang giữ; không gọi LLM hoặc đọc archive để bù thông tin đã mất.

Kỳ vọng: giữ hai lượt gần nhất, mất thông tin ở lượt đầu khỏi active context.
Archive gốc và transcript vẫn đầy đủ để người kiểm tra đối chiếu. Reload trang
giữ active context đã cắt và các mốc truncation trong chat.

Nếu cần đánh giá model thật, chọn Provider cho một chat riêng. Truncation vẫn
0 API; các tin nhắn gửi model trước/sau truncation mới tiêu thụ usage. Không tự
chạy lại provider để kiểm thử giao diện.

## Quy tắc cắt

- Giữ nguyên system/developer instructions đứng đầu history và N lượt mới nhất
  (1–50, mặc định 2). System prompt/memory index từ middleware vẫn được inject.
- Không xét ý nghĩa, không giữ riêng user constraint cũ, không tổng hợp hoặc
  tạo checkpoint. Tool call/result đi cùng trong lượt; không cắt chuỗi tool dở.
- Không đủ lượt để cắt, tham số sai hoặc tool history chưa hoàn tất: báo lỗi,
  không sửa context. Chỉ ghi khi kích thước active giảm.
- Archive không tự gửi lại model. Nội dung ở đó không được coi là model còn biết.
- Có thể truncation nhiều lần sau khi thêm lượt mới; các lượt cũ đã bỏ không quay lại.

## Các kỹ thuật

| Kỹ thuật | Cách làm | Rủi ro | Hiện trạng trên trang B |
|---|---|---|---|
| Truncation | Bỏ messages cũ theo lượt hoàn chỉnh | Mất ràng buộc | Đang dùng |
| Tool-output pruning | Loại log thô/trùng lặp | Bỏ sót bằng chứng | Chưa bật |
| Summary | LLM rút gọn history | Hallucinate, bỏ sót | Chưa bật |
| Structured checkpoint | Lưu state theo schema | Thiếu trường quan trọng | Chưa bật |
| Incremental summary | Nén từng giai đoạn | Lỗi tích lũy | Chưa bật |
| Selective keep/drop | Giữ nguyên đoạn quan trọng | Chọn nhầm đoạn | Chưa bật |

Đánh giá trung thực: context giảm không đồng nghĩa giữ đủ thông tin. Nếu ràng
buộc/next action bị mất, ghi nhận điều đó; không đánh dấu PASS cho tiêu chí giữ
ràng buộc chỉ vì số token giảm. B2 vẫn dùng runtime đếm log có đáp án chuẩn.

## API

`POST /api/challenge-b/chat/compact` với `thread_id` và `keep_turns` trả kết quả
truncation và chat mới nhất. `/api/challenge-b/b1/compact` cũng dùng truncation.
Kết quả có `technique`, `dropped_turns`, `dropped_messages`, `before`, `after`,
`archive_preserved`, `risk`, `compaction_requests=0`; không có `checkpoint`.

## Kiểm thử

`python -m pytest -q --basetemp=data/pytest-b`

Kiểm thử dùng model giả/dữ liệu tạm, kiểm tra tool pairing, không gọi model khi
truncation, context giảm, archive bất biến, usage không tăng, thông tin cũ không
được đưa lại vào request, và dữ liệu A không thay đổi.
