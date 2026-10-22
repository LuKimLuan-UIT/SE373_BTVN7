# Thử như chat và chụp bằng chứng Challenge A

Mở http://127.0.0.1:8000. Giao diện mặc định là chat, không có kịch bản tự chạy.
Nhập câu hỏi vào ô tin nhắn; Enter để gửi, Shift+Enter để xuống dòng.
Tạo session mới cho mỗi bước để chứng minh agent dùng memory thay vì lịch sử chat.

| Bước | Nhập vào ô chat | Cần thấy khi chụp |
|---|---|---|
| 1 | Bên mình đã chốt cơ chế đăng nhập của dự án là JWT. | Agent tự gọi remember dù không có chữ "lưu/nhớ"; memory trước trống, sau có JWT |
| 2 | Dự án mình đang đăng nhập bằng cơ chế nào? | Session mới nạp 0 message lịch sử, gọi recall, trả JWT; không ghi thêm |
| 3 | Nhóm vừa thống nhất bỏ JWT và chuyển hẳn sang session cookie cho đăng nhập. | recall → supersede; trước JWT, sau cookie; mục cũ còn dấu superseded |
| 4 | Hiện tại dự án mình dùng cơ chế đăng nhập nào? | Sau restart, session mới vẫn recall và trả cookie |
| 5 | Chào bạn, hôm nay mình hơi buồn ngủ. | Không đề xuất ghi; memory trước/sau giống nhau |

Các câu này đã chạy thật bằng `cx/gpt-6-luna`. Bạn có thể mở các session
`natural-s1` đến `natural-s5` ở danh sách bên trái để xem lại bằng chứng đã lưu,
không tốn lượt gọi model. Chọn session trước khi bật chế độ chụp ảnh vì chế độ đó
ẩn sidebar và ô nhập để giữ ảnh gọn. Bấm nút lần nữa để trở lại chat.

**Chế độ chụp ảnh** hiện yêu cầu và phản hồi ở bên chat, cùng các phần:

- Model có đề xuất tool ghi hay không; memory thực tế có thay đổi hay không.
- Các mục đang hiệu lực trước và sau lượt chat (snapshot của đúng thời điểm đó).
- Tên tool, tham số đề xuất và kết quả harness/tool trả về.
- Mục active / superseded, key, nguồn session và liên kết thay thế.
- Context thực tế gửi tới từng lượt gọi model, mở thêm khi cần.

Tài liệu/ảnh đã chạy nằm ở `reports/challenge-natural/` và `reports/screenshots/`.
Ảnh không chứa API key. Nếu trình duyệt nằm trong panel hẹp, giao diện xếp dọc;
mở cùng URL trong cửa sổ trình duyệt rộng để xem chat và bằng chứng cạnh nhau.

Memory hiện tại đã là cookie. Nếu tự thực hiện lại từ bước 1, hãy dùng quy ước
demo khác hoặc chấp nhận đây là một thay đổi mới; không xoá dữ liệu chỉ để ảnh
trông giống lần chạy đầu. Ảnh của `natural-s1` luôn giữ snapshot JWT ban đầu.

## Tái hiện bằng terminal SE373

```powershell
conda activate SE373
python scripts/challenge_live.py --natural --step 1
python scripts/challenge_live.py --natural --step 2
python scripts/challenge_live.py --natural --step 3
# Khởi động lại ứng dụng, hoặc đóng process và mở process mới.
python scripts/challenge_live.py --natural --step 4
python scripts/challenge_live.py --natural --step 5
```

Chỉ chạy trên namespace/user demo mới nếu cần đạt tiêu chí session mới hoàn toàn.
Mỗi lệnh khởi tạo runtime trong process Python riêng; report lưu PID để đối chiếu.
Các trace của một session thể hiện lượt chat gần nhất trong session đó.
