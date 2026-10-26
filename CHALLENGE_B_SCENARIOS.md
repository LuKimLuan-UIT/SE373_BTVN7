# Kịch bản trình diễn Challenge B

Mở `http://127.0.0.1:8000/challenge-b`. Chọn **Offline · 0 API** ở góc trên.
Đây là chế độ mặc định; không cần API key, không khởi tạo/gọi provider. Thanh
context vẫn đo kích thước context ước lượng để quan sát. Usage/API calls phải bằng 0.

## 1. B1 - Phiên dài, cảnh báo và compact

1. Bấm **＋ Phiên mẫu**. Đây là fixture chứa 1.600 dòng debug lặp, không đọc dữ liệu cá nhân.
2. Quan sát thanh context tăng và cảnh báo xuất hiện. Ngưỡng demo mặc định 8.000,
   cảnh báo từ 80%; đó không phải context limit của model.
3. Bấm **Compact ngay** hoặc **◫ Compact**.
4. Mở **Checkpoint sau compact** trong chat để đối chiếu.

Kết quả cần kiểm tra:

- Context sau nhỏ hơn trước; chat hiện số working tokens trước/sau và phần trăm giảm.
- Có lỗi 401 chưa sửa; constraint giữ API `/refresh`, không log token.
- Có lần thử tăng timeout 30s không hiệu quả.
- Có nguồn `auth.py:184` / `race.log:7` và đường dẫn `tests/test_refresh.py`.
- Archive gốc giữ nguyên; usage vẫn **0 input, 0 output, 0 lượt API**.

Offline compact trích xuất theo schema, nguồn có vị trí và marker “Tiếp theo”.
Không dùng LLM để suy ra hay viết lại kế hoạch. User/system instructions và kế
hoạch AI ngắn được giữ nguyên; đây không phải thuật toán hiểu ngữ nghĩa tổng quát.

## 2. B1 - Tiếp tục đúng bước và không lặp cách thất bại

Tiếp tục ngay đoạn chat của kịch bản 1, gửi:

```text
Tiếp tục: nêu bước kế tiếp, constraints và cách đã thử không hiệu quả.
```

Đáp án mong đợi:

- Thêm test hai request refresh đồng thời trong `tests/test_refresh.py`, rồi kiểm tra session lock.
- Giữ `/refresh`; không log token.
- Nhắc timeout 30s không hiệu quả, không đề nghị thử lại như phương án mới.

Phản hồi được ghi rõ **Offline · đọc checkpoint/trích dẫn**. Đây là kiểm tra việc
khôi phục trạng thái, không phải AI thực thi test hay sửa một file có thật.
Reload trang: đoạn chat, usage và checkpoint còn. Tạo chat mới để thử riêng;
memory/session của Challenge A không thay đổi.

## 3. B2 - Đếm nhiều log có đáp án chuẩn

1. Tạo **Đoạn chat mới**, vẫn chọn Offline.
2. Chọn **Phân tích log · B2** hoặc **Câu hỏi log chuẩn** trong menu ⓘ.
3. Bấm gửi câu đã điền:

```text
Quét tất cả file log: loại lỗi nào xuất hiện nhiều nhất, chính xác bao nhiêu lần,
ở những file nào? Đưa bằng chứng file và số dòng.
```

Kết quả chuẩn của fixture 4 log nhân 80:

| Loại lỗi | Count |
|---|---:|
| refresh_timeout | 400 |
| db_connection | 240 |
| invalid_token | 80 |

Lỗi nhiều nhất ở `auth.log`, `billing.log`, `worker.log`. Evidence tiêu biểu:
`auth.log:1`, `billing.log:2`, message `Refresh request timed out`.
Mở **Tool và findings** để xem code template và JSON count/evidence. Phải thấy
4 file, `complete=true`, không có lỗi đọc. 80 dòng không parse được được báo riêng.

Offline dùng template code cố định gọi runtime thật, không giả vờ model đã sinh
code. Raw log không gửi LLM vì chế độ này hoàn toàn không có lời gọi LLM.

## 4. B2 - So context raw output với findings mà không tốn API

1. Ghi lại context sau kịch bản 3; đặt tên đoạn chat qua nội dung/ghi chú khi chụp ảnh.
2. Mở ⓘ → **Baseline riêng**. Ở màn hình rộng có nút **Đối chứng native / raw log**.
3. Baseline tạo một chat riêng, dùng cùng câu hỏi và fixture; raw output nằm trong
   active/archive, còn câu trả lời được code tạo để đối chiếu dữ liệu.
4. So thanh context của hai đoạn chat qua danh sách gần đây.

