"""Kiểm chứng Challenge A; xfail mô tả lỗi đã biết, không coi là đạt yêu cầu."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from memory_agent.memory.history import load_history, write_history
from memory_agent.memory.lifecycle import MemoryManager
from memory_agent.memory.store import MarkdownMemoryStore
from memory_agent.memory_tools import build_memory_tools
from tests.test_agent_memory import FakeToolChatModel, make_runtime, tool_call


def manager_at(tmp_path):
    return MemoryManager(MarkdownMemoryStore(tmp_path / "memory", "u1"), "u1")


def test_memory_survives_separate_python_processes(tmp_path):
    """Hai process độc lập, không chia sẻ object hay lịch sử trong RAM."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    setup = (
        "import sys; from memory_agent.memory.store import MarkdownMemoryStore; "
        "from memory_agent.memory.lifecycle import MemoryManager; "
        "m = MemoryManager(MarkdownMemoryStore(sys.argv[1], 'u1'), 'u1'); "
    )
    for operation in (
        "m.remember('auth', 'Authentication uses JWT', source='s1')",
        "assert m.entries('auth')[0].content == 'Authentication uses JWT'; "
        "assert m.entries('auth')[0].source == 's1'",
    ):
        subprocess.run(
            [sys.executable, "-c", setup + operation, str(tmp_path / "memory")],
            env=env, check=True, capture_output=True, text=True, timeout=30,
        )


def test_new_session_receives_only_current_convention(tmp_path):
    runtime = make_runtime(tmp_path, FakeToolChatModel(responses=[
        tool_call("remember", {"topic": "auth", "content": "Authentication sử dụng JWT"}),
        AIMessage(content="Đã ghi."),
    ]))
    runtime.chat("s1", "Dùng JWT")
    old_key = runtime.manager.entries("auth")[0].key
    changed = make_runtime(tmp_path, FakeToolChatModel(responses=[
        tool_call("supersede", {"key": old_key, "content": "Authentication sử dụng session cookie"}),
        AIMessage(content="Đã thay thế."),
    ]))
    changed.chat("s2", "Chuyển sang session cookie")
    seen = []

    class RecordingModel(FakeToolChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.extend(messages)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    restarted = make_runtime(tmp_path, RecordingModel(responses=[AIMessage(content="ok")]))
    restarted.chat("s3", "Dự án dùng gì để đăng nhập?")
    system = "\n".join(str(m.content) for m in seen if m.type == "system")
    assert "session cookie" in system
    assert "JWT" not in system
    assert restarted.manager.find(old_key).status == "superseded"
    assert not any("Chuyển sang" in str(m.content) for m in seen)


def test_forget_survives_reopening_store(tmp_path):
    manager = manager_at(tmp_path)
    key = manager.remember("auth", "Dùng JWT")["key"]
    assert manager.forget(key)
    reopened = manager_at(tmp_path)
    assert reopened.find(key) is None
    assert "Dùng JWT" not in reopened.index_text()


def test_failed_write_is_reported_by_tool(tmp_path, monkeypatch):
    manager = manager_at(tmp_path)

    def fail(*args, **kwargs):
        raise PermissionError("write denied for test")

    monkeypatch.setattr(manager.store, "put", fail)
    result = build_memory_tools(manager)[0].invoke({"topic": "auth", "content": "Dùng JWT"})
    assert "Không ghi được memory" in result
    assert "Đã ghi memory" not in result
    assert manager.entries() == []


@pytest.mark.xfail(strict=True, reason="CA-B01: MemoryEntry bỏ mất timestamp từ SearchItem")
def test_entry_exposes_persisted_timestamps(tmp_path):
    manager = manager_at(tmp_path)
    key = manager.remember("auth", "Dùng JWT")["key"]
    persisted = manager.store.get(("memory", "u1", "auth"), key)
    entry = manager.find(key)
    assert entry.created_at == persisted.created_at.isoformat(timespec="seconds")
    assert entry.updated_at == persisted.updated_at.isoformat(timespec="seconds")


def test_supersede_tool_records_current_session_source(tmp_path):
    manager = manager_at(tmp_path)
    key = manager.remember("auth", "Dùng JWT", source="s1")["key"]
    manager.current_source = "s2"
    result = build_memory_tools(manager)[3].invoke({"key": key, "content": "Dùng session cookie"})
    assert "Đã thay thế" in result
    assert manager.entries("auth", include_superseded=False)[0].source == "s2"
    assert manager.find(key).source == "s1"


@pytest.mark.xfail(strict=True, reason="CA-B03: trùng từ khóa dưới ngưỡng 0.4 nên còn hai quy ước")
def test_remember_detects_reworded_auth_change(tmp_path):
    manager = manager_at(tmp_path)
    manager.remember("auth", "Dùng JWT", source="s1")
    manager.remember("auth", "Chuyển sang session cookie", source="s2")
    active = manager.entries("auth", include_superseded=False)
    assert len(active) == 1
    assert active[0].content == "Chuyển sang session cookie"


@pytest.mark.xfail(strict=True, reason="CA-B04: heading Markdown trong nội dung bị hiểu là ranh giới role")
def test_session_preserves_markdown_headings(tmp_path):
    content = "Quy ước dự án\n\n## Authentication\n\nDùng JWT"
    write_history(tmp_path / "sessions", "s1", [HumanMessage(content=content)])
    history = load_history(tmp_path / "sessions", "s1")
    assert len(history) == 1
    assert history[0].content == content
