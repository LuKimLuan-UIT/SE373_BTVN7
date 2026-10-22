"""Khởi động lại tiến trình web bằng helper độc lập, giữ nguyên dữ liệu."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


def schedule_restart(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Cổng web không hợp lệ.")
    project = Path(__file__).resolve().parents[2]
    logs = project / "data" / "service-logs"
    logs.mkdir(parents=True, exist_ok=True)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS} if os.name == "nt" else {"start_new_session": True}
    with (logs / "restart-helper.log").open("a", encoding="utf-8") as output:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--parent-pid", str(os.getpid()), "--port", str(port)],
            cwd=project, stdin=subprocess.DEVNULL, stdout=output, stderr=output, **options,
        )


def restart_parent(parent_pid: int, port: int) -> None:
    project = Path(__file__).resolve().parents[2]
    time.sleep(2)  # Cho HTTP response quay về trình duyệt trước khi dừng server.
    os.kill(parent_pid, signal.SIGTERM)
    for _ in range(100):
        with socket.socket() as connection:
            connection.settimeout(0.2)
            if connection.connect_ex(("127.0.0.1", port)) != 0:
                break
        time.sleep(0.1)
    else:
        raise RuntimeError("Cổng cũ chưa đóng; không tạo thêm server.")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    logs = project / "data" / "service-logs"
    options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS} if os.name == "nt" else {"start_new_session": True}
    with (logs / "memory-agent.out.log").open("a", encoding="utf-8") as output, (logs / "memory-agent.err.log").open("a", encoding="utf-8") as errors:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "memory_agent.ui.app:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=project, env=environment, stdin=subprocess.DEVNULL, stdout=output, stderr=errors, **options,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--port", type=int, required=True)
    arguments = parser.parse_args()
    restart_parent(arguments.parent_pid, arguments.port)
