"""Đường dẫn gốc của project, resolve từ vị trí file (không phụ thuộc thư mục terminal)."""

from pathlib import Path

# src/memory_agent/paths.py -> src/memory_agent -> src -> <project root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_PATH = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"

# Quy ước của project (luôn nạp vào context, giống AGENTS.md của Claude Code).
AGENTS_PATH = PROJECT_ROOT / "AGENTS.md"

# Thư mục memory: <MEMORY_DIR>/<user_id>/MEMORY.md (index) + <topic>.md (chi tiết).
MEMORY_DIR = DATA_DIR / "memory"

# Lịch sử hội thoại: 1 file Markdown cho mỗi session.
SESSIONS_DIR = DATA_DIR / "sessions"
