"""Test vòng đời memory: ghi, đọc, sửa, thay thế, quên — và xử lý xung đột."""

from __future__ import annotations

from memory_agent.memory.lifecycle import MemoryManager
from memory_agent.memory.store import MarkdownMemoryStore


def make_manager(tmp_path, user_id="u1"):
    store = MarkdownMemoryStore(tmp_path / "memory", user_id)
    return MemoryManager(store, user_id)


def test_remember_then_recall(tmp_path):
    manager = make_manager(tmp_path)
    result = manager.remember("preferences", "An thích lập trình Python", source="s1")
    assert result["key"]

    entries = manager.entries()
    assert len(entries) == 1
    assert entries[0].content == "An thích lập trình Python"
    assert entries[0].source == "s1"
    assert entries[0].is_active


def test_update_keeps_created_at(tmp_path):
    manager = make_manager(tmp_path)
    key = manager.remember("preferences", "An thích Python")["key"]
    before = manager.find(key).created_at

    manager.update(key, "An thích Rust")

    entry = manager.find(key)
    assert entry.content == "An thích Rust"
    assert entry.created_at == before


def test_supersede_marks_old_entry_instead_of_deleting(tmp_path):
    """Quy ước đổi -> mục cũ bị đánh dấu superseded, vẫn truy vết được."""
    manager = make_manager(tmp_path)
    old_key = manager.remember("auth", "Authentication sử dụng JWT", source="session-1")["key"]

    result = manager.supersede(old_key, "Authentication sử dụng session cookie", source="session-2")

    old = manager.find(old_key)
    new = manager.find(result["key"])
    assert old is not None, "mục cũ không được xoá hẳn"
    assert old.status == "superseded"
    assert old.superseded_by == result["key"]
    assert old.source == "session-1"
    assert new.is_active
    assert new.content == "Authentication sử dụng session cookie"


def test_index_only_shows_current_convention(tmp_path):
    manager = make_manager(tmp_path)
    old_key = manager.remember("auth", "Authentication sử dụng JWT")["key"]
    manager.supersede(old_key, "Authentication sử dụng session cookie")

    index = manager.index_text()
    assert "session cookie" in index
    assert "JWT" not in index


def test_conflict_auto_supersedes_old_entry(tmp_path):
    """Trùng chủ đề -> supersede mục cũ TRƯỚC, rồi mới ghi mục mới."""
    manager = make_manager(tmp_path)
    old_key = manager.remember("auth", "Authentication sử dụng JWT token")["key"]

    result = manager.remember("auth", "Authentication sử dụng JWT token mới")

    assert result["superseded"] == [old_key]
    assert manager.find(old_key).status == "superseded"
    assert manager.find(old_key).superseded_by == result["key"]

    active = [e for e in manager.entries(topic="auth") if e.is_active]
    assert len(active) == 1
    assert active[0].content == "Authentication sử dụng JWT token mới"


def test_force_keeps_both_entries(tmp_path):
    manager = make_manager(tmp_path)
    manager.remember("auth", "Authentication sử dụng JWT token")

    manager.remember("auth", "Authentication sử dụng JWT token mới", force=True)

    active = [e for e in manager.entries(topic="auth") if e.is_active]
    assert len(active) == 2


def test_supersede_by_explicit_key(tmp_path):
    manager = make_manager(tmp_path)
    old_key = manager.remember("auth", "Authentication sử dụng JWT token")["key"]

    result = manager.supersede(old_key, "Authentication sử dụng session cookie")

    assert manager.find(old_key).status == "superseded"
    assert manager.find(result["key"]).is_active


def test_forget_removes_entry(tmp_path):
    manager = make_manager(tmp_path)
    key = manager.remember("preferences", "An thích Python")["key"]
    assert manager.forget(key) is True
    assert manager.find(key) is None
    assert manager.forget(key) is False


def test_memory_isolated_per_user(tmp_path):
    store = MarkdownMemoryStore(tmp_path / "memory", "u1")
    u1 = MemoryManager(store, "u1")
    u2 = MemoryManager(store, "u2")

    u1.remember("preferences", "An thích Python")
    assert len(u1.entries()) == 1
    assert len(u2.entries()) == 0
