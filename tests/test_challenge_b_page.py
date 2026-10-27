"""Separate page, namespace isolation and real graph/tool calls with an offline model."""
import importlib
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from memory_agent.challenge_b_lab import ChallengeBLab
from memory_agent.context import CHECKPOINT_PREFIX
from memory_agent.graph import build_agent
from memory_agent.memory.lifecycle import MemoryManager
from memory_agent.memory.store import MarkdownMemoryStore
from memory_agent.runtime import Runtime
from memory_agent.sessions import list_sessions
from tests.test_agent_memory import FakeToolChatModel, make_runtime, make_settings, tool_call
from tests.test_challenge_b import demo
from tests.test_maintenance import request


@pytest.fixture
def page(tmp_path, monkeypatch):
    app = importlib.import_module("memory_agent.ui.app")
    routes = importlib.import_module("memory_agent.ui.challenge_b")
    a = make_runtime(tmp_path / "a", FakeToolChatModel(responses=[AIMessage(content="A")]))
    a.manager.remember("auth", "Quy ước riêng của A")
    model = FakeToolChatModel(responses=[AIMessage(content="Chỉ còn tình trạng 401; thiếu ràng buộc và bằng chứng cũ.")])
    lab = ChallengeBLab(a.settings, tmp_path / "b", model=model)
    monkeypatch.setattr(app, "_state", {"runtime": a})
    monkeypatch.setattr(routes, "_lab", lab)
    return app, lab, a


def test_page_is_separate_and_has_experiment_controls(page):
    app, _, _ = page
    response = request(app, "GET", "/challenge-b")
    assert response.status_code == 200
    assert 'id="compact-btn"' in response.text
    assert 'id="reset-all-btn"' in response.text
    assert 'id="context-state"' in response.text
    assert 'id="context-note"' in response.text
    assert 'id="reset-context-btn"' in response.text
    assert 'id="code-prompts"' in response.text
    assert "/api/chat" not in response.text
    assert 'href="/challenge-b"' in request(app, "GET", "/").text
    status = request(app, "GET", "/api/challenge-b/status").json()
    assert status["namespace"] == "challenge-b-lab"
    assert status["fixture_lines"] == 10000
    assert status["expected_counts"]["refresh_timeout"] == 3000


def test_b1_flow_does_not_change_a_memory_or_sessions(page):
    app, lab, a = page
    seeded = request(app, "POST", "/api/challenge-b/b1/seed", json={"execution":"provider"}).json()
    payload = {"thread_id": seeded["thread_id"]}
    assert request(app, "POST", "/api/challenge-b/b1/continue", json=payload).status_code == 400
    cp = request(app, "POST", "/api/challenge-b/b1/compact", json=payload)
    assert cp.status_code == 200
    result = cp.json()
    assert result["technique"] == "truncation" and result["archive_preserved"]
    assert result["compaction_requests"] == 0 and lab.model.calls == 0
    assert "checkpoint" not in result
    assert result["after"]["estimated_tokens"] < result["before"]["estimated_tokens"]
    continued = request(app, "POST", "/api/challenge-b/b1/continue", json=payload)
    assert continued.status_code == 200
    assert "thiếu" in continued.json()["reply"]
    assert list_sessions(a.settings.sessions_dir) == []
    assert "Quy ước riêng của A" in a.manager.index_text()
    assert lab.settings.sessions_dir != a.settings.sessions_dir
    assert lab.settings.memory_dir != a.settings.memory_dir
    assert {"b1-seed", "b1-compact", "b1-continuation"}.issubset(lab.results())


