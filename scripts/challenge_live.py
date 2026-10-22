"""Chạy một bước Challenge A với model thật; mỗi bước chạy bằng process mới."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memory_agent.config import load_settings
from memory_agent.runtime import build_runtime

PROMPTS = {
    1: "Quy ước dự án: Authentication sử dụng JWT. Hãy ghi nhớ cho các phiên sau.",
    2: "Dự án này dùng gì để đăng nhập? Hãy kiểm tra memory trước khi trả lời.",
    3: "Quy ước đăng nhập thay đổi: Authentication sử dụng session cookie thay cho JWT. Hãy thay thế quy ước cũ, giữ lại dấu vết thay đổi.",
    4: "Quy ước đăng nhập hiện hành của dự án là gì? Hãy kiểm tra memory và phân biệt mục cũ đã bị thay thế.",
}
NATURAL_PROMPTS = {
    1: "Bên mình đã chốt cơ chế đăng nhập của dự án là JWT.",
    2: "Dự án mình đang đăng nhập bằng cơ chế nào?",
    3: "Nhóm vừa thống nhất bỏ JWT và chuyển hẳn sang session cookie cho đăng nhập.",
    4: "Hiện tại dự án mình dùng cơ chế đăng nhập nào?",
    5: "Chào bạn, hôm nay mình hơi buồn ngủ.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--natural", action="store_true")
    parser.add_argument("--recheck", action="store_true", help="Chỉ kiểm tra lại trace đã lưu, không gọi API")
    args = parser.parse_args()
    if args.step == 5 and not args.natural:
        parser.error("Bước 5 chỉ có trong bộ --natural.")
    settings, missing = load_settings()
    if missing:
        raise SystemExit("Thiếu cấu hình: " + ", ".join(missing))
    directory = Path(__file__).resolve().parents[1] / "reports" / ("challenge-natural" if args.natural else "challenge-live")
    if args.recheck:
        trace = json.loads((directory / f"trace-{args.step}.json").read_text(encoding="utf-8"))
    else:
        runtime = build_runtime(settings)
        prefix = "natural" if args.natural else "challenge-a"
        prompt = (NATURAL_PROMPTS if args.natural else PROMPTS)[args.step]
        trace = runtime.chat_with_trace(f"{prefix}-s{args.step}", prompt)["trace"]
    calls = [e["name"] for e in trace["events"] if e["kind"] == "call"]
    active = [e for e in trace["entries"] if e["status"] == "active"]
    old_jwt = [e for e in trace["entries"] if "jwt" in e["content"].lower() and "cookie" not in e["content"].lower()]
    replaced = bool(old_jwt) and all(e["status"] == "superseded" and any(
        n["key"] == e["superseded_by"] and "cookie" in n["content"].lower() for n in active
    ) for e in old_jwt)
    checks = {"model_invoked": bool(trace["prompts"]), "fresh_session": trace["history_messages"] == 0}
    if args.step == 1:
        checks.update(wrote_memory="remember" in calls, jwt_stored=any("jwt" in e["content"].lower() for e in active))
    elif args.step == 2:
        checks.update(recalled="recall" in calls, jwt_answer="jwt" in str(trace["reply"]).lower())
    elif args.step == 3:
        checks.update(cookie_active=any("cookie" in e["content"].lower() for e in active),
                      old_preserved=any(e["status"] == "superseded" and e["superseded_by"] for e in trace["entries"]),
                      old_jwt_replaced_by_active_cookie=replaced)
    elif args.step == 4:
        first_context = "\n".join(str(m["content"]) for m in trace["prompts"][0] if m["role"] == "system")
        checks.update(recalled="recall" in calls, cookie_answer="cookie" in str(trace["reply"]).lower(),
                      cookie_in_initial_context="cookie" in first_context.lower(),
                      old_jwt_replaced_by_active_cookie=replaced,
                      old_keys_absent_from_index=bool(old_jwt) and all(e["key"] not in trace["memory_before"] for e in old_jwt))
    else:
        checks.update(no_write_proposal=not trace["write_proposed"], memory_unchanged=not trace["memory_changed"])
    summary = {"step": args.step, "model": trace["model"], "thread_id": trace["thread_id"],
               "pid": __import__("os").getpid(), "tools": calls, "checks": checks,
               "passed": all(checks.values()), "reply": trace["reply"],
               "elapsed_seconds": trace["elapsed_seconds"], "usage": trace["usage"]}
    if args.recheck:
        original = json.loads((directory / f"step-{args.step}.json").read_text(encoding="utf-8"))
        summary["pid"] = original["pid"]
        summary["validation_note"] = "Kiểm tra theo key/status/liên kết superseded_by; câu 'cookie thay JWT' vẫn có thể nhắc JWT. Không gọi lại model."
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"step-{args.step}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.recheck:
        (directory / f"trace-{args.step}.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
