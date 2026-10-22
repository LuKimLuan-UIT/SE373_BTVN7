"""Lịch sử hội thoại của session, lưu dạng Markdown (đọc/sửa tay được).

Mỗi session = 1 file ``data/sessions/<thread_id>.md``:

    # Session `s1`

    - Cập nhật: 2026-10-22T09:00:00+00:00
    - Tiêu đề: Dự án này dùng JWT để đăng nhập

    ## User

    Dự án này dùng JWT để đăng nhập

    ## Assistant

    Đã nhớ quy ước đăng nhập dùng JWT.

Hai chiều: ghi (`write_history`) và đọc lại (`load_history`) — đọc lại để agent
tiếp tục hội thoại sau khi app restart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

TITLE_PREFIX = "- Tiêu đề: "
UPDATED_PREFIX = "- Cập nhật: "

ROLE_LABELS = {"human": "User", "ai": "Assistant"}
LABEL_ROLES = {value: key for key, value in ROLE_LABELS.items()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def transcript_path(sessions_dir: str | Path, thread_id: str) -> Path:
    """Đường dẫn file lịch sử của 1 session."""
    return Path(sessions_dir) / f"{thread_id}.md"


def write_history(
    sessions_dir: str | Path,
    thread_id: str,
    messages: Iterable[Any],
    *,
    title: str | None = None,
) -> Path:
    """Ghi lịch sử session ra ``<sessions_dir>/<thread_id>.md``."""
    directory = Path(sessions_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = transcript_path(directory, thread_id)

    lines = [
        f"# Session `{thread_id}`",
        "",
        f"{UPDATED_PREFIX}{_now()}",
    ]
    if title:
        lines.append(f"{TITLE_PREFIX}{title}")
    lines.append("")

    for message in messages:
        role = getattr(message, "type", "unknown")
        if role not in ROLE_LABELS:
            continue  # bỏ qua message tool/system
        content = str(getattr(message, "content", "")).strip()
        if not content:
            continue
        lines.append(f"## {ROLE_LABELS[role]}")
        lines.append("")
        lines.append(content)
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def load_history(sessions_dir: str | Path, thread_id: str) -> list[BaseMessage]:
    """Đọc lại lịch sử session dưới dạng message của LangChain."""
    path = transcript_path(sessions_dir, thread_id)
    if not path.exists():
        return []

    messages: list[BaseMessage] = []
    role: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if role and buffer:
            content = "\n".join(buffer).strip()
            if content:
                messages.append(HumanMessage(content=content) if role == "human" else AIMessage(content=content))

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            flush()
            buffer = []
            role = LABEL_ROLES.get(line[3:].strip())
            continue
        if role:
            buffer.append(line)
    flush()
    return messages


def read_title(path: str | Path) -> str:
    """Đọc tiêu đề trong file lịch sử (rỗng nếu không có)."""
    file = Path(path)
    if not file.exists():
        return ""
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.startswith(TITLE_PREFIX):
            return line[len(TITLE_PREFIX) :].strip()
    return ""


def set_title(sessions_dir: str | Path, thread_id: str, title: str) -> Path:
    """Đổi tiêu đề của một session (tạo file nếu chưa có)."""
    path = transcript_path(sessions_dir, thread_id)
    if not path.exists():
        path.write_text(f"# Session `{thread_id}`\n\n{TITLE_PREFIX}{title}\n", encoding="utf-8")
        return path

    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(TITLE_PREFIX):
            out.append(f"{TITLE_PREFIX}{title}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.insert(2, f"{TITLE_PREFIX}{title}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return path
