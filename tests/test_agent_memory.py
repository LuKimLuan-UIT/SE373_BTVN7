"""Integration test: agent thật (LangChain create_agent) + fake model.

Mục tiêu: chứng minh trí nhớ hoạt động đúng end-to-end mà **không cần API key**:

1. Agent gọi tool `remember` -> quy ước được ghi vào file Markdown.
2. Session mới (thread khác) gọi `recall` -> vẫn nhớ quy ước cũ (memory xuyên session).
3. Lịch sử session nạp lại được sau khi "restart" (đọc từ file Markdown).
4. Quy ước đổi -> `supersede` giữ lại dấu vết (mục cũ = superseded).
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from memory_agent.config import Settings
from memory_agent.graph import build_agent
from memory_agent.memory.history import load_history, write_history
from memory_agent.memory.lifecycle import MemoryManager
from memory_agent.memory.store import MarkdownMemoryStore
from memory_agent.runtime import Runtime


class FakeToolChatModel(BaseChatModel):
    """Model giả: trả lần lượt các message đã định sẵn, hỗ trợ bind_tools."""

    responses: list[Any] = []
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake-tool-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        message = self.responses[index]
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self


def make_settings(tmp_path) -> Settings:
    return Settings(
        api_key="fake-key",
        model_name="fake-model",
        base_url=None,
        user_id="u1",
        memory_dir=str(tmp_path / "memory"),
        sessions_dir=str(tmp_path / "sessions"),
        agents_path=str(tmp_path / "AGENTS.md"),
        enable_long_term_memory=True,
        enable_summarization=False,
        memory_placement="system",
        summarize_trigger_messages=12,
        summarize_keep_messages=6,
        model_call_limit=8,
    )


def make_runtime(tmp_path, model) -> Runtime:
    settings = make_settings(tmp_path)
    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    agent = build_agent(model, settings, manager=manager)
    return Runtime(settings=settings, store=store, manager=manager, agent=agent)


def tool_call(name: str, args: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_agent_remembers_convention_across_sessions(tmp_path):
    model = FakeToolChatModel(
        responses=[
            tool_call("remember", {"topic": "auth", "content": "Authentication sử dụng JWT"}),
            AIMessage(content="Đã nhớ quy ước đăng nhập dùng JWT."),
        ]
    )
    runtime = make_runtime(tmp_path, model)
    runtime.chat("s1", "Dự án này dùng JWT để đăng nhập")

    # --- session 2: hỏi lại ở thread khác -> phải nhớ được
    model2 = FakeToolChatModel(
        responses=[
            tool_call("recall", {"topic": "auth"}),
            AIMessage(content="Dự án dùng JWT để đăng nhập."),
        ]
    )
    runtime2 = make_runtime(tmp_path, model2)
    history = load_history(tmp_path / "sessions", "s2")
    result = runtime2.agent.invoke(
        {"messages": [*history, HumanMessage(content="Dự án này dùng gì để đăng nhập?")]},
        config={"configurable": {"thread_id": "s2"}},
    )

    # Agent đã gọi tool recall và đọc được quy ước của session trước.
    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    assert tool_messages, "Agent phải gọi tool recall"
    assert "Authentication sử dụng JWT" in tool_messages[0].content

    # Quy ước nằm trong file Markdown, đọc được bằng mắt.
    topic_file = (tmp_path / "memory" / "u1" / "auth.md").read_text(encoding="utf-8")
    assert "- content: Authentication sử dụng JWT" in topic_file

    # Index MEMORY.md chứa tóm tắt mục.
    index = (tmp_path / "memory" / "u1" / "MEMORY.md").read_text(encoding="utf-8")
    assert "auth" in index
    assert "Authentication sử dụng JWT" in index


def test_session_history_persists_in_markdown(tmp_path):
    model = FakeToolChatModel(responses=[AIMessage(content="Chào bạn!")])
    runtime = make_runtime(tmp_path, model)
    runtime.chat("s1", "xin chào")

    history = load_history(tmp_path / "sessions", "s1")
    assert [m.type for m in history] == ["human", "ai"]
    assert history[0].content == "xin chào"


def test_agent_supersedes_stale_convention(tmp_path):
    model = FakeToolChatModel(
        responses=[
            tool_call("remember", {"topic": "auth", "content": "Authentication sử dụng JWT"}),
            AIMessage(content="ok"),
        ]
    )
    runtime = make_runtime(tmp_path, model)
    runtime.chat("s1", "Dùng JWT")

    old_key = runtime.manager.entries(topic="auth")[0].key

    model2 = FakeToolChatModel(
        responses=[
            tool_call("supersede", {"key": old_key, "content": "Authentication sử dụng session cookie"}),
            AIMessage(content="ok"),
        ]
    )
    runtime2 = make_runtime(tmp_path, model2)
    runtime2.chat("s2", "Chuyển sang session cookie")

    old = runtime2.manager.find(old_key)
    assert old is not None and old.status == "superseded"
    assert old.superseded_by

    # Index chỉ hiện quy ước hiện hành.
    index = runtime2.manager.index_text()
    assert "session cookie" in index
    assert "JWT" not in index


def test_history_is_reused_across_turns(tmp_path):
    """Lượt thứ 2 phải thấy lượt thứ 1 (nạp lại từ file Markdown)."""
    model = FakeToolChatModel(responses=[AIMessage(content="Trả lời")])
    runtime = make_runtime(tmp_path, model)
    runtime.chat("s1", "Câu 1")

    seen: list[str] = []

    class RecordingModel(FakeToolChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.extend(str(m.content) for m in messages)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    runtime2 = make_runtime(tmp_path, RecordingModel(responses=[AIMessage(content="Trả lời 2")]))
    runtime2.chat("s1", "Câu 2")

    assert any("Câu 1" in content for content in seen)
    assert any("Câu 2" in content for content in seen)


def test_placement_end_puts_digest_after_history(tmp_path):
    """Chế độ ``end``: digest memory nằm SAU lịch sử -> lịch sử giữ được prefix cache."""
    from langchain_core.messages import SystemMessage

    settings = make_settings(tmp_path)
    at_end = Settings(**{**settings.__dict__, "memory_placement": "end"})

    store = MarkdownMemoryStore(at_end.memory_dir, at_end.user_id)
    manager = MemoryManager(store, at_end.user_id)
    manager.remember("preferences", "An thích Python")

    seen: list[Any] = []

    class RecordingModel(FakeToolChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.extend(messages)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    agent = build_agent(RecordingModel(responses=[AIMessage(content="ok")]), at_end, manager=manager)
    agent.invoke({"messages": [HumanMessage(content="Câu 1")]})

    assert seen, "model phải được gọi"
    last = seen[-1]
    assert isinstance(last, SystemMessage)
    assert "An thích Python" in str(last.content)
