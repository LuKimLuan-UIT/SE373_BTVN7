"""Chatbot LangGraph với trí nhớ persistent nhiều session (lưu bằng file Markdown).

Các module chính:
- ``config``: đọc .env, bật/tắt các bậc tính năng của lab.
- ``graph``: dựng agent (model + middleware + memory).
- ``memory.store``: lưu long-term memory dạng Markdown (index + file chi tiết).
- ``memory.lifecycle``: vòng đời memory (ghi/đọc/sửa/thay thế/quên) và xử lý xung đột.
- ``memory.history``: lịch sử hội thoại của từng session (file Markdown).
- ``sessions``: liệt kê / đặt tên / xoá session.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
