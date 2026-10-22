"""Bằng chứng của từng lượt gọi model, không lưu credential hoặc cấu hình client."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler


class PromptRecorder(BaseCallbackHandler):
    def __init__(self):
        self.prompts = []
        self.usage = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        for batch in messages:
            self.prompts.append([
                {"role": m.type, "content": m.content} for m in batch
            ])

    def on_llm_end(self, response, **kwargs):
        for batch in response.generations:
            for generation in batch:
                usage = getattr(generation.message, "usage_metadata", None)
                if usage:
                    self.usage.append(usage)


def trace_path(sessions_dir, thread_id):
    digest = hashlib.sha256(thread_id.encode()).hexdigest()
    return Path(sessions_dir) / "traces" / f"{digest}.json"


def save_trace(sessions_dir, thread_id, trace):
    path = trace_path(sessions_dir, thread_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


def load_trace(sessions_dir, thread_id):
    path = trace_path(sessions_dir, thread_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
