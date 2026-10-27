"""Both B1 modes: retention, continuation, real usage and failure atomicity."""
import importlib
import json

import pytest
from langchain_core.messages import AIMessage

from memory_agent.challenge_b_lab import ChallengeBLab
from memory_agent.context import CHECKPOINT_PREFIX
from tests.test_agent_memory import FakeToolChatModel, make_settings
from tests.test_challenge_b import demo
from tests.test_maintenance import request


@pytest.fixture
def modes(tmp_path, monkeypatch):
    app = importlib.import_module("memory_agent.ui.app")
    routes = importlib.import_module("memory_agent.ui.challenge_b")
    lab = ChallengeBLab(make_settings(tmp_path), tmp_path / "b")
    monkeypatch.setattr(routes, "_lab", lab)
    return app, lab


@pytest.mark.parametrize("endpoint", ["chat/compact", "b1/compact"])
def test_offline_modes_on_same_history_preserve_archive_and_expose_loss(modes, monkeypatch, endpoint):
    from memory_agent import challenge_b_lab
    app, lab = modes
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline must never initialize a provider")
    monkeypatch.setattr(challenge_b_lab, "build_model", forbidden)
    snapshots = []
    for technique in ("truncation", "structured"):
        thread = lab.seed(execution="offline")["thread_id"]
        original = lab._working(thread).load()
        response = request(app, "POST", "/api/challenge-b/" + endpoint,
                           json={"thread_id": thread, "technique": technique})
        assert response.status_code == 200, response.text
        result = response.json()
        result = result.get("compact", result)
        active, archive = lab._working(thread).load()
        assert archive == original[1]
        assert result["after"]["estimated_tokens"] < result["before"]["estimated_tokens"]
        assert lab.chat_view(thread)["usage"]["requests"] == 0
        assert lab.chat_view(thread)["usage"]["actual_input_tokens"] == 0
        assert "DEBUG duplicate" not in str(active)
        continued = lab.continue_task(thread)
        assert continued["technique"] == technique
        if technique == "structured":
            cp = result["checkpoint"]
            assert result["summary_method"] == "offline-extraction"
            assert "/refresh" in str(cp["constraints"])
            assert "timeout 30s" in str(cp["failed_attempts"])
            assert "401" in cp["current_state"]
            assert "tests/test_refresh.py" in cp["next_action"]
            assert "race.log:7" in str(cp["findings"])
            assert "tests/test_refresh.py" in continued["reply"]
            assert lab.chat_view(thread)["timeline"][-3]["checkpoint"] == cp
        else:
            assert "checkpoint" not in result
            assert "tests/test_refresh.py" not in continued["reply"]
        snapshots.append(original)
    assert snapshots[0] == snapshots[1]


def test_provider_checkpoint_usage_and_next_request_survive_reload(modes):
    app, lab = modes
    lab.model = FakeToolChatModel(responses=[
        AIMessage(content=json.dumps(demo.CHECKPOINT), usage_metadata={
            "input_tokens": 501, "output_tokens": 83, "total_tokens": 584}),
        AIMessage(content="Thêm test trong tests/test_refresh.py; giữ API /refresh.", usage_metadata={
            "input_tokens": 120, "output_tokens": 20, "total_tokens": 140}),
    ])
    thread = lab.seed(execution="provider")["thread_id"]
    response = request(app, "POST", "/api/challenge-b/chat/compact",
                       json={"thread_id": thread, "technique": "structured"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["compact"]["summary_method"] == "model"
    assert data["chat"]["usage"]["requests"] == 1
    assert data["chat"]["usage"]["actual_input_tokens"] == 501
    assert data["chat"]["usage"]["actual_output_tokens"] == 83
    assert request(app, "GET", "/api/challenge-b/chat/" + thread).json() == data["chat"]
    continued = lab.send(thread, "Tiếp tục từ bước kế tiếp")
    prompts = json.dumps(continued["timeline"][-1]["prompts"], ensure_ascii=False)
    assert CHECKPOINT_PREFIX.strip() in prompts and "tests/test_refresh.py" in prompts
    assert "DEBUG duplicate" not in prompts
    assert continued["usage"]["requests"] == 2
    assert continued["usage"]["actual_input_tokens"] == 621


def test_missing_provider_usage_is_unknown_and_not_zero(modes):
    _, lab = modes
    lab.model = FakeToolChatModel(responses=[AIMessage(content=json.dumps(demo.CHECKPOINT))])
    thread = lab.seed(execution="provider")["thread_id"]
    result = lab.compact(thread, technique="structured")
    assert result["measurement"]["requests"] == 1
    assert result["measurement"]["actual_input_tokens"] is None
    assert result["measurement"]["actual_output_tokens"] is None
    assert result["measurement"]["estimated_input_tokens"] > 0


@pytest.mark.parametrize("response", ["not json", json.dumps(demo.CHECKPOINT)])
def test_failed_checkpoint_keeps_history_but_counts_consumed_usage(modes, response):
    app, lab = modes
    lab.model = FakeToolChatModel(responses=[AIMessage(content=response, usage_metadata={
        "input_tokens": 100, "output_tokens": 15, "total_tokens": 115})])
    # Valid JSON is still rejected if it makes a short chat larger.
    thread = (lab.seed(execution="provider")["thread_id"] if response == "not json"
              else lab.new_chat(execution="provider")["thread_id"])
    if response != "not json":
        from langchain_core.messages import HumanMessage
        history = [HumanMessage(content="Hi")]
        lab._working(thread).save(history, history)
    before = lab._working(thread).path.read_bytes()
    timeline = lab.chat_view(thread)["timeline"]
    result = request(app, "POST", "/api/challenge-b/chat/compact",
                     json={"thread_id": thread, "technique": "structured"})
    assert result.status_code == 400
    assert lab._working(thread).path.read_bytes() == before
    view = lab.chat_view(thread)
    assert view["timeline"] == timeline
    assert view["usage"]["actual_input_tokens"] == 100
    assert view["usage"]["actual_output_tokens"] == 15
    assert view["usage"]["last"]["kind"] == "compact-failed"


def test_switching_mode_after_cut_does_not_read_archive(modes):
    _, lab = modes
    thread = lab.seed(execution="offline")["thread_id"]
    lab.compact(thread, technique="truncation")
    before = lab._working(thread).path.read_bytes()
    # The remaining short history cannot benefit from a checkpoint, and the
    # archived constraints must not be silently restored by switching modes.
    with pytest.raises(ValueError, match="nhỏ hơn"):
        lab.compact(thread, technique="structured")
    assert lab._working(thread).path.read_bytes() == before
    assert "tests/test_refresh.py" not in str(lab._working(thread).load()[0])


def test_unknown_mode_does_not_mutate_history_or_call_model(modes):
    app, lab = modes
    thread = lab.seed(execution="offline")["thread_id"]
    before = lab._working(thread).path.read_bytes()
    result = request(app, "POST", "/api/challenge-b/chat/compact",
                     json={"thread_id": thread, "technique": "unknown"})
    assert result.status_code == 422
    assert lab._working(thread).path.read_bytes() == before
