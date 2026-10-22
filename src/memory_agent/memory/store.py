"""Store của LangGraph: trí nhớ dài hạn lưu dưới dạng **file Markdown**.

Theo case study "AGENTS.md và MEMORY.md":

- ``MEMORY.md``  = **index ngắn**, luôn được nạp vào context.
- ``<topic>.md`` = **chi tiết** theo chủ đề, chỉ nạp khi agent thật sự cần
  (progressive disclosure) — tránh context bloat.

Cấu trúc thư mục::

    data/memory/<user_id>/
    ├── MEMORY.md          # index: topic + tóm tắt 1 dòng mỗi mục
    ├── preferences.md     # chi tiết chủ đề "preferences"
    └── conventions.md     # chi tiết chủ đề "conventions"

Định dạng 1 file chi tiết::

    # preferences

    ## fact-ab12cd34
    - content: An thích lập trình Python
    - source: session-abc123
    - status: active
    - created_at: 2026-10-22T09:00:00+00:00
    - updated_at: 2026-10-22T09:00:00+00:00

Store implement đầy đủ ``langgraph.store.base.BaseStore`` nên sau này có thể thay
bằng store chính thức (Postgres/Redis) mà không phải sửa agent.
"""

from __future__ import annotations

import asyncio
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from langgraph.store.base import BaseStore, Item, SearchItem

_NOT_PROVIDED = object()

_ITEM_RE = re.compile(r"^##\s+(?P<key>.+?)\s*$")
_FIELD_RE = re.compile(r"^-\s+(?P<field>[A-Za-z0-9_]+):\s*(?P<value>.*)$")

INDEX_HEADER = "# Memory index — {user_id}"
INDEX_NOTE = (
    "> Index ngắn: luôn nạp vào context. Chi tiết nằm ở file theo chủ đề, "
    "chỉ nạp khi agent gọi `recall(topic)`."
)
MAX_SUMMARY_LINES = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_name(name: str) -> str:
    """Tên file an toàn cho topic."""
    slug = re.sub(r"[^a-z0-9\-_]+", "-", name.strip().lower()).strip("-")
    return slug or "misc"


