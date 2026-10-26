"""Windows smoke test using disposable services, never the user's live ports."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import pytest


PROJECT = Path(__file__).resolve().parents[1]
STOP = PROJECT / "stop_web.cmd"


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def wait_listening(port):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if listening(port):
            return
        time.sleep(0.1)
    raise AssertionError(f"Disposable service did not start on {port}")


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("node"), reason="Windows and Node.js required")
def test_stop_wrappers_target_services_keep_data_and_are_repeatable(tmp_path):
    sockets = [socket.socket(), socket.socket()]
    for connection in sockets:
        connection.bind(("127.0.0.1", 0))
    app_port, router_port = [connection.getsockname()[1] for connection in sockets]
    for connection in sockets:
        connection.close()

    # A fake 9Router has the same parent/child layout and restarts crashed children.
    router = tmp_path / "node_modules" / "9router"
    (router / "app").mkdir(parents=True)
    (router / "app" / "server.js").write_text(
        "require('net').createServer(s=>s.end()).listen(Number(process.argv[2]),'127.0.0.1');",
        encoding="utf-8",
    )
    cli = router / "cli.js"
    cli.write_text(
        "const {spawn}=require('child_process');const path=require('path');"
        "function start(){const p=spawn(process.execPath,[path.join(__dirname,'app','server.js'),"
        "process.argv[3]],{stdio:'ignore'});p.on('exit',()=>setTimeout(start,100));}"
        "start();setInterval(()=>{},1000);",
        encoding="utf-8",
    )
    sentinels = []
    for name in ("memory/u1/MEMORY.md", "sessions/s1.md", "challenge-b/sessions/contexts/b.json"):
        path = tmp_path / "data" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("KEEP MEMORY AND HISTORY", encoding="utf-8")
        sentinels.append(path)
    environment = {**os.environ, "PYTHONPATH": str(PROJECT / "src")}
    processes = []

    def launch(args):
        process = subprocess.Popen(args, cwd=PROJECT, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(process)
        return process

    def stop(*extra, wrapper=STOP):
        return subprocess.run(
            ["cmd.exe", "/d", "/c", str(wrapper), "-AppPort", str(app_port),
             "-RouterPort", str(router_port), *extra], cwd=tmp_path,
            capture_output=True, text=True, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW,
        )

    try:
        web = launch([sys.executable, "-m", "uvicorn", "memory_agent.ui.app:app",
                      "--host", "127.0.0.1", "--port", str(app_port)])
        supervisor = launch([shutil.which("node"), str(cli), "--port", str(router_port)])
        wait_listening(app_port)
        wait_listening(router_port)
        preview = stop("-WhatIf")
        assert preview.returncode == 0, preview.stdout + preview.stderr
        assert web.poll() is None and supervisor.poll() is None
        assert listening(app_port) and listening(router_port)

        # Use the BTVN7 wrapper when present; GitHub's project root uses STOP.
        outer = PROJECT.parent / "stop_web.cmd"
        result = stop(wrapper=outer if outer.is_file() else STOP)
        assert result.returncode == 0, result.stdout + result.stderr
        web.wait(timeout=5)
        supervisor.wait(timeout=5)
        time.sleep(0.5)
        assert not listening(app_port) and not listening(router_port)
        repeated = stop()
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr

        unrelated = launch([sys.executable, "-m", "http.server", str(app_port), "--bind", "127.0.0.1"])
        wait_listening(app_port)
        refused = stop()
        assert refused.returncode == 1, refused.stdout + refused.stderr
        assert unrelated.poll() is None and listening(app_port)
        assert all(path.read_text(encoding="utf-8") == "KEEP MEMORY AND HISTORY" for path in sentinels)
    finally:
        for process in processes:
            if process.poll() is None:
                subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=5)