def test_b2_code_and_baseline_are_measured_and_keep_data_separate(page):
    app, lab, a = page
    lab.model = demo.DemoModel(mode="code")
    code = request(app, "POST", "/api/challenge-b/b2/code", json={})
    assert code.status_code == 200
    data = code.json()
    assert data["golden_counts_match"]
    assert data["raw_marker_in_requests"] is False
    assert data["measurement"]["requests"] == 2
    assert data["findings"]["files_scanned"] == 4
    lab.model = demo.DemoModel(mode="native")
    native = request(app, "POST", "/api/challenge-b/b2/native", json={}).json()
    assert native["raw_marker_in_requests"] is True
    assert native["measurement"]["requests"] == 2
    assert all(e["kind"] == "call" for e in native["events"])
    assert list_sessions(a.settings.sessions_dir) == []


@pytest.mark.parametrize("thread", ["../a", "session-1", "b1-invalid", "b1-000000000000"])
def test_b_cannot_reference_a_or_missing_session(page, thread):
    app, _, _ = page
    assert request(app, "POST", "/api/challenge-b/b1/compact", json={"thread_id": thread}).status_code == 400


def test_bad_mode_and_provider_errors_are_clear_and_redacted(page):
    app, lab, _ = page
    assert request(app, "POST", "/api/challenge-b/b2/arbitrary", json={}).status_code == 400
    class Broken(FakeToolChatModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("credential-do-not-show")
    lab.model = Broken()
    seeded = lab.seed(execution="provider")
    assert request(app, "POST", "/api/challenge-b/b1/compact", json={"thread_id":seeded["thread_id"]}).status_code == 200
    response = request(app, "POST", "/api/challenge-b/chat", json={"thread_id":seeded["thread_id"],"message":"Tiếp tục"})
    assert response.status_code == 502
    assert "RuntimeError" in response.text
    assert "credential-do-not-show" not in response.text


def test_truncation_does_not_reintroduce_dropped_constraints_or_checkpoint(tmp_path):
    seen = []
    class Recording(FakeToolChatModel):
        def _generate(self, messages, *args, **kwargs):
            seen.extend(messages)
            return super()._generate(messages, *args, **kwargs)
    lab = ChallengeBLab(make_settings(tmp_path), tmp_path / "b")
    thread = lab.seed()["thread_id"]
    original, archive = lab._working(thread).load()
    result = lab.compact(thread)
    active, saved = lab._working(thread).load()
    assert active == [original[0], *original[-4:]]
    assert saved == archive
    assert result["dropped_turns"] == 1
    lab.model = Recording(responses=[AIMessage(content="Thiếu dữ liệu cũ")])
    lab.continue_task(thread)
    serialized = str([m.content for m in seen])
    assert CHECKPOINT_PREFIX not in serialized
    assert "tests/test_refresh.py" not in serialized
    assert "timeout 30s" not in serialized
    assert "DEBUG duplicate" not in serialized


def test_chat_api_shows_context_usage_and_persists_timeline(page):
    app, lab, _ = page
    lab.model = FakeToolChatModel(responses=[AIMessage(content="Chào bạn", usage_metadata={
        "input_tokens": 123, "output_tokens": 8, "total_tokens": 131})])
    created = request(app, "POST", "/api/challenge-b/chat/new", json={"execution":"provider"}).json()
    assert created["usage"]["actual_input_tokens"] == 0
    assert created["context"]["estimated_input_tokens"] > 0
    assert created["context"]["loaded_estimated_tokens"] == 0
    assert created["context"]["state"] == "not_loaded"
    assert created["context"]["provider_context_limit"] is None
    response = request(app, "POST", "/api/challenge-b/chat", json={"thread_id": created["thread_id"], "message": "Chào"})
    assert response.status_code == 200
    data = response.json()
    assert data["usage"]["actual_input_tokens"] == 123
    assert data["usage"]["actual_output_tokens"] == 8
    assert data["context"]["state"] == "ready"
    assert data["context"]["loaded_estimated_tokens"] == data["context"]["estimated_input_tokens"]
    assert data["timeline"][-1]["content"] == "Chào bạn"
    reloaded = request(app, "GET", "/api/challenge-b/chat/" + created["thread_id"]).json()
    assert reloaded == data


def test_chat_truncation_preserves_usage_and_records_before_after_event(page):
    app, lab, _ = page
    lab.model = FakeToolChatModel(responses=[AIMessage(content="Đã nhận", usage_metadata={
        "input_tokens":500,"output_tokens":100,"total_tokens":600})])
    seed = lab.seed(execution="provider")
    lab.send(seed["thread_id"], "Lượt mới")
    before = lab.chat_view(seed["thread_id"])
    data = request(app, "POST", "/api/challenge-b/chat/compact", json={"thread_id":seed["thread_id"],"keep_turns":2}).json()
    assert data["chat"]["context"]["estimated_input_tokens"] < before["context"]["estimated_input_tokens"]
    assert data["chat"]["timeline"][-1]["kind"] == "compact"
    assert data["chat"]["timeline"][-1]["technique"] == "truncation"
    assert data["chat"]["usage"] == before["usage"]
    assert lab.model.calls == 1
    assert "checkpoint" not in data["compact"]


def test_short_truncation_does_not_call_model_or_mutate_context(page):
    app, lab, _ = page
    lab.model = FakeToolChatModel(responses=[AIMessage(content="Chào",usage_metadata={
        "input_tokens":50,"output_tokens":3,"total_tokens":53})])
    created = lab.new_chat(execution="provider")
    before = lab.send(created["thread_id"], "Chào")
    response = request(app,"POST","/api/challenge-b/chat/compact",json={"thread_id":created["thread_id"]})
    assert response.status_code == 400
    assert lab.chat_view(created["thread_id"]) == before
    assert lab.model.calls == 1


@pytest.mark.parametrize("value", [0, 51, True, 1.5, "2"])
def test_truncation_api_rejects_invalid_keep_turns_without_changes(page, value):
    app, lab, _ = page
    created = lab.seed(execution="provider")
    before = snapshot(lab.root)
    response = request(app,"POST","/api/challenge-b/chat/compact",
                       json={"thread_id":created["thread_id"],"keep_turns":value})
    assert response.status_code == 422
    assert snapshot(lab.root) == before
    assert lab.model.calls == 0


@pytest.mark.parametrize("execution", ["offline", "provider"])
def test_truncation_never_builds_provider_model(tmp_path,monkeypatch,execution):
    from dataclasses import replace
    from memory_agent import challenge_b_lab
    def forbidden(*args,**kwargs):
        raise AssertionError("Truncation must not initialize or call a model")
    monkeypatch.setattr(challenge_b_lab,"build_model",forbidden)
    settings=replace(make_settings(tmp_path),api_key="",model_name="")
    lab=ChallengeBLab(settings,tmp_path/"b")
    seed=lab.seed(execution=execution)
    before=lab.chat_view(seed["thread_id"])["usage"]
    result=lab.compact(seed["thread_id"],keep_turns=1)
    assert result["keep_turns"] == 1 and result["dropped_turns"] == 2
    assert lab.chat_view(seed["thread_id"])["usage"] == before
    assert lab.model is None


def test_chat_missing_provider_usage_is_not_shown_as_zero(page):
    app, lab, _ = page
    lab.model = FakeToolChatModel(responses=[AIMessage(content="No usage")])
    created = lab.new_chat()
    data = lab.send(created["thread_id"], "hello")
    assert data["usage"]["actual_input_tokens"] is None
    assert data["usage"]["actual_output_tokens"] is None
    assert data["usage"]["estimated_input_tokens"] > 0


def test_offline_flow_never_builds_or_calls_model_and_needs_no_key(tmp_path, monkeypatch):
    from dataclasses import replace
    from memory_agent import challenge_b_lab
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline must never build a provider model")
    monkeypatch.setattr(challenge_b_lab, "build_model", forbidden)
    settings = replace(make_settings(tmp_path), api_key="", model_name="")
    lab = ChallengeBLab(settings, tmp_path / "offline")
    seed = lab.seed(execution="offline")
    before = lab.chat_view(seed["thread_id"])
    cp = lab.compact(seed["thread_id"])
    assert cp["technique"] == "truncation"
    assert "checkpoint" not in cp
    assert cp["after"]["estimated_tokens"] < cp["before"]["estimated_tokens"]
    assert cp["compaction_requests"] == 0
    data = lab.send(seed["thread_id"], "Tiếp tục: nêu bước kế tiếp và constraints, cách đã thử")
    assert "401" in data["timeline"][-1]["content"]
    assert "timeout 30s" not in data["timeline"][-1]["content"]
    assert data["usage"]["requests"] == 0
    assert data["usage"]["actual_input_tokens"] == 0
    assert data["usage"]["actual_output_tokens"] == 0
    assert data["context"]["estimated_input_tokens"] < before["context"]["estimated_input_tokens"]
    chat = lab.new_chat(execution="offline")
    logs = lab.send(chat["thread_id"], demo.QUESTION)
    assert "3000 lần" in logs["timeline"][-1]["content"]
    assert "auth.log:1" in logs["timeline"][-1]["content"]
    assert "RAW_LOG_ONLY_MARKER" not in json.dumps(logs["timeline"][-1]["events"])
    assert lab.model is None


def test_api_defaults_to_offline_without_calling_injected_model(page):
    app, lab, _ = page
    model = lab.model
    new = request(app, "POST", "/api/challenge-b/chat/new", json={}).json()
    assert new["execution"] == "offline"
    data = request(app, "POST", "/api/challenge-b/chat", json={"thread_id":new["thread_id"], "message":demo.QUESTION}).json()
    assert data["usage"]["requests"] == 0
    assert model.calls == 0
    assert request(app, "POST", "/api/challenge-b/chat/new", json={"execution":"unknown"}).status_code == 422


def test_offline_config_load_does_not_require_model_or_key(tmp_path, monkeypatch):
    from memory_agent import config, paths
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(paths, "ENV_PATH", env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert config.load_settings()[0] is None
    settings, missing = config.load_settings(offline=True)
    assert settings is not None and missing == []
    assert settings.api_key == "" and settings.model_name == ""


def snapshot(directory):
    return {str(p.relative_to(directory)): p.read_bytes() for p in Path(directory).rglob("*") if p.is_file()}


@pytest.mark.parametrize("endpoint", ["/api/challenge-b/memory/clear", "/api/challenge-b/reset"])
def test_clear_b_memory_removes_all_statuses_without_touching_a_or_archives(page, endpoint):
    app, lab, a = page
    a.chat("a-session", "Lịch sử riêng của A")
    a_before = snapshot(Path(a.settings.memory_dir).parent)
    manager = MemoryManager(MarkdownMemoryStore(lab.settings.memory_dir, lab.settings.user_id), lab.settings.user_id)
    old = manager.remember("auth", "B dùng JWT")
    manager.supersede(old["key"], "B dùng cookie")
    other = MarkdownMemoryStore(lab.settings.memory_dir, "other-user")
    other.put(("memory", "other-user", "auth"), "other", {"content": "Giữ nguyên"})
    seeded = lab.seed(execution="offline")
    lab.compact(seeded["thread_id"])
    before = {d: snapshot(lab.root / d) for d in ("sessions", "chat-ui", "logs", "results")}
    assert request(app, "POST", endpoint, json={"execution": "invalid"}).status_code == 422
    assert len(manager.entries(include_superseded=True)) == 2
    response = request(app, "POST", endpoint, json={"execution": "offline"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] and data["deleted"] == 2
    fresh = data["chat"]
    assert fresh["thread_id"] != seeded["thread_id"]
    assert fresh["execution"] == "offline" and fresh["timeline"] == []
    assert fresh["context"]["active"]["serialized_bytes"] == 2
    assert fresh["context"]["loaded_estimated_tokens"] == 0
    assert fresh["context"]["state"] == "not_loaded"
    assert fresh["context"]["estimated_input_tokens"] > 0  # The next input still needs instructions/tools.
    assert request(app, "GET", "/api/challenge-b/chat/" + fresh["thread_id"]).json() == fresh
    assert fresh["usage"]["requests"] == 0
    assert manager.entries(include_superseded=True) == []
    assert "cookie" not in manager.index_text()
    assert other.get(("memory", "other-user", "auth"), "other") is not None
    assert snapshot(Path(a.settings.memory_dir).parent) == a_before
    for directory, files in before.items():
        after = snapshot(lab.root / directory)
        assert all(after[name] == content for name, content in files.items())
    assert lab.model.calls == 0
    assert request(app, "POST", endpoint, json={}).json()["deleted"] == 0


def test_reset_b_context_persists_empty_active_keeps_archive_memory_and_usage(page):
    app, lab, a = page
    a.chat("a-session", "A vẫn giữ context")
    a_before = snapshot(Path(a.settings.memory_dir).parent)
    seed = lab.seed(execution="provider")
    thread = seed["thread_id"]
    lab.compact(thread)
    lab.model = FakeToolChatModel(responses=[AIMessage(content="Giữ lịch sử để đối chiếu", usage_metadata={
        "input_tokens": 123, "output_tokens": 8, "total_tokens": 131})])
    before = lab.send(thread, "OLD_CONTEXT_MARKER")
    _, archive = lab._working(thread).load()
    manager = MemoryManager(MarkdownMemoryStore(lab.settings.memory_dir, lab.settings.user_id), lab.settings.user_id)
    manager.remember("auth", "Memory B cần giữ")
    memory_before = snapshot(lab.root / "memory")
    other = lab.new_chat(execution="offline")
    other_before = lab.chat_view(other["thread_id"])
    response = request(app, "POST", "/api/challenge-b/chat/reset-context", json={"thread_id": thread})
    assert response.status_code == 200
    after = response.json()
    assert after["thread_id"] == thread and after["execution"] == "provider"
    assert lab._working(thread).load() == ([], archive)
    assert after["usage"] == before["usage"]
    assert after["context"]["archive_messages"] == before["context"]["archive_messages"]
    assert after["context"]["state"] == "not_loaded"
    assert after["context"]["loaded_estimated_tokens"] == 0
    assert 0 < after["context"]["estimated_input_tokens"] < before["context"]["estimated_input_tokens"]
    assert after["timeline"][:-1] == before["timeline"]
    assert after["timeline"][-1]["kind"] == "reset"
    assert request(app, "GET", "/api/challenge-b/chat/" + thread).json() == after
    assert lab.chat_view(other["thread_id"]) == other_before
    assert snapshot(lab.root / "memory") == memory_before
    assert snapshot(Path(a.settings.memory_dir).parent) == a_before
    assert lab.model.calls == 1
    # The next real graph invocation must not replay archive/checkpoint/UI events.
    continued = lab.send(thread, "NEW_CONTEXT_MARKER")
    assert continued["context"]["state"] == "ready"
    prompts = json.dumps(continued["timeline"][-1]["prompts"], ensure_ascii=False)
    assert "NEW_CONTEXT_MARKER" in prompts and "Memory B cần giữ" in prompts
    assert "OLD_CONTEXT_MARKER" not in prompts and CHECKPOINT_PREFIX not in prompts


@pytest.mark.parametrize("thread", ["../a", "a-session", "bchat-invalid", "bchat-000000000000"])
def test_reset_context_rejects_other_or_missing_sessions_without_changes(page, thread):
    app, lab, a = page
    before = snapshot(lab.root.parent)
    response = request(app, "POST", "/api/challenge-b/chat/reset-context", json={"thread_id": thread})
    assert response.status_code == 400
    assert snapshot(lab.root.parent) == before


@pytest.mark.parametrize("placement", ["system", "end"])
def test_new_b_chat_does_not_send_previous_chat_history_or_checkpoint(page, placement):
    from dataclasses import replace
    from memory_agent.prompts import BASE_PROMPT
    app, lab, _ = page
    lab.settings = replace(lab.settings, memory_placement=placement)
    previous = lab.seed(execution="offline")["thread_id"]
    lab.compact(previous)
    lab.send(previous, "OLD_CHAT_ONLY_MARKER")
    old_context = lab._working(previous).load()
    lab.model = FakeToolChatModel(responses=[AIMessage(content="Chat riêng")])
    fresh = request(app, "POST", "/api/challenge-b/chat/new", json={"execution": "provider"}).json()
    assert lab._working(fresh["thread_id"]).load() == ([], [])
    assert fresh["context"]["state"] == "not_loaded"
    assert fresh["context"]["loaded_estimated_tokens"] == 0
    assert lab.model.calls == 0
    data = lab.send(fresh["thread_id"], "NEW_CHAT_ONLY_MARKER")
    first_prompts = data["timeline"][-1]["prompts"]
    assert first_prompts[0][0]["role"] == "system"
    assert BASE_PROMPT in first_prompts[0][0]["content"]
    assert data["context"]["state"] == "ready"
    assert data["context"]["loaded_estimated_tokens"] > 0
    prompts = json.dumps(first_prompts, ensure_ascii=False)
    assert "NEW_CHAT_ONLY_MARKER" in prompts
    assert "OLD_CHAT_ONLY_MARKER" not in prompts and CHECKPOINT_PREFIX not in prompts
    assert "DEBUG duplicate" not in prompts and "race.log:7" not in prompts
    assert lab._working(previous).load() == old_context
    # Every subsequent model request must receive the system instructions again.
    second = lab.send(fresh["thread_id"], "SECOND_CHAT_MARKER")
    assert BASE_PROMPT in second["timeline"][-1]["prompts"][0][0]["content"]


def test_full_reset_first_send_reloads_system_without_old_memory_or_history(page):
    from memory_agent.prompts import BASE_PROMPT
    app, lab, a = page
    a_before = snapshot(Path(a.settings.memory_dir).parent)
    manager = MemoryManager(MarkdownMemoryStore(lab.settings.memory_dir, lab.settings.user_id), lab.settings.user_id)
    manager.remember("auth", "OLD_MEMORY_ONLY_MARKER")
    previous = lab.seed(execution="offline")["thread_id"]
    old_context = lab._working(previous).load()
    reset = request(app, "POST", "/api/challenge-b/reset", json={"execution": "provider"}).json()
    fresh = reset["chat"]
    assert reset["deleted"] == 1
    assert fresh["context"]["state"] == "not_loaded"
    assert fresh["context"]["loaded_estimated_tokens"] == 0
    assert fresh["usage"]["requests"] == 0 and lab.model.calls == 0
    lab.model = FakeToolChatModel(responses=[AIMessage(content="Phiên hoàn toàn mới")])
    sent = lab.send(fresh["thread_id"], "FRESH_USER_MARKER")
    prompts = sent["timeline"][-1]["prompts"]
    assert BASE_PROMPT in prompts[0][0]["content"]
    serialized = json.dumps(prompts, ensure_ascii=False)
    assert "FRESH_USER_MARKER" in serialized and "OLD_MEMORY_ONLY_MARKER" not in serialized
    assert "race.log:7" not in serialized and CHECKPOINT_PREFIX not in serialized
    assert sent["context"]["state"] == "ready"
    assert sent["context"]["loaded_estimated_tokens"] > 0
    assert lab._working(previous).load() == old_context
    assert snapshot(Path(a.settings.memory_dir).parent) == a_before
