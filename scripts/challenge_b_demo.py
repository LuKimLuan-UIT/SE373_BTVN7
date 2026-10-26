"""Offline evidence: real graph/tools + scripted model; no API call or credentials.

python scripts/challenge_b_demo.py --output reports/challenge-b
This verifies the harness/continuation contract, NOT real LLM reasoning quality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from memory_agent.code_mode import build_code_tools
from memory_agent.challenge_b_scenarios import FIXTURES, QUESTION, CODE, long_history
from memory_agent.config import Settings
from memory_agent.context import CHECKPOINT_PREFIX, WorkingContext
from memory_agent.graph import build_agent
from memory_agent.memory.history import write_history
from memory_agent.memory.lifecycle import MemoryManager
from memory_agent.memory.store import MarkdownMemoryStore
from memory_agent.memory_tools import build_memory_tools
from memory_agent.metrics import input_metrics, reduction
from memory_agent.runtime import Runtime

CHECKPOINT = {
    "goal": "Điều tra refresh-token race condition",
    "current_state": "Lỗi 401 khi hai request refresh đồng thời vẫn chưa được sửa.",
    "constraints": ["Giữ nguyên API /refresh và không log token."],
    "findings": ["auth.py:184 hai request đọc cùng refresh token; race.log:7 xác nhận interleaving."],
    "failed_attempts": ["Tăng timeout lên 30s không giảm lỗi 401; loại trừ timeout."],
    "files": ["auth.py:184", "tests/test_refresh.py", "race.log:7"],
    "next_action": "Thêm test hai request refresh đồng thời trong tests/test_refresh.py, rồi kiểm tra lock theo session.",
    "open_questions": ["Chưa xác nhận lock theo session có giải quyết race giữa các process hay không."],
}


class DemoModel(BaseChatModel):
    mode: str

    @property
    def _llm_type(self):
        return "challenge-b-offline-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.mode == "compact":
            reply = AIMessage(content=json.dumps(CHECKPOINT, ensure_ascii=False))
        elif self.mode == "continue":
            checkpoint = next(json.loads(str(m.content)[len(CHECKPOINT_PREFIX):]) for m in messages
                              if str(m.content).startswith(CHECKPOINT_PREFIX))
            assert "timeout" in " ".join(checkpoint["failed_attempts"])
            assert "401" in checkpoint["current_state"]
            assert "không log token" in " ".join(checkpoint["constraints"])
            assert "race.log:7" in " ".join(checkpoint["findings"])
            reply = AIMessage(content=checkpoint["next_action"])
        elif messages[-1].type != "tool":
            name = "run_code" if self.mode == "code" else "read_all_logs"
            reply = AIMessage(content="", tool_calls=[{
                "name": name, "args": {"code": CODE} if self.mode == "code" else {}, "id": "analysis-1"}])
        else:
            if self.mode == "code":
                findings = json.loads(messages[-1].content)
                winner = findings["error_summary"][0]
            else:
                # Deterministic fake model parses native raw output for the control.
                data = json.loads(messages[-1].content)
                counts, evidence, files = {}, {}, {}
                for name, content in data.items():
                    for line, text in enumerate(content.splitlines(), 1):
                        match = re.search(r"\bERROR\s+([\w-]+)\s+(.*)", text)
                        if match:
                            kind = match[1]
                            counts[kind] = counts.get(kind, 0) + 1
                            files.setdefault(kind, set()).add(name)
                            evidence.setdefault(kind, {}).setdefault(name, {"file": name, "line": line, "message": match[2][:120]})
                kind = sorted(counts, key=lambda k: (-counts[k], k))[0]
                winner = {"type": kind, "count": counts[kind], "files": sorted(files[kind]),
                          "evidence": list(evidence[kind].values())[:2]}
            reply = AIMessage(content=json.dumps(winner, ensure_ascii=False))
        return ChatResult(generations=[ChatGeneration(message=reply)])


def settings_at(path, logs=None):
    return Settings(api_key="offline-placeholder", model_name="offline-scripted", base_url=None,
                    user_id="demo-user", memory_dir=str(path / "memory"),
                    sessions_dir=str(path / "sessions"), agents_path=str(path / "AGENTS.md"),
                    enable_long_term_memory=True, memory_placement="system", model_call_limit=8,
                    code_mode_logs_dir=str(logs) if logs else None)


def runtime_at(settings, model, extra_tools=()):
    store = MarkdownMemoryStore(settings.memory_dir, settings.user_id)
    manager = MemoryManager(store, settings.user_id)
    return Runtime(settings, store, manager,
                   build_agent(model, settings, manager=manager, extra_tools=extra_tools), model)


def run_demo(output, *, scale=80):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Workspace-local temporary data: không dùng memory/session cá nhân.
    with tempfile.TemporaryDirectory(prefix="b-demo-", dir=output) as directory:
        temp = Path(directory)
        settings = settings_at(temp / "b1")
        active = long_history()
        working = WorkingContext(settings.sessions_dir, "race")
        working.save(active, active)
        write_history(settings.sessions_dir, "race", active)
        runtime = runtime_at(settings, DemoModel(mode="continue"))
        b1 = runtime.compact("race", model=DemoModel(mode="compact"))
        result = runtime.chat_with_trace("race", "Tiếp tục từ bước kế tiếp.")
        assert result["reply"] == CHECKPOINT["next_action"]
        new_active, archive = working.load()
        assert "DEBUG duplicate" not in json.dumps(result["trace"]["prompts"])
        assert any("DEBUG duplicate" in str(m.content) for m in archive)
        assert any("Policy:" in str(m.content) for m in new_active)
        b1["continuation"] = result["reply"]
        b1["continuation_passed"] = True
        b1["archive_preserved"] = True
        b1["reduction_percent_estimated"] = reduction(b1["before"]["estimated_tokens"], b1["after"]["estimated_tokens"])
        tools = build_memory_tools(runtime.manager)
        b1["continuation_input"] = input_metrics(result["trace"]["prompts"], tools, result["trace"]["usage"])
        b1["cost_note"] = "Compaction input is an EXTRA request, reported separately; context reduction is not total-cost reduction."

        logs = temp / "logs"
        logs.mkdir()
        for file in sorted((FIXTURES / "logs").glob("*.log")):
            (logs / file.name).write_text((file.read_text(encoding="utf-8").rstrip() + "\n") * scale, encoding="utf-8")

        @tool
        def read_all_logs() -> str:
            """Baseline only: read every log file verbatim and return raw contents."""
            return json.dumps({p.name: p.read_text(encoding="utf-8") for p in sorted(logs.glob("*.log"))})

        measurements, replies = {}, {}
        for mode in ("native", "code"):
            setting = settings_at(temp / mode, logs if mode == "code" else None)
            rt = runtime_at(setting, DemoModel(mode=mode), (read_all_logs,) if mode == "native" else ())
            data = rt.chat_with_trace(mode, QUESTION)
            toolset = [*build_memory_tools(rt.manager), *(build_code_tools(logs) if mode == "code" else [read_all_logs])]
            measurements[mode] = input_metrics(data["trace"]["prompts"], toolset, data["trace"]["usage"])
            replies[mode] = json.loads(data["reply"])
            prompts = json.dumps(data["trace"]["prompts"], ensure_ascii=False)
            assert ("RAW_LOG_ONLY_MARKER" in prompts) == (mode == "native")
            if mode == "code":
                assert not any(p.read_text(encoding="utf-8").strip() in prompts for p in logs.glob("*.log"))
                (output / "code-prompts.json").write_text(json.dumps(data["trace"]["prompts"], ensure_ascii=False, indent=2), encoding="utf-8")
        expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
        for reply in replies.values():
            assert reply["type"] == "refresh_timeout"
            assert reply["count"] == expected["counts"]["refresh_timeout"] * scale
            assert reply["files"] == expected["winner_files"]
            for evidence in reply["evidence"]:
                assert evidence["line"] == expected["winner_evidence"][evidence["file"]]
        b2 = {"question": QUESTION, "fixture_scale": scale, "measurements": measurements,
              "answers": replies, "correct": True, "raw_log_absent_from_code_requests": True,
              "reduction_percent_estimated": reduction(measurements["native"]["estimated_input_tokens"],
                                                       measurements["code"]["estimated_input_tokens"])}
        report = {"mode": "offline scripted model; not real-provider validation", "b1": b1, "b2": b2}
        (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/challenge-b")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_demo(args.output), ensure_ascii=False, indent=2))
