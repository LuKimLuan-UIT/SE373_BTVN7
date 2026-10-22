"""Test quản lý session: liệt kê, đặt tên, xoá (mỗi session = 1 file Markdown)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from memory_agent.memory.history import write_history
from memory_agent.sessions import delete_session, list_sessions, rename_session


def test_list_sessions_reads_files(tmp_path):
    sessions_dir = tmp_path / "sessions"
    write_history(sessions_dir, "s1", [HumanMessage(content="buổi học sáng")], title="buổi học sáng")
    write_history(sessions_dir, "s2", [HumanMessage(content="buổi chiều")], title="buổi chiều")

    sessions = list_sessions(sessions_dir)
    titles = {s.thread_id: s.title for s in sessions}
    assert titles["s1"] == "buổi học sáng"
    assert titles["s2"] == "buổi chiều"


def test_list_sessions_empty(tmp_path):
    assert list_sessions(tmp_path / "khong-co") == []


def test_rename_session(tmp_path):
    sessions_dir = tmp_path / "sessions"
    write_history(sessions_dir, "s1", [HumanMessage(content="x")], title="cũ")

    rename_session(sessions_dir, "s1", "mới")

    assert list_sessions(sessions_dir)[0].title == "mới"


def test_delete_session_removes_file(tmp_path):
    sessions_dir = tmp_path / "sessions"
    write_history(sessions_dir, "s1", [HumanMessage(content="x")], title="x")

    delete_session(sessions_dir, "s1")

    assert not (sessions_dir / "s1.md").exists()
    assert list_sessions(sessions_dir) == []
