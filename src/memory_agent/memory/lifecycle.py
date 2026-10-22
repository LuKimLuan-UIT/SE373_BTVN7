"""Chính sách vòng đời của memory: ghi, đọc, sửa, quên — và cách xử lý xung đột.

Theo case study: memory không chỉ "append", phải có chính sách rõ ràng:

- **ghi** (``remember``): thêm mục mới vào một topic.
- **đọc** (``recall``): nạp chi tiết của topic khi thật cần.
- **sửa** (``update``): sửa nội dung mục, giữ nguyên thời điểm tạo.
- **thay thế** (``supersede``): khi quy ước thay đổi — mục cũ được đánh dấu
  ``superseded`` (giữ nguồn + thời điểm), mục mới ghi nhận ``supersedes``.
- **quên** (``forget``): xoá hẳn mục sai/lỗi thời.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .store import MarkdownMemoryStore

ACTIVE = "active"
SUPERSEDED = "superseded"


@dataclass(frozen=True)
class MemoryEntry:
    """Một mục memory đã đọc từ store."""

    key: str
    topic: str
    content: str
    source: str
    status: str
    created_at: str
    updated_at: str
    superseded_by: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "topic": self.topic,
            "content": self.content,
            "source": self.source,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "superseded_by": self.superseded_by,
        }


def _keywords(text: str) -> set[str]:
    """Từ khoá đơn giản để so trùng nội dung (tiếng Việt không dấu)."""
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    return {w for w in normalized.split() if len(w) > 2}


def make_key(topic: str, content: str) -> str:
    """Key ổn định theo topic + nội dung (giống nhau thì không tạo bản trùng)."""
    digest = hashlib.sha1(f"{topic}::{content.strip().lower()}".encode("utf-8")).hexdigest()[:8]
    return f"fact-{digest}"


class MemoryManager:
    """Lớp nghiệp vụ cho vòng đời memory, đặt trên store Markdown."""

    def __init__(self, store: MarkdownMemoryStore, user_id: str) -> None:
        self.store = store
        self.user_id = user_id
        # Session hiện tại — dùng làm nguồn mặc định cho mục memory ghi ra.
        self.current_source: str = ""

    # ------------------------------------------------------------------ read
    def entries(self, topic: str | None = None, include_superseded: bool = True) -> list[MemoryEntry]:
        """Đọc các mục memory (mặc định mọi topic)."""
        namespace = ("memory", self.user_id) if topic is None else ("memory", self.user_id, topic)
        items = self.store.search(namespace, limit=1000)
        result = []
        for item in items:
            value = item.value
            status = value.get("status", ACTIVE)
            if not include_superseded and status != ACTIVE:
                continue
            result.append(
                MemoryEntry(
                    key=item.key,
                    topic=item.namespace[-1] if len(item.namespace) > 2 else "misc",
                    content=value.get("content", ""),
                    source=value.get("source", ""),
                    status=status,
                    created_at=value.get("created_at", ""),
                    updated_at=value.get("updated_at", ""),
                    superseded_by=value.get("superseded_by", ""),
                )
            )
        return result

    def find(self, key: str) -> MemoryEntry | None:
        """Tìm một mục theo key (bất kỳ topic nào)."""
        for entry in self.entries():
            if entry.key == key:
                return entry
        return None

    def index_text(self) -> str:
        """Index MEMORY.md — phần luôn nạp vào context."""
        return self.store.index_text()

    # ----------------------------------------------------------------- write
    def remember(
        self,
        topic: str,
        content: str,
        *,
        source: str = "",
        supersedes: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Ghi một mục memory mới.

        Nếu trong cùng topic đã có mục **đang hiệu lực** có nội dung gần giống, mục cũ
        được **supersede trước** (đánh dấu ``superseded``, giữ nguồn + thời điểm),
        sau đó mới ghi mục mới. Nhờ vậy không bao giờ có hai mục mâu thuẫn cùng hiệu lực.

        Args:
            topic: chủ đề của mục memory.
            content: nội dung mục memory.
            source: nguồn (mặc định là session hiện tại).
            supersedes: key của mục cũ bị thay thế (ngoài các mục tự phát hiện).
            force: giữ cả mục cũ và mục mới (khi thật sự là hai quyết định khác nhau).

        Returns:
            dict với ``key``, ``topic``, ``superseded`` (danh sách key bị thay thế).
        """
        content = content.strip()
        if not content:
            raise ValueError("Nội dung memory rỗng.")

        key = make_key(topic, content)
        namespace = ("memory", self.user_id, topic)

        # 1. supersede mục cũ trước (mục tự phát hiện trùng chủ đề + mục được chỉ định).
        superseded: list[str] = []
        if not force:
            for conflict in self.find_conflicts(topic, content, exclude_key=key):
                self._mark_superseded(conflict.key, new_key=key)
                superseded.append(conflict.key)
        if supersedes and supersedes not in superseded:
            self._mark_superseded(supersedes, new_key=key)
            superseded.append(supersedes)

        # 2. rồi mới ghi mục mới.
        self.store.put(
            namespace,
            key,
            {
                "content": content,
                "topic": topic,
                "source": source or self.current_source,
                "status": ACTIVE,
            },
        )

        return {
            "key": key,
            "topic": topic,
            "superseded": superseded,
        }

    def find_conflicts(self, topic: str, content: str, *, exclude_key: str = "") -> list[MemoryEntry]:
        """Tìm các mục đang hiệu lực trong cùng topic có nội dung gần giống.

        Đây là "cảnh báo xung đột": agent nên gọi ``supersede`` thay vì append.
        """
        words = _keywords(content)
        if not words:
            return []
        conflicts = []
        for entry in self.entries(topic=topic, include_superseded=False):
            if entry.key == exclude_key:
                continue
            other = _keywords(entry.content)
            if not other:
                continue
            overlap = len(words & other) / max(len(words | other), 1)
            if overlap >= 0.4:
                conflicts.append(entry)
        return conflicts

    def update(self, key: str, content: str) -> MemoryEntry:
        """Sửa nội dung một mục (giữ nguyên ``created_at`` và ``source``)."""
        entry = self.find(key)
        if entry is None:
            raise KeyError(f"Không tìm thấy mục memory: {key}")
        content = content.strip()
        self.store.put(
            ("memory", self.user_id, entry.topic),
            key,
            {
                "content": content,
                "topic": entry.topic,
                "source": entry.source,
                "status": entry.status,
            },
        )
        updated = self.find(key)
        assert updated is not None
        return updated

    def supersede(self, key: str, content: str, *, source: str = "") -> dict[str, Any]:
        """Thay thế một mục cũ bằng nội dung mới.

        Mục cũ **không bị xoá**: được đánh dấu ``superseded`` và trỏ sang mục mới,
        giữ lại nguồn + thời điểm để truy vết.
        """
        entry = self.find(key)
        if entry is None:
            raise KeyError(f"Không tìm thấy mục memory: {key}")
        result = self.remember(entry.topic, content, source=source or entry.source, supersedes=key)
        return result

    def forget(self, key: str) -> bool:
        """Quên một mục (xoá hẳn). Trả về True nếu đã xoá."""
        entry = self.find(key)
        if entry is None:
            return False
        self.store.delete(("memory", self.user_id, entry.topic), key)
        return True

    # ---------------------------------------------------------------- helper
    def _mark_superseded(self, key: str, *, new_key: str) -> None:
        entry = self.find(key)
        if entry is None:
            return
        self.store.put(
            ("memory", self.user_id, entry.topic),
            key,
            {
                "content": entry.content,
                "topic": entry.topic,
                "source": entry.source,
                "status": SUPERSEDED,
                "superseded_by": new_key,
                "superseded_at": _now_iso(),
            },
        )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
