"""Web UI (FastAPI) của lab: chatbot nhiều session + panel memory.

Cách chạy:
    uv run uvicorn memory_agent.ui.app:app --port 8000

Mở http://localhost:8000 — giao diện chat đơn giản, bên trái là danh sách session,
bên phải là panel memory (index + chi tiết) và context đang inject.
"""

from __future__ import annotations

import uuid
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..config import load_settings
from ..runtime import injected_context, runtime_from_settings
from ..sessions import delete_session, list_sessions, rename_session
from ..tracing import load_trace

app = FastAPI(title="LangGraph Memory Lab")

_state: dict[str, Any] = {}
_chat_lock = threading.RLock()


def get_runtime():
    """Khởi tạo (hoặc lấy lại) runtime cho tiến trình hiện tại."""
    if "runtime" in _state:
        return _state["runtime"]

    settings, missing = load_settings()
    if settings is None:
        raise HTTPException(
            status_code=503,
            detail=f"Thiếu cấu hình trong .env: {', '.join(missing)}. Copy .env.example → .env rồi điền.",
        )

    _state["runtime"] = runtime_from_settings(settings)
    return _state["runtime"]


# ------------------------------------------------------------------ schemas
class ChatRequest(BaseModel):
    thread_id: str
    message: str


class RenameRequest(BaseModel):
    thread_id: str
    title: str


# -------------------------------------------------------------------- API
@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        runtime = get_runtime()
    except HTTPException as exc:
        return {"ok": False, "detail": exc.detail}
    return {"ok": True, "user_id": runtime.settings.user_id,
            "model": runtime.settings.model_name, "base_url": runtime.settings.base_url}


@app.get("/api/sessions")
def sessions() -> list[dict[str, Any]]:
    runtime = get_runtime()
    return [
        {
            "thread_id": s.thread_id,
            "title": s.title,
            "updated_at": s.updated_at,
            "path": s.path,
        }
        for s in list_sessions(runtime.settings.sessions_dir)
    ]


@app.get("/api/messages/{thread_id}")
def messages(thread_id: str) -> list[dict[str, Any]]:
    runtime = get_runtime()
    return runtime.history(thread_id)


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    runtime = get_runtime()
    with _chat_lock:
        result = runtime.chat_with_trace(request.thread_id, request.message)
    return {"thread_id": request.thread_id, **result}


@app.get("/api/trace/{thread_id}")
def trace(thread_id: str):
    runtime = get_runtime()
    return load_trace(runtime.settings.sessions_dir, thread_id)


@app.post("/api/sessions/rename")
def rename(request: RenameRequest) -> dict[str, Any]:
    runtime = get_runtime()
    rename_session(runtime.settings.sessions_dir, request.thread_id, request.title)
    return {"ok": True}


@app.delete("/api/sessions/{thread_id}")
def delete(thread_id: str) -> dict[str, Any]:
    runtime = get_runtime()
    delete_session(runtime.settings.sessions_dir, thread_id)
    return {"ok": True}


@app.get("/api/memory")
def memory() -> dict[str, Any]:
    """Index + chi tiết memory (đọc trực tiếp từ file Markdown)."""
    runtime = get_runtime()
    entries = runtime.manager.entries()
    return {
        "index": runtime.manager.index_text(),
        "entries": [entry.to_dict() for entry in entries],
    }


@app.get("/api/context")
def context() -> dict[str, Any]:
    """Phần context thực sự được inject vào model (kiểm chứng theo yêu cầu của slide)."""
    runtime = get_runtime()
    return {"context": injected_context(runtime.settings, runtime.manager)}


@app.post("/api/sessions/new")
def new_session() -> dict[str, str]:
    return {"thread_id": f"session-{uuid.uuid4().hex[:8]}"}


# --------------------------------------------------------------------- UI
INDEX_HTML = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)
