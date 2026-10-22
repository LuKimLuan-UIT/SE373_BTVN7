"""Test store Markdown: index (MEMORY.md) + file chi tiết theo topic."""

from __future__ import annotations

from memory_agent.memory.store import MarkdownMemoryStore


def make_store(tmp_path, user_id="u1"):
    return MarkdownMemoryStore(tmp_path / "memory", user_id)


def test_put_get_roundtrip(tmp_path):
    store = make_store(tmp_path)
    store.put(("memory", "u1", "preferences"), "fact-1", {"content": "An thích Python", "status": "active"})

    item = store.get(("memory", "u1", "preferences"), "fact-1")
    assert item is not None
    assert item.value["content"] == "An thích Python"
    assert item.key == "fact-1"
    assert item.namespace == ("memory", "u1", "preferences")


def test_data_survives_new_instance(tmp_path):
    """Memory là bộ nhớ bền vững: mở lại vẫn thấy dữ liệu cũ."""
    store = make_store(tmp_path)
    store.put(("memory", "u1", "preferences"), "fact-1", {"content": "An thích Python"})

    reopened = make_store(tmp_path)
    assert reopened.get(("memory", "u1", "preferences"), "fact-1").value["content"] == "An thích Python"


def test_memory_is_readable_markdown(tmp_path):
    """File memory phải đọc được bằng mắt (Markdown, không phải JSON blob)."""
    store = make_store(tmp_path)
    store.put(("memory", "u1", "preferences"), "fact-1", {"content": "An thích Python", "source": "s1"})

    topic_file = (tmp_path / "memory" / "u1" / "preferences.md").read_text(encoding="utf-8")
    assert "# preferences" in topic_file
    assert "## fact-1" in topic_file
    assert "- content: An thích Python" in topic_file
    assert "- source: s1" in topic_file


def test_index_lists_topic_and_summary(tmp_path):
    store = make_store(tmp_path)
    store.put(("memory", "u1", "preferences"), "fact-1", {"content": "An thích Python", "status": "active"})

    index = store.index_text()
    assert "preferences" in index
    assert "An thích Python" in index
    assert (tmp_path / "memory" / "u1" / "MEMORY.md").exists()


def test_index_hides_superseded_entries(tmp_path):
    store = make_store(tmp_path)
    store.put(("memory", "u1", "auth"), "fact-old", {"content": "Dùng JWT", "status": "superseded"})
    store.put(("memory", "u1", "auth"), "fact-new", {"content": "Dùng session cookie", "status": "active"})

    index = store.index_text()
    assert "Dùng session cookie" in index
    assert "Dùng JWT" not in index


def test_search_scopes_by_namespace_prefix(tmp_path):
    store = make_store(tmp_path)
    store.put(("memory", "u1", "preferences"), "fact-1", {"content": "a"})
    store.put(("memory", "u2", "preferences"), "fact-2", {"content": "b"})

    keys = {item.key for item in store.search(("memory", "u1"))}
    assert keys == {"fact-1"}

    all_keys = {item.key for item in store.search(("memory",))}
    assert all_keys == {"fact-1", "fact-2"}


def test_delete_removes_item(tmp_path):
    store = make_store(tmp_path)
    store.put(("memory", "u1", "preferences"), "fact-1", {"content": "a"})
    store.delete(("memory", "u1", "preferences"), "fact-1")
    assert store.get(("memory", "u1", "preferences"), "fact-1") is None
