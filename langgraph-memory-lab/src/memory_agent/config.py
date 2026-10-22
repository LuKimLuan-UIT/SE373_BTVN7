"""Cấu hình runtime: đọc `.env` và các bậc/tính năng của bài lab.

Bài lab chia làm 3 bậc, bật/tắt bằng biến môi trường trong `.env`:

- Bậc 1 (luôn bật): lịch sử session lưu file Markdown -> nhớ được sau khi restart app.
- Bậc 2 (``MEMORY_LONG_TERM=1``): memory Markdown -> nhớ được quy ước giữa nhiều session.
- Bậc 3 (``MEMORY_SUMMARIZATION=1``): tóm tắt lịch sử -> session dài không làm vỡ context window.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from . import paths


@dataclass(frozen=True)
class Settings:
    """Toàn bộ cấu hình cần cho một lần chạy agent."""

    api_key: str
    model_name: str
    base_url: str | None

    # Định danh người dùng: namespace của memory và profile.
    user_id: str

    # Nơi lưu trạng thái bền vững (toàn bộ đều là file Markdown).
    memory_dir: str
    sessions_dir: str
    agents_path: str

    # Các bậc tính năng của lab.
    enable_long_term_memory: bool
    enable_summarization: bool

    # Vị trí đặt memory index: "system" (cuối system prompt) hoặc "end" (cuối hội thoại).
    # "end" giữ được prompt cache cho toàn bộ hội thoại (xem README mục prompt caching).
    memory_placement: str

    # Ngưỡng tóm tắt lịch sử (số tin nhắn) và số tin nhắn giữ lại sau khi tóm tắt.
    summarize_trigger_messages: int
    summarize_keep_messages: int

    # Giới hạn số lần gọi model trong một lượt chat.
    model_call_limit: int


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_settings() -> tuple[Settings | None, list[str]]:
    """Đọc `.env`. Trả về ``(settings, [])`` khi đủ cấu hình, ngược lại ``(None, [biến thiếu])``.

    ``override=True``: giá trị trong `.env` luôn thắng biến môi trường đã có.
    Nếu không, lúc `.env` còn trống thì ``OPENAI_API_KEY`` bị set thành ``""``
    trong ``os.environ`` và mọi lần đọc sau đều thấy giá trị rỗng -> app báo
    thiếu cấu hình dù đã điền key.
    """
    load_dotenv(paths.ENV_PATH, override=True)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model_name = os.getenv("MODEL_NAME", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None

    missing = [
        name
        for name, value in (("OPENAI_API_KEY", api_key), ("MODEL_NAME", model_name))
        if not value
    ]
    if missing:
        return None, missing

    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    paths.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    return (
        Settings(
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
            user_id=os.getenv("USER_ID", "default-user").strip() or "default-user",
            memory_dir=str(paths.MEMORY_DIR),
            sessions_dir=str(paths.SESSIONS_DIR),
            agents_path=str(paths.AGENTS_PATH),
            enable_long_term_memory=_flag("MEMORY_LONG_TERM", default=True),
            enable_summarization=_flag("MEMORY_SUMMARIZATION", default=True),
            memory_placement=os.getenv("MEMORY_PLACEMENT", "system").strip().lower() or "system",
            summarize_trigger_messages=_int("MEMORY_SUMMARY_TRIGGER", 12),
            summarize_keep_messages=_int("MEMORY_SUMMARY_KEEP", 6),
            model_call_limit=_int("MODEL_CALL_LIMIT", 8),
        ),
        [],
    )
