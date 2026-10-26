"""B1/B2: real LangGraph/tool routing, controlled model, archive and request spy."""
import importlib.util
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from memory_agent.code_mode import LogRuntime, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, build_code_tools, execute_code
from memory_agent.context import CHECKPOINT_PREFIX, Checkpoint, WorkingContext
from memory_agent.memory.history import load_history
from memory_agent.metrics import input_metrics, reduction
from memory_agent.sessions import delete_session
from tests.test_agent_memory import FakeToolChatModel

spec = importlib.util.spec_from_file_location("challenge_b_demo", Path(__file__).resolve().parents[1] / "scripts" / "challenge_b_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_compact_continues_with_original_constraints_and_archive_after_restart(tmp_path):
    settings = demo.settings_at(tmp_path)
    Path(settings.agents_path).write_text("Policy project: tiếng Việt, giữ API /refresh", encoding="utf-8")
    original = demo.long_history()
    working = WorkingContext(settings.sessions_dir, "race")
    working.save(original, original)
    runtime = demo.runtime_at(settings, demo.DemoModel(mode="continue"))
    result = runtime.compact("race", model=demo.DemoModel(mode="compact"))
    assert result["after"]["serialized_bytes"] < result["before"]["serialized_bytes"]
    assert result["compaction_requests"] == 1
    assert result["compaction_input_estimate"] > 0
    assert result["compaction_usage"] == []
    cp = Checkpoint.model_validate(result["checkpoint"])
    assert "401" in cp.current_state
    assert "timeout" in cp.failed_attempts[0]
    assert "race.log:7" in cp.findings[0]
    active, archive = WorkingContext(settings.sessions_dir, "race").load()
    assert [m.model_dump() for m in archive] == [m.model_dump() for m in original]
    assert active[0].content == original[0].content
    assert active[1].content == original[1].content
    assert not any(m.type == "tool" for m in active)
    restarted = demo.runtime_at(settings, demo.DemoModel(mode="continue"))
    data = restarted.chat_with_trace("race", "Tiếp tục")
    assert data["reply"] == cp.next_action
    sent = json.dumps(data["trace"]["prompts"], ensure_ascii=False)
    assert "Policy project" in sent
    assert "DEBUG duplicate" not in sent
    assert "Tăng timeout lên 30s không giảm" in sent
    _, archived_after = working.load()
    assert len(archived_after) == len(original) + 2
    assert archived_after[-2].content == "Tiếp tục"
    assert len(load_history(settings.sessions_dir, "race")) >= 4


@pytest.mark.parametrize("response", ["not json", "{}", json.dumps({**demo.CHECKPOINT, "next_action": " " * 15}),
                                      json.dumps({**demo.CHECKPOINT, "failed_attempts": [""]})])
def test_invalid_checkpoint_does_not_mutate_context(tmp_path, response):
    working = WorkingContext(tmp_path, "race")
    original = demo.long_history()
    working.save(original, original)
    before = working.path.read_bytes()
    with pytest.raises(ValueError, match="checkpoint"):
        working.compact(FakeToolChatModel(responses=[AIMessage(content=response)]))
    assert working.path.read_bytes() == before


def test_short_context_is_not_replaced_by_larger_checkpoint(tmp_path):
    working = WorkingContext(tmp_path, "short")
    working.save([HumanMessage(content="hi")], [HumanMessage(content="hi")])
    before = working.path.read_bytes()
    with pytest.raises(ValueError, match="nhỏ hơn"):
        working.compact(demo.DemoModel(mode="compact"))
    assert working.path.read_bytes() == before


def test_compact_missing_session_and_provider_failure(tmp_path):
    working = WorkingContext(tmp_path, "empty")
    with pytest.raises(ValueError, match="chưa có history"):
        working.compact(None)
    working.save(demo.long_history(), demo.long_history())
    before = working.path.read_bytes()
    class Broken:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("model unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        working.compact(Broken())
    assert working.path.read_bytes() == before


def test_recompact_replaces_previous_checkpoint_keeps_user_and_archive(tmp_path):
    working = WorkingContext(tmp_path, "race")
    original = demo.long_history()
    working.save(original, original)
    working.compact(demo.DemoModel(mode="compact"))
    active, archive = working.load()
    active += [AIMessage(content="More debug\n" * 3000)]
    archive += [active[-1]]
    working.save(active, archive)
    working.compact(demo.DemoModel(mode="compact"))
    active, saved = working.load()
    assert sum(str(m.content).startswith(CHECKPOINT_PREFIX) for m in active) == 1
    assert active[1].content == original[1].content
    assert len(saved) == len(archive)


def test_delete_session_also_removes_checkpoint(tmp_path):
    working = WorkingContext(tmp_path, "race")
    working.save(demo.long_history(), demo.long_history())
    delete_session(tmp_path, "race")
    assert working.load() == ([], [])


def test_code_fixture_matches_all_counts_and_exact_evidence():
    data = json.loads(execute_code(demo.FIXTURES / "logs", demo.CODE))
    expected = json.loads((demo.FIXTURES / "expected.json").read_text(encoding="utf-8"))
    assert data["files_scanned"] == expected["files_scanned"]
    assert data["complete"] and not data["errors"]
    assert data["unparsed_lines"] == 1
    assert data["matched_records"] == 9
    assert {g["type"]: g["count"] for g in data["error_summary"]} == expected["counts"]
    winner = data["error_summary"][0]
    assert winner["files"] == expected["winner_files"]
    assert {e["file"]: e["line"] for e in winner["evidence"]} == expected["winner_evidence"]
    for group in data["error_summary"]:
        for evidence in group["evidence"]:
            source = (demo.FIXTURES / "logs" / evidence["file"]).read_text(encoding="utf-8").splitlines()
            assert evidence["message"] in source[evidence["line"] - 1]


@pytest.mark.parametrize("code", [
    "import os", 'result = open("../.env")', 'result = __import__("os")',
    'result = read_logs.__globals__', 'while True: pass',
    'rows = read_logs()\nresult = rows', 'rows = read_logs()\nresult = select(rows)',
    'result = read_logs("../")', 'rows = read_logs()\nresult = summarize(rows, top=99)',
    'result = eval("1+1")', 'result = read_logs()\nresult = read_logs()',
    "#" * 2001,
])
def test_runtime_rejects_ungranted_code_without_raw_output(code):
    tool = build_code_tools(demo.FIXTURES / "logs")[0]
    result = json.loads(tool.invoke({"code": code}))
    assert result["ok"] is False
    assert "RAW_LOG_ONLY_MARKER" not in json.dumps(result)


def test_runtime_reports_bad_files_and_ignores_other_extensions_and_subdirectories(tmp_path):
    (tmp_path / "good.log").write_text("ERROR refresh_timeout timeout\n", encoding="utf-8")
    (tmp_path / "bad.log").write_bytes(b"\xff\xfe")
    (tmp_path / ".env").write_text("ERROR secret DO_NOT_READ", encoding="utf-8")
    (tmp_path / "child").mkdir()
    (tmp_path / "child" / "hidden.log").write_text("ERROR secret DO_NOT_READ", encoding="utf-8")
    data = json.loads(execute_code(tmp_path, demo.CODE))
    assert data["files_scanned"] == 1
    assert data["matched_records"] == 1
    assert not data["complete"]
    assert data["errors"] == [{"file": "bad.log", "error": "UnicodeDecodeError"}]
    assert "DO_NOT_READ" not in json.dumps(data)


def test_runtime_reports_permission_error(tmp_path, monkeypatch):
    (tmp_path / "denied.log").write_text("ERROR secret PRIVATE_CONTENT", encoding="utf-8")
    def denied(*args):
        raise PermissionError("PRIVATE_CONTENT")
    monkeypatch.setattr(LogRuntime, "_read_bounded", denied)
    result = json.loads(execute_code(tmp_path, demo.CODE))
    assert not result["complete"]
    assert result["errors"][0]["error"] == "PermissionError"
    assert "PRIVATE_CONTENT" not in json.dumps(result)


def test_runtime_blocks_resolved_path_escape(tmp_path, monkeypatch):
    path = tmp_path / "escape.log"
    path.write_text("ERROR secret PRIVATE_CONTENT", encoding="utf-8")
    real_resolve = Path.resolve
    def resolve(p, *args, **kwargs):
        if p.name == "escape.log":
            return tmp_path.parent / "outside.log"
        return real_resolve(p, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    result = json.loads(execute_code(tmp_path, demo.CODE))
    assert result["files_scanned"] == 0
    assert not result["complete"]
    assert "PRIVATE_CONTENT" not in json.dumps(result)


def test_runtime_bounds_input_time_and_output(tmp_path):
    (tmp_path / "large.log").write_bytes(b"x" * (MAX_INPUT_BYTES + 1))
    data = json.loads(execute_code(tmp_path, demo.CODE))
    assert not data["complete"] and data["files_scanned"] == 0
    with pytest.raises(ValueError, match="thời gian"):
        LogRuntime(tmp_path, seconds=-1).read_logs()
    (tmp_path / "large.log").unlink()
    (tmp_path / "long.log").write_text(("ERROR huge_message " + "x" * 1000 + "\n") * 100, encoding="utf-8")
    output = execute_code(tmp_path, demo.CODE)
    data = json.loads(output)
    assert len(output.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert len(data["error_summary"][0]["evidence"][0]["message"]) <= 120
    assert data["error_summary"][0]["count"] == 100


def test_agent_tools_and_native_baseline_all_request_metrics(tmp_path):
    report = demo.run_demo(tmp_path / "report")
    assert report["b1"]["continuation_passed"]
    b2 = report["b2"]
    assert b2["correct"] and b2["raw_log_absent_from_code_requests"]
    assert b2["measurements"]["native"]["requests"] == 2
    assert b2["measurements"]["code"]["requests"] == 2
    assert b2["measurements"]["code"]["actual_input_tokens"] is None
    assert b2["reduction_percent_estimated"] > 0


def test_usage_must_cover_all_requests():
    assert reduction(0, 2) is None
    assert reduction(None, 2) is None
    assert input_metrics([[{}], [{}]], usage=[{"input_tokens": 20}])["actual_input_tokens"] is None
    result = input_metrics([[{}], [{}]], usage=[{"input_tokens": 20}, {"input_tokens": 30}])
    assert result["actual_input_tokens"] == 50
    assert result["usage_field"] == "usage_metadata.input_tokens"


def test_web_compact_endpoint_preserves_context_and_rejects_empty_session(tmp_path, monkeypatch):
    import importlib
    from tests.test_maintenance import request
    module = importlib.import_module("memory_agent.ui.app")
    settings = demo.settings_at(tmp_path)
    runtime = demo.runtime_at(settings, demo.DemoModel(mode="compact"))
    working = WorkingContext(settings.sessions_dir, "race")
    working.save(demo.long_history(), demo.long_history())
    monkeypatch.setattr(module, "_state", {"runtime": runtime})
    assert request(module, "POST", "/api/compact", json={"thread_id": "empty"}).status_code == 400
    response = request(module, "POST", "/api/compact", json={"thread_id": "race"})
    assert response.status_code == 200
    assert response.json()["checkpoint"]["next_action"] == demo.CHECKPOINT["next_action"]


def test_code_mode_configuration_defaults_off(tmp_path, monkeypatch):
    from memory_agent import config, paths
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=fake\nMODEL_NAME=fake\n", encoding="utf-8")
    monkeypatch.setattr(paths, "ENV_PATH", env_path)
    monkeypatch.delenv("CODE_MODE_LOGS_DIR", raising=False)
    assert config.load_settings()[0].code_mode_logs_dir is None
    monkeypatch.setenv("CODE_MODE_LOGS_DIR", str(demo.FIXTURES / "logs"))
    assert config.load_settings()[0].code_mode_logs_dir == str(demo.FIXTURES / "logs")
