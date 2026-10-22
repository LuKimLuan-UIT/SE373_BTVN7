"""Test lịch sử session: ghi Markdown và đọc lại được (sau khi restart app)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from memory_agent.memory.history import (
    load_history,
    read_title,
    set_title,
    transcript_path,
    write_history,
)


def test_history_is_markdown(tmp_path):
    path = write_history(
        tmp_path / "sessions",
        "s1",
        [HumanMessage(content="Tôi tên là An"), AIMessage(content="Chào An")],
        title="Tôi tên là An",
    )
    text = path.read_text(encoding="utf-8")
    assert "# Session `s1`" in text
    assert "- Tiêu đề: Tôi tên là An" in text
    assert "## User" in text
    assert "## Assistant" in text
    assert "Tôi tên là An" in text


def test_load_history_roundtrip(tmp_path):
    write_history(
        tmp_path / "sessions",
        "s1",
        [HumanMessage(content="Câu 1"), AIMessage(content="Trả lời 1"), HumanMessage(content="Câu 2")],
        title="Câu 1",
    )

    history = load_history(tmp_path / "sessions", "s1")
    assert [m.type for m in history] == ["human", "ai", "human"]
    assert history[0].content == "Câu 1"
    assert history[1].content == "Trả lời 1"
    assert history[2].content == "Câu 2"


def test_load_history_survives_new_process_state(tmp_path):
    """Lịch sử nằm trên đĩa -> đọc lại được sau khi app restart."""
    sessions_dir = tmp_path / "sessions"
    write_history(sessions_dir, "s1", [HumanMessage(content="Câu 1")], title="Câu 1")

    # "restart": chỉ cần đọc lại từ đĩa.
    history = load_history(sessions_dir, "s1")
    assert len(history) == 1


def test_load_history_empty_when_missing(tmp_path):
    assert load_history(tmp_path / "sessions", "khong-co") == []


def test_rename_title(tmp_path):
    sessions_dir = tmp_path / "sessions"
    write_history(sessions_dir, "s1", [HumanMessage(content="x")], title="cũ")
    set_title(sessions_dir, "s1", "mới")
    assert read_title(transcript_path(sessions_dir, "s1")) == "mới"
