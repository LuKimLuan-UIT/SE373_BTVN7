"""Large synthetic B2 corpus, independently counted and shared by both paths."""
from collections import Counter
import json

from memory_agent.challenge_b_scenarios import prepare_large_logs, CODE
from memory_agent.code_mode import execute_code
from memory_agent.challenge_b_lab import ChallengeBLab
from tests.test_agent_memory import make_settings
from tests.test_challenge_b import demo


def test_exact_10000_lines_match_independent_golden_counts_and_evidence(tmp_path):
    root = prepare_large_logs(tmp_path / "logs")
    files = sorted(root.glob("*.log"))
    assert len(files) == 4
    expected = {"refresh_timeout": 3000, "db_connection": 1800, "invalid_token": 600}
    raw = {p.name: p.read_text(encoding="utf-8") for p in files}
    assert all(len(text.splitlines()) == 2500 for text in raw.values())
    counts = Counter(line.split()[2] for text in raw.values() for line in text.splitlines()
                     if line.split()[1] == "ERROR")
    assert counts == expected
    findings = json.loads(execute_code(root, CODE))
    assert findings["lines_scanned"] == 10000 and findings["files_scanned"] == 4
    assert findings["complete"] and findings["unparsed_lines"] == 0
    assert findings["matched_records"] == 5400
    assert {g["type"]: g["count"] for g in findings["error_summary"]} == expected
    assert findings["error_summary"][0]["files"] == ["auth.log", "billing.log", "worker.log"]
    for group in findings["error_summary"]:
        for evidence in group["evidence"]:
            original = raw[evidence["file"]].splitlines()[evidence["line"] - 1]
            assert evidence["message"] in original
    assert "RAW_LOG_ONLY_MARKER" not in json.dumps(findings)
    assert len(json.dumps(findings).encode()) < 2000
    prepare_large_logs(root)
    assert {p.name: p.read_text(encoding="utf-8") for p in files} == raw


def test_native_and_code_read_identical_large_data_with_bounded_findings(tmp_path):
    lab = ChallengeBLab(make_settings(tmp_path), tmp_path / "b")
    lab.model = demo.DemoModel(mode="code")
    code = lab.analyze("code")
    assert code["golden_counts_match"] and code["fixture_lines"] == 10000
    assert code["raw_marker_in_requests"] is False
    lab.model = demo.DemoModel(mode="native")
    native = lab.analyze("native")
    assert native["dataset"] == code["dataset"]
    assert json.loads(native["reply"])["count"] == 3000
    assert native["raw_marker_in_requests"] is True
    assert native["measurement"]["estimated_input_tokens"] > code["measurement"]["estimated_input_tokens"]
