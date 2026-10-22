# AGENTS.md — quy ước của project

> File này luôn được nạp vào context của agent, giống `AGENTS.md` của Claude Code.
> Agent phải tuân thủ các quy ước dưới đây.

## Quy tắc bắt buộc

- Trả lời bằng tiếng Việt, ngắn gọn và rõ ràng.
- Chỉ khẳng định đã ghi/đọc/xoá memory khi tool trả về thành công.
- Khi tool báo lỗi, nói rõ lỗi và đề xuất cách xử lý; không bịa kết quả.
- Không hard-code model hay credential — đọc từ `config.py`/`.env`.

## Quy ước về memory

- Memory nằm ở `data/memory/<user_id>/`:
  - `MEMORY.md` — index ngắn, luôn nạp vào context.
  - `<topic>.md` — chi tiết theo chủ đề, chỉ nạp khi thật cần (`recall`).
- Khi người dùng nói ra một quy ước/quy tắc quan trọng: ghi bằng `remember`.
- Khi có thông tin mới **thay thế** thông tin cũ: dùng `supersede` (đánh dấu mục cũ
  là `superseded`, giữ lại nguồn và thời điểm) — không xoá lịch sử, không chỉ append.
- `remember` tự so trùng chủ đề: nếu mục mới thay thế mục cũ, mục cũ được supersede
  trước rồi mới ghi mục mới. Dùng `force=true` khi chắc chắn là hai quyết định khác nhau.
- Khi thông tin sai hoặc không còn đúng: dùng `forget`.
- Không ghi những thứ chỉ là câu chào hỏi hoặc thông tin tức thời.

## Quy ước về code

- Mỗi module một trách nhiệm; không import chéo giữa các tầng.
- Test chạy được không cần API key (dùng fake chat model).
- Thêm bài tập mới vào `README.md` mục "Bài tập".
