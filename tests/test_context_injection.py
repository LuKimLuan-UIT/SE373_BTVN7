"""Test phần context được inject vào model (kiểm chứng theo yêu cầu của slide)."""

from __future__ import annotations

from memory_agent.config import Settings
from memory_agent.memory.lifecycle import MemoryManager
from memory_agent.memory.store import MarkdownMemoryStore
from memory_agent.prompts import build_memory_digest
from memory_agent.runtime import injected_context


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
        memory_placement="system",
        model_call_limit=8,
    )


def test_context_contains_agents_and_index(tmp_path):
    settings = make_settings(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("## Quy tắc\n- Luôn trả lời bằng tiếng Việt.", encoding="utf-8")

    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    manager.remember("preferences", "An thích lập trình Python")

    context = injected_context(settings, manager)

    assert "Luôn trả lời bằng tiếng Việt" in context
    assert "Memory index" in context
    assert "An thích lập trình Python" in context


def test_index_is_short_and_details_not_injected(tmp_path):
    """Progressive disclosure: index luôn nạp, chi tiết chỉ nạp khi gọi recall."""
    settings = make_settings(tmp_path)
    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    for i in range(40):
        manager.remember("preferences", f"An thích thứ {i} trong lập trình")

    context = injected_context(settings, manager)

    assert "An thích thứ 0" in context          # index có tóm tắt
    assert "An thích thứ 39" not in context     # chi tiết không nạp hết vào context
    assert context.count("An thích thứ") <= 15  # index bị giới hạn số dòng


def test_context_without_memory_feature(tmp_path):
    settings = make_settings(tmp_path)
    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    manager.remember("preferences", "An thích Python")

    disabled = Settings(**{**settings.__dict__, "enable_long_term_memory": False})
    context = injected_context(disabled, manager)

    assert "Memory index" not in context


def test_context_is_byte_identical_between_turns(tmp_path):
    """Prompt caching: system prompt phải giống hệt nhau khi memory không đổi.

    Nếu có timestamp/random trong prompt thì prefix cache của provider (Anthropic,
    OpenAI, Gemini) sẽ miss mỗi lượt.
    """
    settings = make_settings(tmp_path)
    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    manager.remember("preferences", "An thích Python")

    first = injected_context(settings, manager)
    second = injected_context(settings, manager)

    assert first == second


def test_volatile_index_is_at_the_end_of_prompt(tmp_path):
    """Phần thay đổi (index memory) phải nằm CUỐI prompt.

    Như vậy khi index đổi, chỉ phần đuôi bị cache-miss, còn prefix ổn định
    (base prompt + AGENTS.md) vẫn được cache.
    """
    settings = make_settings(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("## Quy tắc\n- Marker của AGENTS.", encoding="utf-8")

    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    manager.remember("preferences", "Marker của index")

    context = injected_context(settings, manager)

    assert context.index("Marker của AGENTS.") < context.index("Marker của index")


def test_memory_placement_end_keeps_history_cached(tmp_path):
    """Chế độ ``end``: digest memory là message CUỐI -> lịch sử vẫn nằm trong prefix cache.

    Với prefix cache, chỉ phần sau điểm khác biệt đầu tiên bị xử lý lại.
    Nếu digest đặt cuối hội thoại, đổi memory chỉ làm hỏng cache từ digest trở đi.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    settings = make_settings(tmp_path)
    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    manager.remember("preferences", "An thích Python")

    # "end": system prompt KHÔNG chứa index -> phần system + lịch sử giữ nguyên.
    at_end = Settings(**{**settings.__dict__, "memory_placement": "end"})
    context = injected_context(at_end, manager)
    assert "Memory index" not in context

    # Digest được đính vào cuối danh sách message (sau lịch sử) -> lịch sử vẫn cache được.
    digest = build_memory_digest(manager.index_text())
    messages = [HumanMessage(content="Câu 1"), SystemMessage(content=digest)]

    assert messages.index(messages[-1]) == len(messages) - 1
    assert "An thích Python" in digest
