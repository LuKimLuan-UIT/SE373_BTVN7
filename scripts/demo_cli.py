"""CLI demo trí nhớ persistent — chạy nhanh trong terminal để thấy rõ khác biệt.

Ví dụ:
    python scripts/demo_cli.py chat --thread s1 "Dự án này dùng JWT để đăng nhập"
    python scripts/demo_cli.py chat --thread s2 "Dự án này dùng gì để đăng nhập?"   # session khác, vẫn nhớ
    python scripts/demo_cli.py chat --thread s1 "Chuyển sang session cookie nhé"      # quy ước đổi
    python scripts/demo_cli.py context                                             # in context đã inject
    python scripts/demo_cli.py memory                                              # xem memory
    python scripts/demo_cli.py threads                                             # liệt kê session
    python scripts/demo_cli.py reset                                               # xoá toàn bộ session
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Windows: console mặc định dùng cp1252, in tiếng Việt sẽ lỗi.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from memory_agent.config import load_settings  # noqa: E402
from memory_agent.runtime import build_runtime, injected_context  # noqa: E402
from memory_agent.sessions import delete_session, list_sessions  # noqa: E402


def _settings_or_exit():
    settings, missing = load_settings()
    if settings is None:
        print(f"Thiếu cấu hình trong .env: {', '.join(missing)}")
        raise SystemExit(1)
    return settings


def cmd_chat(args: argparse.Namespace) -> int:
    settings = _settings_or_exit()
    runtime = build_runtime(settings)
    print(runtime.chat(args.thread, args.message))
    return 0


def cmd_threads(args: argparse.Namespace) -> int:
    settings = _settings_or_exit()
    sessions = list_sessions(settings.sessions_dir)
    if not sessions:
        print("Chưa có session nào.")
        return 0
    for session in sessions:
        print(f"- {session.thread_id}  {session.title}  ({session.updated_at or 'chưa cập nhật'})")
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    settings = _settings_or_exit()
    runtime = build_runtime(settings)
    print("=== MEMORY.md (index — luôn nạp vào context) ===")
    print(runtime.manager.index_text())
    print("=== Chi tiết các mục ===")
    entries = runtime.manager.entries()
    if not entries:
        print("Chưa có mục memory nào.")
        return 0
    for entry in entries:
        mark = "" if entry.is_active else f"  [superseded_by={entry.superseded_by}]"
        print(f"- ({entry.topic}) {entry.content} — key={entry.key}{mark}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    """In ra phần context thực sự được inject vào model (kiểm chứng theo slide)."""
    settings = _settings_or_exit()
    runtime = build_runtime(settings)
    print(injected_context(settings, runtime.manager))
    return 0


def cmd_compact(args: argparse.Namespace) -> int:
    runtime = build_runtime(_settings_or_exit())
    try:
        print(json.dumps(runtime.compact(args.thread), ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(str(exc))
        return 1


def cmd_reset(args: argparse.Namespace) -> int:
    settings = _settings_or_exit()
    for session in list_sessions(settings.sessions_dir):
        delete_session(settings.sessions_dir, session.thread_id)
    print("Đã xoá toàn bộ session (memory dài hạn giữ nguyên).")
    return 0


def cmd_forget(args: argparse.Namespace) -> int:
    settings = _settings_or_exit()
    runtime = build_runtime(settings)
    ok = runtime.manager.forget(args.key)
    print(f"Đã quên key={args.key}" if ok else f"Không tìm thấy key={args.key}")
    return 0


def cmd_wipe(args: argparse.Namespace) -> int:
    """Xoá sạch cả session lẫn memory (bắt đầu lại từ đầu)."""
    settings = _settings_or_exit()
    shutil.rmtree(settings.sessions_dir, ignore_errors=True)
    shutil.rmtree(settings.memory_dir, ignore_errors=True)
    print("Đã xoá toàn bộ session và memory.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_chat = sub.add_parser("chat", help="gửi 1 tin nhắn vào 1 session")
    p_chat.add_argument("message")
    p_chat.add_argument("--thread", default="session-1")
    p_chat.set_defaults(func=cmd_chat)

    p_threads = sub.add_parser("threads", help="liệt kê các session")
    p_threads.set_defaults(func=cmd_threads)

    p_memory = sub.add_parser("memory", help="xem index + chi tiết memory")
    p_memory.set_defaults(func=cmd_memory)

    p_context = sub.add_parser("context", help="in phần context sẽ inject vào model")
    p_context.set_defaults(func=cmd_context)

    p_compact = sub.add_parser("compact", help="B1: checkpoint active context, giữ archive")
    p_compact.add_argument("--thread", required=True)
    p_compact.set_defaults(func=cmd_compact)

    p_forget = sub.add_parser("forget", help="quên 1 mục memory theo key")
    p_forget.add_argument("--key", required=True)
    p_forget.set_defaults(func=cmd_forget)

    p_reset = sub.add_parser("reset", help="xoá toàn bộ session")
    p_reset.set_defaults(func=cmd_reset)

    p_wipe = sub.add_parser("wipe", help="xoá cả session lẫn memory")
    p_wipe.set_defaults(func=cmd_wipe)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
