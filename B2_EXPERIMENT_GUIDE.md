# B2: thử nghiệm 10.000 dòng log giả

## Các khái niệm trên giao diện

| Mục | Ý nghĩa |
|---|---|
| Log | Các dòng ghi lại sự kiện, gồm thời gian, mức độ, loại sự kiện và nội dung. Bộ thử này hoàn toàn giả lập. |
| Tool / công cụ | Hàm agent gọi để lấy hoặc xử lý dữ liệu, ví dụ `run_code`. |
| Findings | Kết quả tổng hợp mà tool trả về: count, tên file, số dòng và một vài đoạn bằng chứng. |
| Code Mode | Agent gọi `run_code`; backend đọc và đếm log, chỉ gửi findings cho model trả lời. |
| Native / raw baseline | Agent gọi `read_all_logs`; tool trả nguyên log cho model phân tích. Đây là phương pháp đối chứng. |
| Usage | Token thực tế provider báo cho các lượt model đã chạy. |
| Context | Ước lượng lượng thông tin trong request tiếp theo; khác với tổng usage. |

## Dữ liệu và thuật toán

Bộ `synthetic-10000-v1` có 4 file, mỗi file 2.500 dòng: auth.log, billing.log,
worker.log và irrelevant.log. Có 3.000 lỗi refresh_timeout, 1.800 db_connection,
600 invalid_token; 4.600 dòng còn lại là INFO/WARN. Timestamp và request_id được
sinh cố định để có thể chạy lại. Cả Code Mode và native đọc cùng thư mục log.

Trong Code Mode, agent sinh các lời gọi API được cấp:

```python
rows = read_logs()
errors = select(rows, level="ERROR")
result = summarize(errors, top=5)
```

Runtime chạy ở backend Python của ứng dụng. Runtime đọc file, lọc mức ERROR,
đếm theo error_type, xếp theo số lần giảm dần và chọn vài dòng bằng chứng.
Biến trung gian không trả về model; chỉ `result` được chuyển thành JSON findings.
Tool chỉ nhận một tập lệnh giới hạn, không chạy Python/shell tùy ý.

Đây là thuật toán xử lý dữ liệu của B2. Hai chế độ Compact/Truncation thuộc B1;
không cần bấm Compact trong phép đo B2.

## Thao tác và ảnh báo cáo

1. Tải lại trang B, chọn Provider, tạo chat mới. Bấm Phân tích log · B2 và gửi câu
   hỏi đã điền. Chụp câu hỏi, câu trả lời, nhãn 10.000 dòng và Usage.
2. Mở Tool và findings: chụp `run_code`, code và JSON có `files_scanned=4`,
   `lines_scanned=10000`, `complete=true`, count và bằng chứng file/dòng.
3. Mở Xem context gửi model, kiểm tra tool result chỉ là findings, không có toàn
   bộ raw log. Chụp phần request minh họa.
4. Mở ⓘ → Baseline riêng · raw log. Chat đối chứng dùng cùng câu hỏi và bộ log.
   Chụp câu trả lời và tổng Usage. Không hỏi thêm hoặc compact giữa phép đo.

So tổng input token của tất cả request trong từng chat Provider mới. Mức giảm:
`(input_native - input_code) / input_native * 100%`. Chỉ tính khi có usage đầy đủ
và baseline > 0; không thay usage bằng Context hoặc số 0 khi provider không báo.
Đối chiếu độ đúng của cả hai câu trả lời; nếu native bị từ chối vì input quá dài
hoặc không đếm đúng, ghi nhận kết quả đó. Offline không gọi model, usage bằng 0,
chỉ kiểm tra luồng code và dung lượng, không đo tiết kiệm usage provider.

Code Mode có thể vẫn dùng ít token dù log tăng lên 10.000 dòng vì findings vẫn
ngắn. Số 400/240/80 và các ảnh cũ thuộc bộ dữ liệu trước, không dùng cho lần đo mới.
