"""Runtime dùng chung cho UI và CLI: store + manager + agent.

Một chỗ duy nhất để khởi tạo mọi thứ, tránh UI và CLI lệch nhau.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings
from .graph import build_agent, build_model, read_agents_file
from .memory.history import load_history, write_history
from .memory.lifecycle import MemoryManager
from .memory.store import MarkdownMemoryStore
from .prompts import build_context
from .sessions import rename_session


@dataclass
class Runtime:
    """Bundle các thành phần của một lần chạy agent."""

    settings: Settings
    store: MarkdownMemoryStore
    manager: MemoryManager
    agent: Any

    def chat(self, thread_id: str, message: str) -> str:
        """Gửi 1 tin nhắn vào session và trả về câu trả lời.

        Lịch sử được nạp lại từ file Markdown của session (nên nhớ được sau khi
        restart app), rồi lưu lại sau khi trả lời.
        """
        from langchain_core.messages import HumanMessage

        history = load_history(self.settings.sessions_dir, thread_id)
        result = self.agent.invoke(
            {"messages": [*history, HumanMessage(content=message)]},
            config={"configurable": {"thread_id": thread_id}},
        )
        answer = result["messages"][-1].content

        title = next((m.content for m in result["messages"] if m.type == "human"), thread_id)
        title = str(title)[:40]
        write_history(self.settings.sessions_dir, thread_id, result["messages"], title=title)
        rename_session(self.settings.sessions_dir, thread_id, title)
        return answer

    def history(self, thread_id: str) -> list[dict[str, str]]:
        """Lịch sử session (để hiển thị)."""
        return [
            {"role": message.type, "content": str(message.content)}
            for message in load_history(self.settings.sessions_dir, thread_id)
        ]


def build_runtime(settings: Settings) -> Runtime:
    """Dựng runtime đầy đủ."""
    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    agent = build_agent(build_model(settings), settings, manager=manager)
    return Runtime(settings=settings, store=store, manager=manager, agent=agent)


def runtime_from_settings(settings: Settings) -> Runtime:
    """Alias của :func:`build_runtime` (giữ tên gọi rõ nghĩa ở UI/CLI)."""
    return build_runtime(settings)


def injected_context(settings: Settings, manager: MemoryManager | None) -> str:
    """Đúng phần context sẽ được inject vào model (để kiểm chứng theo yêu cầu của slide).

    Ở chế độ ``end`` thì index không nằm trong system prompt mà được đính vào
    cuối hội thoại (xem ``graph.build_agent``).
    """
    at_end = settings.memory_placement == "end"
    return build_context(
        long_term_memory=settings.enable_long_term_memory and manager is not None,
        summarization=settings.enable_summarization,
        agents_text=read_agents_file(settings.agents_path),
        memory_index="" if at_end else (manager.index_text() if manager else ""),
    )
