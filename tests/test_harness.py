from tests.test_memory_tools import make_tools


def test_similar_words_do_not_replace_independent_decision(tmp_path):
    tools, manager = make_tools(tmp_path)
    tools[0].invoke({"topic": "preferences", "content": "Tôi thích lập trình Python"})
    tools[0].invoke({"topic": "preferences", "content": "Tôi thích lập trình Rust"})
    assert len(manager.entries(include_superseded=False)) == 2


def test_invalid_replacement_key_does_not_write(tmp_path):
    tools, manager = make_tools(tmp_path)
    result = tools[0].invoke({"topic": "auth", "content": "Dùng cookie", "supersedes": "invented-key"})
    assert "Không ghi được" in result
    assert manager.entries() == []


def test_cross_topic_replacement_rejected(tmp_path):
    tools, manager = make_tools(tmp_path)
    key = manager.remember("auth", "Dùng JWT")["key"]
    result = tools[0].invoke({"topic": "preferences", "content": "Thích Python", "supersedes": key})
    assert "Không ghi được" in result
    assert manager.find(key).is_active
    assert len(manager.entries()) == 1


def test_empty_update_rejected(tmp_path):
    tools, manager = make_tools(tmp_path)
    key = manager.remember("auth", "Dùng JWT")["key"]
    result = tools[2].invoke({"key": key, "content": " "})
    assert "Không sửa được" in result
    assert manager.find(key).content == "Dùng JWT"
