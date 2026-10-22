"""System prompt của agent + phần context nạp kèm (AGENTS.md, MEMORY.md index).

Nguyên tắc của case study: **index luôn nạp, chi tiết nạp khi cần** — không nhồi
toàn bộ memory vào mỗi lượt để tránh context bloat.
"""

from __future__ import annotations

BASE_PROMPT = """Bạn là trợ lý trong lab "LangGraph Persistent Memory". Trả lời bằng tiếng Việt, ngắn gọn, rõ ràng.

Quy tắc chung:
- Chỉ nói bạn đã ghi/đọc/xoá memory khi đã gọi tool tương ứng và nhận kết quả thành công.
- Khi tool báo lỗi, nói rõ lỗi cho người dùng, không bịa kết quả.
- Khi người dùng hỏi về thông tin đã lưu ở phiên trước, hãy dùng tool `recall` thay vì đoán."""

LONG_TERM_PROMPT = """Bạn có bộ công cụ trí nhớ dài hạn (lưu trong file Markdown):
- `remember(topic, content, supersedes?, force?)`: ghi một mục vào chủ đề (vd: "preferences", "project").
- `recall(topic?)`: đọc chi tiết các mục đã lưu. Chỉ gọi khi thật cần — index đã nạp sẵn.
- `update(key, content)`: sửa nội dung một mục đã có.
- `supersede(key, content)`: thay thế mục cũ (quy ước đã đổi) — mục cũ được đánh dấu
  `superseded` nhưng vẫn giữ nguồn và thời điểm.
- `forget(key)`: quên hẳn một mục sai/lỗi thời.

Cách dùng đúng:
- Hiểu ý nghĩa hội thoại để đề xuất memory bền vững: quyết định đã thống nhất,
  quy ước dự án, sở thích ổn định. Không cần người dùng nói "nhớ" hay "lưu".
- Phân biệt sự kiện đã chốt với giả định, câu hỏi, trích dẫn và đề xuất đang cân nhắc.
  Nếu chưa rõ quyết định đã được chấp thuận, hỏi lại thay vì ghi như sự thật.
- Người dùng hỏi lại ("quy ước của dự án là gì?") → `recall` trước khi trả lời.
- Model đề xuất thao tác; harness kiểm tra dữ liệu, namespace, key và trạng thái.
  Harness không suy ngữ nghĩa bằng từ khóa và không bảo đảm model luôn hiểu đúng.
- Trước khi ghi, đối chiếu index/recall. Khi quy ước đổi, dùng `supersede(key, content)`
  hoặc `remember(..., supersedes=key)` để chỉ rõ quyết định bị thay thế.
  Không tự ghi thêm mục mâu thuẫn; cùng topic có thể chứa nhiều quyết định độc lập.
- Nội dung ngắn gọn, tự chứa, chỉ mô tả quy ước hiện hành; tránh lặp thông tin cũ.
- Không lưu câu chào hỏi hay thông tin tức thời.
- Không lưu mật khẩu, API key hoặc credential. Yêu cầu lưu rõ ràng của người dùng
  phải được xem xét theo cùng chính sách, không tự động coi mọi yêu cầu là hợp lệ.
- Không bịa key: key lấy từ kết quả `recall` hoặc từ thông báo của `remember`."""




def build_system_prompt(*, long_term_memory: bool) -> str:
    """Ghép prompt theo các tính năng đang bật."""
    parts = [BASE_PROMPT]
    if long_term_memory:
        parts.append(LONG_TERM_PROMPT)
    return "\n\n".join(parts)


def build_memory_digest(memory_index: str) -> str:
    """Digest memory dạng ngắn, dùng khi đặt ở cuối hội thoại (chế độ ``end``)."""
    return (
        "[Memory index — luôn cập nhật, dùng để trả lời đúng quy ước đã lưu. "
        "Chi tiết từng mục: gọi tool `recall(topic)`.]\n"
        + memory_index.strip()
    )


def build_context(
    *,
    long_term_memory: bool,
    agents_text: str = "",
    memory_index: str = "",
) -> str:
    """Phần context nạp thêm cho mỗi lượt: AGENTS.md + index MEMORY.md.

    - ``AGENTS.md``  : quy ước project — luôn nạp.
    - ``MEMORY.md`` : index ngắn của memory — luôn nạp (chi tiết nạp khi `recall`).
    """
    parts = [build_system_prompt(long_term_memory=long_term_memory)]

    if agents_text.strip():
        parts.append("# Quy ước của project (AGENTS.md)\n\n" + agents_text.strip())

    if long_term_memory and memory_index.strip():
        parts.append(
            "# Index memory (MEMORY.md)\n\n"
            "Đây là index ngắn. Chi tiết từng mục nằm ở file theo chủ đề — "
            "khi cần chi tiết, gọi tool `recall`.\n\n" + memory_index.strip()
        )

    return "\n\n".join(parts)
