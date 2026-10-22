"""Tool trí nhớ dài hạn cho agent: ghi, đọc, sửa, thay thế, quên.

Tool được tạo bằng factory để bind sẵn ``MemoryManager`` — không phụ thuộc cơ chế
inject runtime của LangChain nên tương thích nhiều phiên bản.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from .memory.lifecycle import MemoryConflictError, MemoryManager


def _format_entries(entries: list[Any]) -> str:
    if not entries:
        return "Chưa có mục memory nào."
    lines = []
    for entry in entries:
        mark = "" if entry.status == "active" else f" [đã bị thay thế bởi {entry.superseded_by}]"
        lines.append(f"- ({entry.topic}) {entry.content} — key={entry.key}{mark}")
    return "\n".join(lines)


def build_memory_tools(manager: MemoryManager) -> list:
    """Trả về bộ tool trí nhớ dài hạn đã bind ``manager``."""

    @tool
    def remember(topic: str, content: str, supersedes: str | None = None, force: bool = False) -> str:
        """Ghi một mục memory mới vào một chủ đề (topic).

        Args:
            topic: Chủ đề, ví dụ "preferences", "conventions", "project".
            content: Nội dung mục memory, tự chứa và đủ ngắn gọn.
            supersedes: (tuỳ chọn) key của mục cũ bị thay thế bởi mục này.
            force: (tuỳ chọn) ghi kèm khi biết chắc mục mới khác hẳn mục cũ.
        """
        try:
            result = manager.remember(
                topic, content, supersedes=supersedes, force=force
            )
        except MemoryConflictError as exc:
            lines = [f"- (key={c.key}) {c.content}" for c in exc.conflicts]
            return (
                "CHƯA GHI ĐƯỢC: nội dung này có thể THAY THẾ mục đang hiệu lực trong "
                f"topic '{topic}'. Hãy chọn 1 trong 2:\n"
                "1) mục mới thay thế mục cũ → gọi tool `supersede(key=<key cũ>, content=<nội dung mới>)`\n"
                "2) hai mục thực sự khác nhau → gọi lại `remember` với `force=true`\n"
                "Các mục có thể xung đột:\n" + "\n".join(lines)
            )
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho model xử lý
            return f"Không ghi được memory: {exc}"

        message = f"Đã ghi memory [{result['topic']}] key={result['key']}: {content}"
        conflicts = result.get("conflicts") or []
        if conflicts and not supersedes:
            lines = [f"- (key={c['key']}) {c['content']}" for c in conflicts]
            message += (
                "\n\nLƯU Ý: đã ghi kèm vì có mục gần giống trong cùng topic. "
                "Nếu mục mới thực ra thay thế mục cũ, hãy dùng tool `supersede` để "
                "đánh dấu mục cũ là superseded.\n" + "\n".join(lines)
            )
        return message

    @tool
    def recall(topic: str | None = None) -> str:
        """Đọc chi tiết các mục memory (chỉ nạp khi thật cần).

        Args:
            topic: (tuỳ chọn) chủ đề cần đọc; bỏ trống để xem tất cả.
        """
        try:
            entries = manager.entries(topic=topic)
        except Exception as exc:  # noqa: BLE001
            return f"Không đọc được memory: {exc}"
        header = f"Memory đã lưu{' cho topic ' + topic if topic else ''}:"
        return header + "\n" + _format_entries(entries)

    @tool
    def update(key: str, content: str) -> str:
        """Sửa nội dung của một mục memory đã có (giữ nguyên thời điểm tạo).

        Args:
            key: Key của mục cần sửa (lấy từ kết quả recall).
            content: Nội dung mới.
        """
        try:
            entry = manager.update(key, content)
        except KeyError:
            return f"Không tìm thấy mục memory key={key}."
        except Exception as exc:  # noqa: BLE001
            return f"Không sửa được memory: {exc}"
        return f"Đã sửa memory key={entry.key}: {entry.content}"

    @tool
    def supersede(key: str, content: str) -> str:
        """Thay thế một mục memory cũ bằng nội dung mới (mục cũ được đánh dấu đã bị thay thế).

        Dùng khi quy ước thay đổi: mục cũ không bị xoá, vẫn giữ nguồn và thời điểm.

        Args:
            key: Key của mục cũ.
            content: Nội dung mới thay thế.
        """
        try:
            result = manager.supersede(key, content)
        except KeyError:
            return f"Không tìm thấy mục memory key={key}."
        except Exception as exc:  # noqa: BLE001
            return f"Không thay thế được memory: {exc}"
        return (
            f"Đã thay thế mục cũ key={key} bằng mục mới key={result['key']} "
            f"(mục cũ được đánh dấu superseded, vẫn truy vết được)."
        )

    @tool
    def forget(key: str) -> str:
        """Quên một mục memory: xoá hẳn (dùng khi thông tin sai hoặc không còn đúng).

        Args:
            key: Key của mục cần xoá.
        """
        try:
            deleted = manager.forget(key)
        except Exception as exc:  # noqa: BLE001
            return f"Không xoá được memory: {exc}"
        return f"Đã quên mục memory key={key}." if deleted else f"Không tìm thấy mục memory key={key}."

    return [remember, recall, update, supersede, forget]
