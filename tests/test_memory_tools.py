"""Test các tool trí nhớ dài hạn (remember / recall / update / supersede / forget)."""

from __future__ import annotations

from memory_agent.memory.lifecycle import MemoryManager
from memory_agent.memory.store import MarkdownMemoryStore
from memory_agent.memory_tools import build_memory_tools


def make_tools(tmp_path, user_id="u1"):
    store = MarkdownMemoryStore(tmp_path / "memory", user_id)
    manager = MemoryManager(store, user_id)
    return build_memory_tools(manager), manager


def test_remember_then_recall(tmp_path):
    tools, _ = make_tools(tmp_path)
    remember, recall = tools[0], tools[1]

    result = remember.invoke({"topic": "preferences", "content": "An thích lập trình Python"})
    assert "Đã ghi memory" in result

    recalled = recall.invoke({})
    assert "An thích lập trình Python" in recalled


def test_recall_by_topic(tmp_path):
    tools, _ = make_tools(tmp_path)
    remember, recall = tools[0], tools[1]
    remember.invoke({"topic": "preferences", "content": "An thích Python"})
    remember.invoke({"topic": "auth", "content": "Dùng JWT"})

    only_auth = recall.invoke({"topic": "auth"})
    assert "Dùng JWT" in only_auth
    assert "An thích Python" not in only_auth


def test_recall_is_empty_at_start(tmp_path):
    tools, _ = make_tools(tmp_path)
    recall = tools[1]
    assert "Chưa có" in recall.invoke({})


def test_remember_auto_supersedes_conflict(tmp_path):
    """Mục mới trùng chủ đề -> mục cũ bị supersede, mục mới ghi vào."""
    tools, manager = make_tools(tmp_path)
    remember = tools[0]
    first = remember.invoke({"topic": "auth", "content": "Authentication sử dụng JWT token"})
    old_key = first.split("key=")[1].split(":")[0].strip()

    result = remember.invoke({"topic": "auth", "content": "Authentication sử dụng JWT token mới"})

    assert "Đã ghi memory" in result
    assert "supersede" in result
    assert manager.find(old_key).status == "superseded"

    active = [e for e in manager.entries(topic="auth") if e.is_active]
    assert len(active) == 1


def test_remember_force_keeps_both(tmp_path):
    tools, manager = make_tools(tmp_path)
    remember = tools[0]
    remember.invoke({"topic": "auth", "content": "Authentication sử dụng JWT token"})
    result = remember.invoke(
        {"topic": "auth", "content": "Authentication sử dụng JWT token mới", "force": True}
    )

    assert "Đã ghi memory" in result
    assert len([e for e in manager.entries(topic="auth") if e.is_active]) == 2


def test_supersede_replaces_and_keeps_trace(tmp_path):
    tools, manager = make_tools(tmp_path)
    remember, _, _, supersede = tools[0], tools[1], tools[2], tools[3]

    key = remember.invoke({"topic": "auth", "content": "Authentication sử dụng JWT"})
    old_key = key.split("key=")[1].split(":")[0].strip()

    result = supersede.invoke({"key": old_key, "content": "Authentication sử dụng session cookie"})
    assert "Đã thay thế" in result

    old = manager.find(old_key)
    assert old is not None and old.status == "superseded"


def test_forget_removes_fact(tmp_path):
    tools, _ = make_tools(tmp_path)
    remember, recall, _, _, forget = tools
    remember.invoke({"topic": "preferences", "content": "Sở thích: Python"})

    key = tools[0].invoke({"topic": "preferences", "content": "Sở thích: Python"})
    key_value = key.split("key=")[1].split(":")[0].strip()

    assert "Đã quên" in forget.invoke({"key": key_value})
    assert "Chưa có" in recall.invoke({})


def test_update_tool(tmp_path):
    tools, _ = make_tools(tmp_path)
    remember, _, update = tools[0], tools[1], tools[2]
    result = remember.invoke({"topic": "preferences", "content": "An thích Python"})
    key_value = result.split("key=")[1].split(":")[0].strip()

    assert "Đã sửa" in update.invoke({"key": key_value, "content": "An thích Rust"})
