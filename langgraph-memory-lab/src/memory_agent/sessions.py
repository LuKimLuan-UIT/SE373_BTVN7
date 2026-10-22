"""Quản lý session: mỗi session = 1 file Markdown trong ``data/sessions``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .memory.history import read_title, set_title, transcript_path


@dataclass(frozen=True)
class SessionInfo:
    """Thông tin hiển thị cho 1 session trong sidebar UI."""

    thread_id: str
    title: str
    updated_at: str
    path: str


def list_sessions(sessions_dir: str | Path) -> list[SessionInfo]:
    """Liệt kê session (mỗi file .md là 1 session), mới nhất trước."""
    directory = Path(sessions_dir)
    if not directory.exists():
        return []

    sessions: list[SessionInfo] = []
    for path in sorted(directory.glob("*.md")):
        updated = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- Cập nhật:"):
                updated = line.split(":", 1)[1].strip()
        sessions.append(
            SessionInfo(
                thread_id=path.stem,
                title=read_title(path) or path.stem,
                updated_at=updated,
                path=str(path),
            )
        )
    sessions.sort(key=lambda s: s.updated_at, reverse=True)
    return sessions


def rename_session(sessions_dir: str | Path, thread_id: str, title: str) -> Path:
    """Đặt lại tiêu đề cho session."""
    return set_title(sessions_dir, thread_id, title)


def delete_session(sessions_dir: str | Path, thread_id: str) -> None:
    """Xoá hẳn một session (xoá file lịch sử)."""
    path = transcript_path(sessions_dir, thread_id)
    if path.exists():
        path.unlink()
