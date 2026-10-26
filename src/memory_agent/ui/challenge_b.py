"""Dedicated Challenge B routes; never use Challenge A's session/memory namespace."""
from pathlib import Path
import json
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import paths
from ..challenge_b_lab import ChallengeBLab
from ..config import load_settings

router = APIRouter()
_lab = None
_lock = threading.RLock()


def get_lab():
    global _lab
    if _lab is None:
        settings, missing = load_settings(offline=True)
        if settings is None:
            raise HTTPException(status_code=503, detail="Thiếu cấu hình: " + ", ".join(missing))
        _lab = ChallengeBLab(settings, paths.DATA_DIR / "challenge-b")
    return _lab


class B1Request(BaseModel):
    thread_id: str


class ModeRequest(BaseModel):
    execution: Literal["offline", "provider"] = "offline"


class ChatRequest(B1Request):
    message: str


class CompactRequest(B1Request):
    keep_turns: int = Field(default=2, ge=1, le=50, strict=True)


@router.post("/api/challenge-b/chat/new")
def new_chat(request: ModeRequest):
    return execute(lambda lab: lab.new_chat(request.execution))


@router.post("/api/challenge-b/reset")
@router.post("/api/challenge-b/memory/clear")
def clear_memory(request: ModeRequest):
    return execute(lambda lab: lab.clear_memory(request.execution))


@router.post("/api/challenge-b/chat/reset-context")
def reset_context(request: B1Request):
    return execute(lambda lab: lab.reset_context(request.thread_id))


@router.get("/api/challenge-b/chat/{thread_id}")
def get_chat(thread_id: str):
    return execute(lambda lab: lab.chat_view(thread_id))


@router.post("/api/challenge-b/chat")
def chat(request: ChatRequest):
    return execute(lambda lab: lab.send(request.thread_id, request.message))


@router.post("/api/challenge-b/chat/compact")
def chat_compact(request: CompactRequest):
    def action(lab):
        result = lab.compact(request.thread_id, keep_turns=request.keep_turns)
        return {"compact": result, "chat": lab.chat_view(request.thread_id)}
    return execute(action)


@router.post("/api/challenge-b/chat/baseline")
def chat_baseline(request: ModeRequest):
    def action(lab):
        from ..challenge_b_scenarios import QUESTION
        created = lab.new_chat(request.execution)
        return lab.send(created["thread_id"], QUESTION, mode="native")
    return execute(action)


def execute(action):
    with _lock:
        try:
            return action(get_lab())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            # Do not expose provider exception text or client configuration.
            raise HTTPException(status_code=502, detail=f"Không hoàn tất yêu cầu ({type(exc).__name__}). Kiểm tra provider và thử lại.") from exc


@router.get("/challenge-b", response_class=HTMLResponse)
def page():
    return (Path(__file__).parent / "challenge_b_chat.html").read_text(encoding="utf-8")


@router.get("/api/challenge-b/status")
def status():
    def view(lab):
        verification_path = paths.PROJECT_ROOT / "reports" / "challenge-b-live" / "results.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8")) if verification_path.exists() else None
        return {"model": lab.settings.model_name, "namespace": "challenge-b-lab", "fixture_files": 4,
                "fixture_scale": 80, "expected_counts": {"refresh_timeout": 400, "db_connection": 240, "invalid_token": 80},
                "results": lab.results(), "verification": verification}
    return execute(view)


@router.post("/api/challenge-b/b1/seed")
def seed(request: ModeRequest):
    return execute(lambda lab: lab.seed(request.execution))


@router.post("/api/challenge-b/b1/compact")
def compact(request: CompactRequest):
    return execute(lambda lab: lab.compact(request.thread_id, keep_turns=request.keep_turns))


@router.post("/api/challenge-b/b1/continue")
def continuation(request: B1Request):
    return execute(lambda lab: lab.continue_task(request.thread_id))


@router.post("/api/challenge-b/b2/{mode}")
def analyze(mode: str):
    return execute(lambda lab: lab.analyze(mode))
