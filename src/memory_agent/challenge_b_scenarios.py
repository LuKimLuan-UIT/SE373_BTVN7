"""Synthetic scenarios shared by CLI verification and the separate Challenge B lab."""
from pathlib import Path
from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .paths import PROJECT_ROOT

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "challenge_b"
QUESTION = "Quét tất cả file log: loại lỗi nào xuất hiện nhiều nhất, chính xác bao nhiêu lần, ở những file nào? Đưa bằng chứng file và số dòng."
CODE = 'rows = read_logs()\nerrors = select(rows, level="ERROR")\nresult = summarize(errors, top=5)'
B2_DATASET = "synthetic-10000-v1"
B2_TOTAL_LINES = 10000
B2_EXPECTED_COUNTS = {"refresh_timeout": 3000, "db_connection": 1800, "invalid_token": 600}


def long_history():
    return [
        SystemMessage(content="Policy: không xuất secrets; trả lời bằng tiếng Việt."),
        HumanMessage(content="Điều tra race refresh. Giữ nguyên API /refresh và không log token."),
        AIMessage(content="", tool_calls=[{"name": "read_debug", "args": {}, "id": "debug-1"}]),
        ToolMessage(content=("DEBUG duplicate irrelevant output\n" * 1600) +
                    "race.log:7 requests A and B read same token; auth.py:184 interleaving confirmed",
                    tool_call_id="debug-1", name="read_debug"),
        AIMessage(content="Tăng timeout 30s không hiệu quả; lỗi 401 chưa sửa. Tiếp theo thêm test hai request refresh đồng thời trong tests/test_refresh.py; kiểm tra session lock."),
    ]


def prepare_logs(destination, scale=80):
    """Reproducible generated logs, not personal/application logs."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for source in sorted((FIXTURES / "logs").glob("*.log")):
        (destination / source.name).write_text(
            (source.read_text(encoding="utf-8").rstrip() + "\n") * scale, encoding="utf-8")
    return destination


def prepare_large_logs(destination):
    """Exactly 10,000 synthetic lines; stable counts, varied request IDs/times.

    The original small fixtures remain unchanged for historical CLI experiments.
    Both live Code Mode and raw baseline read these same four generated files.
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    patterns = {
        "auth.log": ["refresh_timeout"] * 15 + ["invalid_token"] * 5 + ["heartbeat"] * 5,
        "billing.log": ["db_connection", "refresh_timeout"] + ["db_connection"] * 11
                       + ["refresh_timeout"] * 4 + ["heartbeat"] * 8,
        "worker.log": ["refresh_timeout"] * 10 + ["db_connection"] * 6
                      + ["invalid_token"] + ["queue_delay"] * 8,
        "irrelevant.log": ["heartbeat"] * 25,
    }
    messages = {
        "refresh_timeout": ("ERROR", "Refresh request timed out"),
        "db_connection": ("ERROR", "Database connection refused"),
        "invalid_token": ("ERROR", "Token signature rejected"),
        "heartbeat": ("INFO", "RAW_LOG_ONLY_MARKER normal heartbeat"),
        "queue_delay": ("WARN", "Queue delay observed"),
    }
    start = datetime(2026, 10, 27, tzinfo=timezone.utc)
    for file_index, (name, pattern) in enumerate(patterns.items()):
        lines = []
        for index in range(2500):
            kind = pattern[index % len(pattern)]
            level, message = messages[kind]
            timestamp = (start + timedelta(seconds=file_index * 2500 + index)).isoformat()
            lines.append(f"{timestamp} {level} {kind} {message} request_id=demo-{file_index}-{index + 1:04d}\n")
        (destination / name).write_text("".join(lines), encoding="utf-8")
    return destination


def truncation_history():
    """Three complete turns: original constraints/log evidence sit in the oldest turn."""
    return [*long_history(),
            HumanMessage(content="Ghi nhận tình trạng hiện tại của công việc."),
            AIMessage(content="Lỗi 401 chưa được xử lý; chưa có thay đổi code."),
            HumanMessage(content="Chuẩn bị tiếp tục từ đoạn trao đổi gần nhất."),
            AIMessage(content="Chờ yêu cầu tiếp theo.")]
