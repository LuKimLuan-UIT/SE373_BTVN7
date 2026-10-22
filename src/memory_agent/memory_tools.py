"""Tool trí nhớ dài hạn cho agent: ghi, đọc, sửa, thay thế, quên.

Tool được tạo bằng factory để bind sẵn ``MemoryManager`` — không phụ thuộc cơ chế
inject runtime của LangChain nên tương thích nhiều phiên bản.
"""

from __future__ import annotations

from typing import Any
import re

from langchain_core.tools import tool

from .memory.lifecycle import MemoryManager


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

    def review(topic: str, content: str, key: str | None = None):
        """Harness kiểm tra cấu trúc và đích ghi; model chịu trách nhiệm ngữ nghĩa."""
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", topic):
            raise ValueError("Topic phải là slug chữ thường, ví dụ project hoặc preferences.")
        if not content.strip():
            raise ValueError("Nội dung memory rỗng.")
        if key:
            entry = manager.find(key)
            if entry is None:
                raise KeyError(key)
            if not entry.is_active or entry.topic != topic:
                raise ValueError("Harness từ chối: key phải còn active và thuộc đúng topic của user.")
            if content.strip().casefold() == entry.content.strip().casefold():
                raise ValueError("Nội dung không đổi; không cần thay thế chính mục đó.")

    @tool
    def remember(topic: str, content: str, supersedes: str | None = None, force: bool = False) -> str:
        """Ghi một mục memory mới vào một chủ đề (topic).

        Model quyết định điều gì đáng nhớ theo ý nghĩa, không dựa vào từ khóa.
        Nếu thay đổi một quyết định cũ, phải cung cấp supersedes từ recall/index.
        Harness kiểm tra nội dung, topic, key và trạng thái trước khi ghi.

        Args:
            topic: Chủ đề, ví dụ "preferences", "project".
            content: Nội dung mục memory, tự chứa và đủ ngắn gọn.
            supersedes: (tuỳ chọn) key của mục cũ bị thay thế.
            force: (tuỳ chọn) ghi kèm, giữ cả mục cũ — dùng khi hai mục là hai
                quyết định khác nhau.
        """
        try:
            review(topic, content, supersedes)
            if force and supersedes:
                raise ValueError("Không dùng force cùng supersedes.")
            result = manager.remember(
                topic, content, supersedes=supersedes, force=True
            )
        except Exception as exc:  # noqa: BLE001 - báo lỗi cho model xử lý
            return f"Không ghi được memory: {exc}"

        message = f"Đã ghi memory [{result['topic']}] key={result['key']}: {content}"
        superseded = result.get("superseded") or []
        if superseded:
            message += (
                "\n\nĐã supersede mục cũ (đánh dấu là superseded, vẫn truy vết được): "
                + ", ".join(superseded)
            )
        return message + "\nHarness: đã kiểm tra nội dung, namespace và key thay thế; không suy xung đột bằng từ khóa."

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
            current = manager.find(key)
            if current is None:
                raise KeyError(key)
            review(current.topic, content)
            if not current.is_active:
                raise ValueError("Harness từ chối sửa mục đã bị thay thế.")
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
            current = manager.find(key)
            if current is None:
                raise KeyError(key)
            review(current.topic, content, key)
            result = manager.supersede(key, content)
        except KeyError:
            return f"Không tìm thấy mục memory key={key}."
        except Exception as exc:  # noqa: BLE001
            return f"Không thay thế được memory: {exc}"
        return (
            f"Đã thay thế mục cũ key={key} bằng mục mới key={result['key']} "
            f"(mục cũ được đánh dấu superseded, vẫn truy vết được). "
            "Harness: đã kiểm tra key còn hiệu lực và giữ nguồn session hiện tại."
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
