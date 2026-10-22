"""Dựng agent: model + middleware + memory.

Ba thứ ghép lại:

- **memory** (Markdown): lưu quy ước/quy tắc xuyên session -> trí nhớ dài hạn.
- **middleware**: nạp AGENTS.md + index MEMORY.md vào context, tóm tắt lịch sử dài,
  chặn vòng lặp model vô hạn.
- **lịch sử session**: file Markdown, nạp lại vào mỗi lượt (xem `memory/history.py`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, before_model, dynamic_prompt
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from .config import Settings
from .memory.lifecycle import MemoryManager
from .memory_tools import build_memory_tools
from .prompts import build_context, build_memory_digest


def build_model(settings: Settings) -> ChatOpenAI:
    """Tạo model từ cấu hình (OpenAI-compatible endpoint)."""
    kwargs: dict[str, Any] = {
        "model": settings.model_name,
        "api_key": settings.api_key,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return ChatOpenAI(**kwargs)


def read_agents_file(path: str | Path) -> str:
    """Đọc AGENTS.md (quy ước project). Trả chuỗi rỗng nếu file không tồn tại."""
    file = Path(path)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def build_middleware(settings: Settings, model: ChatOpenAI) -> list:
    """Danh sách middleware, theo đúng thứ tự áp dụng.

    - ``SummarizationMiddleware`` phải chạy TRƯỚC ``ModelCallLimitMiddleware``
      trong danh sách để lịch sử được gọn trước khi đếm số lần gọi model.
    """
    middleware: list = []
    if settings.enable_summarization:
        from langchain.agents.middleware import SummarizationMiddleware

        middleware.append(
            SummarizationMiddleware(
                model=model,
                trigger=("messages", settings.summarize_trigger_messages),
                keep=("messages", settings.summarize_keep_messages),
            )
        )
    middleware.append(
        ModelCallLimitMiddleware(run_limit=settings.model_call_limit, exit_behavior="end")
    )
    return middleware


def build_agent(
    model: ChatOpenAI,
    settings: Settings,
    *,
    manager: MemoryManager | None = None,
):
    """Tạo agent đã gắn memory theo cấu hình của lab.

    Vị trí đặt memory (ảnh hưởng tới prompt caching):

    - ``system`` (mặc định): index memory nằm cuối system prompt.
      Khi index đổi, phần hội thoại phía sau cũng phải xử lý lại.
    - ``end``: index memory thành **message cuối cùng** của lượt gọi model.
      Nhờ đó prefix (system prompt + toàn bộ hội thoại) luôn được cache;
      chỉ digest + lượt mới bị xử lý lại khi memory đổi.
    """
    use_memory = settings.enable_long_term_memory and manager is not None
    tools = build_memory_tools(manager) if use_memory else []
    agents_text = read_agents_file(settings.agents_path)
    at_end = settings.memory_placement == "end"

    @dynamic_prompt
    def system_prompt(request) -> str:
        index = manager.index_text() if use_memory and manager and not at_end else ""
        return build_context(
            long_term_memory=use_memory,
            summarization=settings.enable_summarization,
            agents_text=agents_text,
            memory_index=index,
        )

    middleware: list = [system_prompt]

    if use_memory and at_end:

        @before_model
        def inject_memory_digest(state, runtime) -> dict[str, Any] | None:
            """Đính digest memory (index) vào CUỐI hội thoại để giữ prompt cache."""
            digest = build_memory_digest(manager.index_text())
            messages = state.get("messages", [])
            if messages:
                last = messages[-1]
                if isinstance(last, SystemMessage) and str(last.content) == digest:
                    return None  # đã có digest ở lượt gọi model trước
            return {"messages": [SystemMessage(content=digest)]}

        middleware.append(inject_memory_digest)

    middleware.extend(build_middleware(settings, model))

    return create_agent(
        model=model,
        tools=tools,
        middleware=middleware,
    )
