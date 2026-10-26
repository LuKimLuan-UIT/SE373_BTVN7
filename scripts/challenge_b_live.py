"""Optional provider verification; isolates all memory/session data in a temporary directory.

Uses model/credential only from existing Settings. Never prints client config/errors.
python scripts/challenge_b_live.py --output reports/challenge-b-live
"""
from dataclasses import replace
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from langchain_core.tools import tool
from memory_agent.config import load_settings
from memory_agent.context import WorkingContext
from memory_agent.graph import build_model
from memory_agent.memory_tools import build_memory_tools
from memory_agent.code_mode import build_code_tools
from memory_agent.metrics import input_metrics, reduction
from challenge_b_demo import FIXTURES, QUESTION, long_history, runtime_at


def run_live(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    settings, missing = load_settings()
    report = {"mode": "real provider", "status": "incomplete"}
    if settings is None:
        report["error"] = "Missing configuration: " + ", ".join(missing)
    else:
        report["model"] = settings.model_name
        try:
            with tempfile.TemporaryDirectory(prefix="b-live-", dir=output) as directory:
                temp = Path(directory)
                isolated = replace(settings, memory_dir=str(temp / "memory"),
                                   sessions_dir=str(temp / "sessions"), user_id="challenge-b-live",
                                   code_mode_logs_dir=None)
                model = build_model(isolated, timeout=25, max_retries=0)
                rt = runtime_at(isolated, model)
                history = long_history()
                working = WorkingContext(isolated.sessions_dir, "race")
                working.save(history, history)
                report["stage"] = "B1 compact"
                b1 = rt.compact("race")
                report["b1"] = b1
                cp = b1["checkpoint"]
                # Identifiers are language-independent; human review still needed for semantics.
                failed = " ".join(cp["failed_attempts"]).lower()
                b1["checkpoint_checks"] = {
                    "unresolved_401": "401" in cp["current_state"],
                    "api_constraint": "/refresh" in " ".join(cp["constraints"]),
                    "failed_timeout_attempt": "timeout" in failed or "thời gian chờ" in failed,
                    "next_action_file": "tests/test_refresh.py" in cp["next_action"],
                }
                report["stage"] = "B1 continuation"
                continued = rt.chat_with_trace("race", "Tiếp tục: nêu bước kế tiếp, constraints và cách đã thử không hiệu quả. Chưa cần thực thi.")
                b1["continuation_reply"] = continued["reply"]
                b1["continuation_prompts"] = continued["trace"]["prompts"]
                b1["continuation_input"] = input_metrics(continued["trace"]["prompts"],
                    build_memory_tools(rt.manager), continued["trace"]["usage"])
                b1["continuation_checks"] = {
                    "next_action_file": "tests/test_refresh.py" in continued["reply"],
                    "raw_debug_absent": "DEBUG duplicate" not in json.dumps(continued["trace"]["prompts"]),
                }
                b1["identifier_checks_passed"] = all(b1["checkpoint_checks"].values()) and all(b1["continuation_checks"].values())

                logs = temp / "logs"
                logs.mkdir()
                for source in sorted((FIXTURES / "logs").glob("*.log")):
                    (logs / source.name).write_text((source.read_text(encoding="utf-8").rstrip() + "\n") * 80, encoding="utf-8")
                @tool
                def read_all_logs() -> str:
                    """Baseline only: read every log file verbatim and return raw contents."""
                    return json.dumps({p.name: p.read_text(encoding="utf-8") for p in sorted(logs.glob("*.log"))})

                b2 = {"question": QUESTION, "fixture_scale": 80, "runs": {}}
                report["b2"] = b2
                for mode in ("code", "native"):
                    report["stage"] = "B2 " + mode
                    setting = replace(isolated, sessions_dir=str(temp / mode),
                                      code_mode_logs_dir=str(logs) if mode == "code" else None)
                    runtime = runtime_at(setting, model, (read_all_logs,) if mode == "native" else ())
                    data = runtime.chat_with_trace(mode, QUESTION)
                    tools = [*build_memory_tools(runtime.manager), *(build_code_tools(logs) if mode == "code" else [read_all_logs])]
                    measurement = input_metrics(data["trace"]["prompts"], tools, data["trace"]["usage"])
                    run = {"measurement": measurement, "reply": data["reply"], "events": data["trace"]["events"]}
                    run["answer_checks"] = {
                        "winner_type": "refresh_timeout" in str(data["reply"]),
                        "expected_count": "400" in str(data["reply"]),
                        "all_files": all(f in str(data["reply"]) for f in ["auth.log", "billing.log", "worker.log"]),
                    }
                    if mode == "native":
                        # Do not publish all raw baseline results again in the report.
                        run.pop("events")
                    b2["runs"][mode] = run
                    assert any(e["kind"] == "call" and e["name"] == ("run_code" if mode == "code" else "read_all_logs")
                               for e in data["trace"]["events"])
                    if mode == "code":
                        assert "RAW_LOG_ONLY_MARKER" not in json.dumps(data["trace"]["prompts"])
                        for event in data["trace"]["events"]:
                            if event["kind"] == "result" and event["name"] == "run_code":
                                findings = json.loads(event["content"])
                                assert findings["error_summary"][0]["count"] == 400
                                assert findings["files_scanned"] == 4
                        run["raw_log_absent_from_requests"] = True
                native = b2["runs"]["native"]["measurement"]
                code = b2["runs"]["code"]["measurement"]
                b2["reduction_percent_actual"] = reduction(native["actual_input_tokens"], code["actual_input_tokens"])
                b2["reduction_percent_estimated"] = reduction(native["estimated_input_tokens"], code["estimated_input_tokens"])
                all_checks = b1["identifier_checks_passed"] and all(
                    all(run["answer_checks"].values()) for run in b2["runs"].values())
                report["status"] = ("passed identifier/count checks; review replies for full semantics" if all_checks
                                    else "completed with failed quality checks; review recorded replies")
        except Exception as exc:
            report["error_type"] = type(exc).__name__
            report["error"] = "Provider/check failed at recorded stage; exception text omitted to protect client details."
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/challenge-b-live")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = run_live(args.output)
    # Compact progress only; review complete artifacts locally.
    print(json.dumps({k: result[k] for k in ("mode", "status", "stage", "error_type", "error") if k in result}, ensure_ascii=False))
    raise SystemExit(0 if result["status"].startswith(("passed", "completed")) else 1)
