"""Synthetic scenarios shared by CLI verification and the separate Challenge B lab."""
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .paths import PROJECT_ROOT

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "challenge_b"
QUESTION = "Quét tất cả file log: loại lỗi nào xuất hiện nhiều nhất, chính xác bao nhiêu lần, ở những file nào? Đưa bằng chứng file và số dòng."
CODE = 'rows = read_logs()\nerrors = select(rows, level="ERROR")\nresult = summarize(errors, top=5)'


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


def truncation_history():
    """Three complete turns: original constraints/log evidence sit in the oldest turn."""
    return [*long_history(),
            HumanMessage(content="Ghi nhận tình trạng hiện tại của công việc."),
            AIMessage(content="Lỗi 401 chưa được xử lý; chưa có thay đổi code."),
            HumanMessage(content="Chuẩn bị tiếp tục từ đoạn trao đổi gần nhất."),
            AIMessage(content="Chờ yêu cầu tiếp theo.")]
