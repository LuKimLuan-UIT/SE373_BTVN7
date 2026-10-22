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
- `remember(topic, content, supersedes?)`: ghi một mục vào chủ đề (vd: "preferences", "conventions").
- `recall(topic?)`: đọc chi tiết các mục đã lưu. Chỉ gọi khi thật cần — index đã nạp sẵn.
- `update(key, content)`: sửa nội dung một mục đã có.
- `supersede(key, content)`: thay thế mục cũ (quy ước đã đổi) — mục cũ được đánh dấu
  `superseded` nhưng vẫn giữ nguồn và thời điểm.
- `forget(key)`: quên hẳn một mục sai/lỗi thời.

Cách dùng đúng:
- Người dùng nói ra quy ước/quy tắc quan trọng → chủ động `remember`.
- Người dùng hỏi lại ("quy ước của dự án là gì?") → `recall` trước khi trả lời.
- Khi `remember` báo CẢNH BÁO xung đột: nếu mục mới thay thế mục cũ thì dùng
  `supersede` (hoặc `remember` với `supersedes=<key>`), đừng chỉ append.
- Không lưu câu chào hỏi hay thông tin tức thời.
- Không bịa key: key lấy từ kết quả `recall`."""

SUMMARIZATION_PROMPT = """Lịch sử hội thoại đã được tóm tắt. Hãy dựa vào phần tóm tắt và các tin nhắn gần đây để trả lời."""


def build_system_prompt(*, long_term_memory: bool, summarization: bool) -> str:
    """Ghép prompt theo các tính năng đang bật."""
    parts = [BASE_PROMPT]
    if long_term_memory:
        parts.append(LONG_TERM_PROMPT)
    if summarization:
        parts.append(SUMMARIZATION_PROMPT)
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
    summarization: bool,
    agents_text: str = "",
    memory_index: str = "",
) -> str:
    """Phần context nạp thêm cho mỗi lượt: AGENTS.md + index MEMORY.md.

    - ``AGENTS.md``  : quy ước project — luôn nạp.
    - ``MEMORY.md`` : index ngắn của memory — luôn nạp (chi tiết nạp khi `recall`).
    """
    parts = [build_system_prompt(long_term_memory=long_term_memory, summarization=summarization)]

    if agents_text.strip():
        parts.append("# Quy ước của project (AGENTS.md)\n\n" + agents_text.strip())

    if long_term_memory and memory_index.strip():
        parts.append(
            "# Index memory (MEMORY.md)\n\n"
            "Đây là index ngắn. Chi tiết từng mục nằm ở file theo chủ đề — "
            "khi cần chi tiết, gọi tool `recall`.\n\n" + memory_index.strip()
        )

    return "\n\n".join(parts)