Raw-output context sẽ lớn hơn findings context. **Cả hai usage đều bằng 0**;
không gọi đây là phần trăm tiết kiệm usage thật. Đây chỉ là đối chứng dung lượng
context giả định. Kết quả model thật đã lưu trong `reports/challenge-b-live/` là
nguồn riêng nếu cần trình bày phần LLM/tool orchestration của đề bài.

## 5. B1 - Compact không có lợi phải từ chối

1. Tạo chat mới ở Offline; gửi `Xin chào`.
2. Bấm Compact.
3. Nếu checkpoint lớn hơn history ngắn, hệ thống báo “Compact không làm context
   nhỏ hơn”, giữ nguyên history/context. Không xoá archive để ép số giảm.

Usage vẫn 0 vì không có model. Khi chọn Provider, compact thất bại vẫn có thể
tốn token; hệ thống ghi usage của request đã thực hiện nếu provider trả đủ dữ liệu.

## 6. Kịch bản provider - tùy chọn, không bắt buộc chạy lại

Chỉ khi muốn và chấp nhận chi phí: chọn **Provider .env** để mở chat riêng rồi
lặp kịch bản 1-3. Không tự chuyển Offline sang Provider khi gặp câu hỏi ngoài
khả năng xử lý. Các lượt kiểm chứng hiện có đã được lưu; sau yêu cầu tiết kiệm
token của người dùng, không gọi provider thêm để kiểm thử giao diện.

## Cách chọn kịch bản để báo cáo

Để trình diễn ngắn: dùng 1 → 2 → 3; thêm 4 để giải thích vì sao Code Mode giảm
context, thêm 5 để chứng minh fail-safe. Chụp cả thanh usage/context và kết quả
trong chat; ghi rõ mode, fixture, đáp án chuẩn, observed result và PASS/FAIL.

Offline chứng minh context/archive, runtime counting và UI không mất chi phí API.
Nó không tự chứng minh model biết sinh code hay tóm tắt đúng mọi trường hợp.
Phần đó có tests graph với model giả và artifact provider thật đã lưu. Lần CLI
B1 đạt; một lần UI provider vẫn lệch thứ tự bước nên phải ghi nhận giới hạn,
không gộp tất cả kết quả thành PASS.

## Kiểm thử tự động không dùng model thật

```powershell
python -m pytest -q --basetemp=data/pytest-b --junitxml=reports/pytest-challenge-b.xml
```

`test_offline_flow_never_builds_or_calls_model_and_needs_no_key` chặn `build_model`
bằng hàm luôn báo lỗi, rồi chạy seed, compact, continuation và đếm log. Nếu có
đường gọi provider ngoài ý muốn thì test thất bại; không chỉ kiểm tra nhãn “Offline”.

## Dọn memory và reset context trên trang B

- **Reset tất cả B**: xác nhận xóa mọi memory dài hạn của B (active và superseded),
  rồi mở chat B mới với chế độ đang chọn, context hiển thị **0 · chưa nạp**.
  Chat/archive cũ vẫn giữ riêng để đối chiếu; không tự nạp lại vào phiên mới.
- **Reset context**: xác nhận bỏ active messages và checkpoint của phiên B hiện tại.
  Giữ memory dài hạn, archive, lịch sử hiển thị và usage đã tiêu thụ; có mốc reset
  ngay trong chat. Tin nhắn trước mốc không nằm trong context lượt tiếp theo.

Hai nút nằm dưới ô nhập trên desktop và mobile, bị khóa khi đang xử lý yêu cầu.
Không gọi model và chỉ tác động namespace B; không xóa dữ liệu Challenge A.
Context vừa reset hiển thị **0 · chưa nạp**. Sau tin đầu hoặc nạp phiên mẫu, thanh
**Context · hiện tại (ước lượng)** đo snapshot hiện tại: instructions, memory index,
tool schemas và active history/checkpoint, gồm cả câu trả lời mới nhất được giữ
trong history. Không gồm archive, tin nhắn đang gõ hay dự đoán nội dung tương lai.
Số đo dùng JSON UTF-8 bytes/4 nên có thể khác tokenizer của provider. System prompt
và công cụ gửi lại ở mỗi request; **Usage · cộng dồn phiên** chỉ ghi nhận các request
đã gọi provider và cộng cả những phần context được gửi nhiều lần.
Để kiểm chứng: nạp phiên dài → Reset tất cả B → kiểm tra 0/chưa nạp → reload vẫn 0
→ gửi tin đầu → kiểm tra thanh context và **Xem context gửi model** (Provider).
Trong Offline, thanh đo chỉ mô phỏng context; usage/API calls vẫn bằng 0.