class MarkdownMemoryStore(BaseStore):
    """Store bền vững trên file Markdown: index + file chi tiết theo topic."""

    def __init__(self, root: str | Path, user_id: str = "default-user") -> None:
        self.root = Path(root)
        self.user_id = user_id
        self.user_dir = self.root / user_id
        self.index_path = self.user_dir / "MEMORY.md"
        self._lock = threading.RLock()
        self.user_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text(self._render_index({}), encoding="utf-8")

    # ------------------------------------------------------------------ path
    @staticmethod
    def _split_namespace(namespace: tuple[str, ...], default_user: str) -> tuple[str, str]:
        """Tách namespace -> (user, topic).

        Namespace chuẩn của lab: ``("memory", <user_id>, <topic>)``.
        """
        parts = list(namespace)
        if len(parts) >= 3:
            return parts[1], parts[2]
        if len(parts) == 2:
            return parts[1], "misc"
        if len(parts) == 1:
            return default_user, parts[0]
        return default_user, "misc"

    def _topic_file(self, topic: str, user: str | None = None) -> Path:
        user = user or self.user_id
        return self.root / user / f"{_safe_name(topic)}.md"

    def _namespace(self, topic: str, user: str | None = None) -> tuple[str, ...]:
        return ("memory", user or self.user_id, topic)

    # ---------------------------------------------------------------- parse
    @staticmethod
    def _parse_file(path: Path) -> dict[str, dict[str, Any]]:
        """Đọc 1 file chi tiết -> {key: fields}."""
        entries: dict[str, dict[str, Any]] = {}
        if not path.exists():
            return entries
        key: str | None = None
        item: dict[str, Any] | None = None
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.rstrip()
            item_match = _ITEM_RE.match(line)
            if item_match:
                key = item_match.group("key")
                item = {}
                entries[key] = item
                continue
            field_match = _FIELD_RE.match(line)
            if field_match and item is not None and key is not None:
                item[field_match.group("field")] = field_match.group("value")
        return entries

    @staticmethod
    def _render_file(topic: str, entries: dict[str, dict[str, Any]]) -> str:
        lines = [f"# {topic}", ""]
        for key, fields in entries.items():
            lines.append(f"## {key}")
            for field, value in fields.items():
                text = str(value).replace("\r", " ").replace("\n", " ").strip()
                lines.append(f"- {field}: {text}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    # ---------------------------------------------------------------- index
    def _render_index(self, topics: dict[str, dict[str, dict[str, Any]]], user: str | None = None) -> str:
        """Sinh lại MEMORY.md (index ngắn)."""
        lines = [INDEX_HEADER.format(user_id=user or self.user_id), "", INDEX_NOTE, ""]
        if not topics:
            lines.append("_Chưa có memory nào._")
            return "\n".join(lines).rstrip() + "\n"

        lines.append("| Topic | Số mục hiệu lực | File |")
        lines.append("|---|---|---|")
        for topic, entries in sorted(topics.items()):
            active = [e for e in entries.values() if e.get("status", "active") == "active"]
            file_name = f"{_safe_name(topic)}.md"
            lines.append(f"| {topic} | {len(active)} | [{file_name}]({file_name}) |")
        lines.append("")

        summaries: list[str] = []
        for topic, entries in sorted(topics.items()):
            for key, fields in entries.items():
                if fields.get("status", "active") != "active":
                    continue
                summaries.append(f"- [{topic}] {fields.get('content', '')} (`{key}`)")
        if summaries:
            lines.append("## Mục đang hiệu lực")
            lines.append("")
            lines.extend(summaries[:MAX_SUMMARY_LINES])
            if len(summaries) > MAX_SUMMARY_LINES:
                lines.append(f"- … và {len(summaries) - MAX_SUMMARY_LINES} mục khác (xem file chi tiết)")
        return "\n".join(lines).rstrip() + "\n"

    def refresh_index(self, user: str | None = None) -> None:
        """Dựng lại MEMORY.md từ các file chi tiết."""
        user = user or self.user_id
        with self._lock:
            topics = self._all_topics(user)
            directory = self.root / user
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "MEMORY.md").write_text(self._render_index(topics, user), encoding="utf-8")

    def _all_topics(self, user: str | None = None) -> dict[str, dict[str, dict[str, Any]]]:
        """Đọc tất cả file chi tiết của 1 user -> {topic: {key: fields}}."""
        directory = self.root / (user or self.user_id)
        topics: dict[str, dict[str, dict[str, Any]]] = {}
        if not directory.exists():
            return topics
        for path in sorted(directory.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            topics[path.stem] = self._parse_file(path)
        return topics

    def index_text(self) -> str:
        """Nội dung index (luôn nạp vào context của agent)."""
        with self._lock:
            if self.index_path.exists():
                return self.index_path.read_text(encoding="utf-8")
            self.refresh_index()
            return self.index_path.read_text(encoding="utf-8")

    def clear(self) -> int:
        """Xóa memory của user hiện tại; giữ lịch sử session và user khác."""
        with self._lock:
            directory = self.user_dir.resolve()
            if directory == self.root.resolve() or self.root.resolve() not in directory.parents:
                raise ValueError("Thư mục memory phải nằm trong thư mục gốc của store.")
            files = list(directory.glob("*.md"))
            if any(path.is_symlink() or path.resolve().parent != directory for path in files):
                raise ValueError("Không xóa memory qua liên kết tới thư mục khác.")
            count = sum(len(self._parse_file(path)) for path in files if path.name != "MEMORY.md")
            for path in files:
                if path.name != "MEMORY.md":
                    path.unlink()
            self.refresh_index()
            return count

    # ---------------------------------------------------------- BaseStore API
    def put(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: Mapping[str, Any],
        index: Any = None,
        *,
        ttl: float | None | Any = _NOT_PROVIDED,
    ) -> None:
        """Ghi (namespace, key) -> value trong file của topic tương ứng."""
        user, topic = self._split_namespace(namespace, self.user_id)
        with self._lock:
            path = self._topic_file(topic, user)
            entries = self._parse_file(path)
            previous = entries.get(key, {})
            fields = dict(value)
            fields.setdefault("created_at", previous.get("created_at", _now()))
            fields["updated_at"] = _now()
            entries[key] = fields
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self._render_file(topic, entries), encoding="utf-8")
            self.refresh_index(user)

    def get(self, namespace: tuple[str, ...], key: str, *, refresh_ttl: bool | None = None) -> Item | None:
        """Đọc một item theo namespace + key."""
        user, topic = self._split_namespace(namespace, self.user_id)
        with self._lock:
            entries = self._parse_file(self._topic_file(topic, user))
            fields = entries.get(key)
            if fields is None:
                return None
            return self._to_item(self._namespace(topic, user), key, fields)

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        """Xoá một item theo namespace + key."""
        user, topic = self._split_namespace(namespace, self.user_id)
        with self._lock:
            path = self._topic_file(topic, user)
            entries = self._parse_file(path)
            if key in entries:
                del entries[key]
                path.write_text(self._render_file(topic, entries), encoding="utf-8")
                self.refresh_index(user)

    def search(
        self,
        namespace_prefix: tuple[str, ...],
        /,
        *,
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
        refresh_ttl: bool | None = None,
    ) -> list[SearchItem]:
        """Liệt kê các item dưới namespace (mọi topic con)."""
        with self._lock:
            results: list[SearchItem] = []
            prefix = tuple(namespace_prefix)
            users = self._users_for_prefix(prefix)
            for user in users:
                for topic, entries in self._all_topics(user).items():
                    namespace = self._namespace(topic, user)
                    if namespace[: len(prefix)] != prefix:
                        continue
                    for key, fields in entries.items():
                        if filter and any(str(fields.get(k)) != str(v) for k, v in filter.items()):
                            continue
                        if query and query.lower() not in fields.get("content", "").lower():
                            continue
                        results.append(self._to_item(namespace, key, fields))
            return results[offset : offset + limit]

    def _users_for_prefix(self, prefix: tuple[str, ...]) -> list[str]:
        """Các user cần quét cho một namespace prefix."""
        if len(prefix) >= 2:
            return [prefix[1]]
        if self.root.exists():
            return sorted(p.name for p in self.root.iterdir() if p.is_dir())
        return [self.user_id]

    def list_namespaces(
        self,
        *,
        prefix: Any = None,
        suffix: Any = None,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, ...]]:
        """Liệt kê các namespace đang có."""
        with self._lock:
            namespaces: list[tuple[str, ...]] = []
            for user in self._users_for_prefix(("memory",) if not prefix else tuple(prefix)):
                for topic in self._all_topics(user):
                    namespaces.append(self._namespace(topic, user))
            if prefix:
                namespaces = [ns for ns in namespaces if ns[: len(prefix)] == tuple(prefix)]
            if max_depth is not None:
                namespaces = [ns for ns in namespaces if len(ns) <= max_depth]
            return namespaces[offset : offset + limit]

    def batch(self, ops: Iterable[Any]) -> list[Any]:
        """Chạy nhiều thao tác (put/get/delete/search) trong một lần gọi."""
        results: list[Any] = []
        for op in ops:
            op_type = getattr(op, "op", None) or op[0]
            if op_type == "put":
                _, namespace, key, value = op[:4]
                self.put(tuple(namespace), key, value)
                results.append(None)
            elif op_type == "get":
                _, namespace, key = op[:3]
                results.append(self.get(tuple(namespace), key))
            elif op_type == "delete":
                _, namespace, key = op[:3]
                results.append(None)
            elif op_type == "search":
                _, namespace_prefix = op[:2]
                results.append(self.search(tuple(namespace_prefix), limit=1000))
            else:
                raise ValueError(f"Operation chưa hỗ trợ: {op_type!r}")
        return results

    async def abatch(self, ops: Iterable[Any]) -> list[Any]:
        """Phiên bản async của :meth:`batch`."""
        return await asyncio.to_thread(self.batch, ops)

    # ---------------------------------------------------------------- helper
    @staticmethod
    def _to_item(namespace: tuple[str, ...], key: str, fields: dict[str, Any]) -> SearchItem:
        created = fields.get("created_at")
        updated = fields.get("updated_at")
        return SearchItem(
            namespace=namespace,
            key=key,
            value={k: v for k, v in fields.items() if k not in {"created_at", "updated_at"}},
            created_at=datetime.fromisoformat(created) if created else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(updated) if updated else datetime.now(timezone.utc),
        )
