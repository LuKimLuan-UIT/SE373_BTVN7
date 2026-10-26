"""Persistent, isolated B1/B2 experiments for the dedicated web page."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from langchain_core.tools import tool

from .challenge_b_scenarios import FIXTURES, QUESTION, long_history, prepare_logs
from .code_mode import build_code_tools
from .context import CHECKPOINT_PREFIX, Checkpoint, WorkingContext, context_size
from .graph import build_agent, build_model, append_checkpoint_context
from .runtime import injected_context
from .prompts import build_memory_digest
from .memory.history import write_history
from .memory.lifecycle import MemoryManager
from .memory.store import MarkdownMemoryStore
from .memory_tools import build_memory_tools
from .metrics import input_metrics, reduction
from .runtime import Runtime
from .offline import OfflineCompactor
from .code_mode import execute_code
from .challenge_b_scenarios import CODE
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


class ChallengeBLab:
    def __init__(self, settings, root, *, model=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs = prepare_logs(self.root / "logs")
        self.settings = replace(settings, user_id="challenge-b-lab", memory_dir=str(self.root / "memory"),
                                sessions_dir=str(self.root / "sessions"), code_mode_logs_dir=None)
        self.model = model

    def runtime(self, mode="b1"):
        if self.model is None:
            if not self.settings.api_key or not self.settings.model_name:
                raise ValueError("Chưa có cấu hình provider; hãy chọn Offline hoặc điền .env")
            self.model = build_model(self.settings, timeout=90, max_retries=0)
        settings = replace(self.settings, code_mode_logs_dir=str(self.logs) if mode == "code" else None)
        manager = MemoryManager(MarkdownMemoryStore(settings.memory_dir, settings.user_id), settings.user_id)
        extra = ()
        if mode == "native":
            @tool
            def read_all_logs() -> str:
                """Baseline only: read every synthetic log file verbatim and return raw contents."""
                return json.dumps({p.name: p.read_text(encoding="utf-8") for p in sorted(self.logs.glob("*.log"))})
            extra = (read_all_logs,)
        rt = Runtime(settings, manager.store, manager,
                     build_agent(self.model, settings, manager=manager, extra_tools=extra), self.model)
        tools = [*build_memory_tools(manager)] if settings.enable_long_term_memory else []
        tools.extend(build_code_tools(self.logs) if mode == "code" else extra)
        return rt, tools

    def _working(self, thread):
        # Clients cannot use session IDs from A or arbitrary path components.
        if not isinstance(thread, str) or not re.fullmatch(r"(?:b1|bchat)-[0-9a-f]{12}", thread):
            raise ValueError("Mã phiên B1 không hợp lệ")
        working = WorkingContext(self.settings.sessions_dir, thread)
        if not working.path.exists():
            raise ValueError("Phiên B1 chưa tồn tại; hãy tạo phiên mẫu")
        return working

    def seed(self, execution="provider"):
        thread = "b1-" + uuid.uuid4().hex[:12]
        history = long_history()
        working = WorkingContext(self.settings.sessions_dir, thread)
        working.save(history, history)
        write_history(self.settings.sessions_dir, thread, history, title="B1 · refresh-token race")
        result = {"thread_id": thread, "execution": execution, "size": context_size(history), "archive_messages": len(history),
                "scenario": {"goal": "Điều tra lỗi 401 khi refresh đồng thời", "constraints": "Giữ API /refresh; không log token",
                             "failed_attempt": "Tăng timeout 30s không hiệu quả", "evidence": "auth.py:184 · race.log:7",
                             "next_action": "Thêm concurrency test trong tests/test_refresh.py, kiểm tra session lock",
                             "debug_lines": 1600}}
        self.save("b1-seed", result)
        self._write_ui(thread, {"execution": execution, "timeline": [{"kind": "scenario", "content": "Đã nạp phiên dài giả lập: lỗi 401 khi refresh đồng thời. Giữ API /refresh, không log token. Tăng timeout 30s không hiệu quả. Bước kế tiếp: thêm test trong tests/test_refresh.py rồi kiểm tra session lock. Archive chứa 1.600 dòng debug lặp."}], "turns": []})
        return result

    def compact(self, thread):
        working = self._working(thread)
        offline = self._read_ui(thread).get("execution") == "offline"
        try:
            if offline:
                result = working.compact(OfflineCompactor())
            else:
                rt, _ = self.runtime()
                result = rt.compact(thread)
        except Exception as exc:
            self._record_failure(thread, exc, kind="compact")
            raise
        result["reduction_percent_estimated"] = reduction(result["before"]["estimated_tokens"], result["after"]["estimated_tokens"])
        active, archive = working.load()
        result["archive_preserved"] = any("DEBUG duplicate" in str(m.content) for m in archive)
        result["active_preview"] = [{"role": m.type, "content": m.content} for m in active]
        result["thread_id"] = thread
        result["execution"] = "offline" if offline else "provider"
        ui = self._read_ui(thread)
        ui["timeline"].append({"kind": "compact", "content": "Đã compact context và giữ archive.",
                               "before": result["before"], "after": result["after"], "checkpoint": result["checkpoint"]})
        count = len(result["compaction_usage"])
        ui["turns"].append({"requests": result["compaction_requests"], "estimated_input_tokens": result["compaction_input_estimate"],
                            "actual_input_tokens": 0 if offline else sum(u["input_tokens"] for u in result["compaction_usage"]) if count == result["compaction_requests"] and count else None,
                            "actual_output_tokens": 0 if offline else sum(u.get("output_tokens", 0) for u in result["compaction_usage"]) if count else None,
                            "kind": "compact"})
        self._write_ui(thread, ui)
        self.save("b1-compact", result)
        return result

    def continue_task(self, thread):
        active, _ = self._working(thread).load()
        if not any(str(m.content).startswith(CHECKPOINT_PREFIX) for m in active):
            raise ValueError("Cần compact trước khi kiểm tra continuation")
        rt, tools = self.runtime()
        data = rt.chat_with_trace(thread, "Tiếp tục: nêu bước kế tiếp, constraints và cách đã thử không hiệu quả. Chưa cần thực thi.")
        data["thread_id"] = thread
        data["measurement"] = input_metrics(data["trace"]["prompts"], tools, data["trace"]["usage"])
        data["raw_debug_absent"] = "DEBUG duplicate" not in json.dumps(data["trace"]["prompts"])
        self.save("b1-continuation", data)
        return data

    def analyze(self, mode):
        if mode not in {"code", "native"}:
            raise ValueError("Mode phải là code hoặc native")
        rt, tools = self.runtime(mode)
        data = rt.chat_with_trace("b2-" + uuid.uuid4().hex[:12], QUESTION)
        trace = data["trace"]
        prompts_text = "\n".join(str(m["content"]) for p in trace["prompts"] for m in p)
        result = {"mode": mode, "question": QUESTION, "reply": data["reply"],
                  "measurement": input_metrics(trace["prompts"], tools, trace["usage"]),
                  "model": self.settings.model_name, "elapsed_seconds": trace["elapsed_seconds"],
                  "raw_marker_in_requests": "RAW_LOG_ONLY_MARKER" in prompts_text,
                  "events": trace["events"] if mode == "code" else [e for e in trace["events"] if e["kind"] == "call"]}
        if mode == "code":
            result["prompts"] = trace["prompts"]
            summaries = []
            for event in trace["events"]:
                if event["kind"] == "result" and event["name"] == "run_code":
                    try:
                        findings = json.loads(event["content"])
                        if "error_summary" in findings:
                            summaries.append(findings)
                    except (TypeError, ValueError):
                        pass
            result["findings"] = summaries[-1] if summaries else None
            expected = {"refresh_timeout": 400, "db_connection": 240, "invalid_token": 80}
            result["golden_counts_match"] = bool(summaries) and {
                g["type"]: g["count"] for g in summaries[-1]["error_summary"]} == expected
        self.save("b2-" + mode, result)
        return result

    def save(self, name, data):
        directory = self.root / "results"
        directory.mkdir(exist_ok=True)
        result = {**data, "at": datetime.now(timezone.utc).isoformat(),
                  "model": "offline-no-model" if data.get("execution") == "offline" else self.settings.model_name}
        path = directory / f"{name}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def results(self):
        values = {}
        for file in (self.root / "results").glob("*.json"):
            values[file.stem] = json.loads(file.read_text(encoding="utf-8"))
        return values

    def _ui_path(self, thread):
        self._working(thread)
        directory = self.root / "chat-ui"
        directory.mkdir(exist_ok=True)
        return directory / f"{thread}.json"

    def _read_ui(self, thread):
        path = self._ui_path(thread)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"timeline": [], "turns": []}

    def _write_ui(self, thread, ui):
        path = self._ui_path(thread)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(ui, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def new_chat(self, execution="provider"):
        if execution not in {"offline", "provider"}:
            raise ValueError("Chế độ phải là offline hoặc provider")
        thread = "bchat-" + uuid.uuid4().hex[:12]
        WorkingContext(self.settings.sessions_dir, thread).save([], [])
        write_history(self.settings.sessions_dir, thread, [], title="Challenge B · Chat")
        self._write_ui(thread, {"execution": execution, "timeline": [], "turns": []})
        return self.chat_view(thread)

    def clear_memory(self, execution="offline"):
        """Clear only B's long-term memory and open a fresh B context."""
        if execution not in {"offline", "provider"}:
            raise ValueError("Chế độ phải là offline hoặc provider")
        store = MarkdownMemoryStore(self.settings.memory_dir, self.settings.user_id)
        deleted = store.clear()
        return {"ok": True, "deleted": deleted, "chat": self.new_chat(execution)}

    def reset_context(self, thread):
        """Drop active messages/checkpoints, retaining B's archive and actual usage."""
        working = self._working(thread)
        _, archive = working.load()
        ui = self._read_ui(thread)
        working.save([], archive)
        ui["timeline"].append({"kind": "reset", "content":
            "Đã reset context và checkpoint của phiên B. Tin nhắn phía trên chỉ còn là lịch sử, "
            "không gửi lại model. Archive, memory dài hạn và usage đã tiêu thụ được giữ nguyên."})
        self._write_ui(thread, ui)
        return self.chat_view(thread)

    def chat_view(self, thread):
        active, archive = self._working(thread).load()
        ui = self._read_ui(thread)
        offline = ui.get("execution") == "offline"
        setting = replace(self.settings, code_mode_logs_dir=str(self.logs))
        manager = MemoryManager(MarkdownMemoryStore(setting.memory_dir, setting.user_id), setting.user_id)
        tools = [*build_memory_tools(manager), *build_code_tools(self.logs)] if setting.enable_long_term_memory else build_code_tools(self.logs)
        system = injected_context(setting, manager)
        system = append_checkpoint_context(system, active)
        prompt = [{"role": "system", "content": system}]
        for message in active:
            item = {"role": message.type, "content": message.content}
            if getattr(message, "tool_calls", None):
                item["tool_calls"] = message.tool_calls
            if getattr(message, "tool_call_id", None):
                item["tool_call_id"] = message.tool_call_id
            prompt.append(item)
        if setting.memory_placement == "end" and setting.enable_long_term_memory:
            prompt.append({"role": "system", "content": build_memory_digest(manager.index_text())})
        estimate = input_metrics([prompt], tools)["estimated_input_tokens"]
        turns = ui["turns"]
        complete_input = all(t["actual_input_tokens"] is not None for t in turns)
        complete_output = all(t.get("actual_output_tokens") is not None for t in turns)
        return {"thread_id": thread, "timeline": ui["timeline"], "execution": "offline" if offline else "provider",
                "model": "Offline · code thuần · 0 API" if offline else self.settings.model_name,
                "context": {"estimated_input_tokens": estimate,
                            "loaded_estimated_tokens": estimate if active else 0,
                            "state": "ready" if active else "not_loaded",
                            "active_messages": len(active), "active": context_size(active),
                            "archive_messages": len(archive),
                            "method": "JSON UTF-8 bytes/4; estimated_input_tokens forecasts next input including instructions/tools; loaded_estimated_tokens is 0 until active messages exist; excludes next user message",
                            "provider_context_limit": None},
                "usage": {"requests": sum(t["requests"] for t in turns),
                          "actual_input_tokens": sum(t["actual_input_tokens"] for t in turns) if complete_input else None,
                          "actual_output_tokens": sum(t.get("actual_output_tokens", 0) for t in turns) if complete_output else None,
                          "known_actual_input_tokens": sum(t["actual_input_tokens"] or 0 for t in turns),
                          "estimated_input_tokens": sum(t["estimated_input_tokens"] for t in turns),
                          "last": turns[-1] if turns else None}}

    def send(self, thread, message, *, mode="code"):
        self._working(thread)
        if not message.strip() or len(message) > 12000:
            raise ValueError("Tin nhắn phải có nội dung và tối đa 12.000 ký tự")
        if self._read_ui(thread).get("execution") == "offline":
            return self.send_offline(thread, message, mode=mode)
        rt, tools = self.runtime(mode)
        try:
            data = rt.chat_with_trace(thread, message)
        except Exception as exc:
            self._record_failure(thread, exc, tools, kind=mode)
            raise
        trace = data["trace"]
        measurement = input_metrics(trace["prompts"], tools, trace["usage"])
        usage = trace["usage"]
        measurement["actual_output_tokens"] = (sum(u.get("output_tokens", 0) for u in usage)
            if len(usage) == measurement["requests"] and usage else None)
        measurement["kind"] = mode
        ui = self._read_ui(thread)
        ui["turns"].append(measurement)
        # Raw baseline output stays in trace/archive; the chat UI shows the answer and call metadata.
        events = trace["events"] if mode == "code" else [e for e in trace["events"] if e["kind"] == "call"]
        ui["timeline"].extend([{"kind": "user", "content": message},
                               {"kind": "assistant", "content": data["reply"], "measurement": measurement,
                                "events": events, "mode": mode, "prompts": trace["prompts"] if mode == "code" else None}])
        self._write_ui(thread, ui)
        return self.chat_view(thread)

    def send_offline(self, thread, message, *, mode="code"):
        working = self._working(thread)
        active, archive = working.load()
        events = []
        additions = [HumanMessage(content=message)]
        if re.search(r"phân tích.*log|file log|loại lỗi|đếm lỗi|error", message, re.IGNORECASE):
            output = execute_code(self.logs, CODE)
            findings = json.loads(output)
            winner = findings["error_summary"][0] if findings["error_summary"] else None
            answer = (f"{winner['type']}: {winner['count']} lần; file: {', '.join(winner['files'])}.\nBằng chứng: " +
                      "; ".join(f"{e['file']}:{e['line']} — {e['message']}" for e in winner['evidence'])) if winner else "Không có ERROR phù hợp."
            answer = "[Offline · đếm bằng code, không có LLM]\n" + answer
            raw = json.dumps({p.name: p.read_text(encoding="utf-8") for p in sorted(self.logs.glob("*.log"))}) if mode == "native" else output
            name = "read_all_logs" if mode == "native" else "run_code"
            additions += [AIMessage(content="", tool_calls=[{"name": name, "args": {} if mode == "native" else {"code": CODE}, "id": "offline-1"}]),
                          ToolMessage(content=raw, tool_call_id="offline-1", name=name)]
            events = [{"kind": "call", "name": name, "args": {} if mode == "native" else {"code": CODE}},
                      {"kind": "result", "name": name, "content": "Raw output giữ trong archive; offline không gửi model." if mode == "native" else output}]
        elif re.search(r"tiếp tục|bước kế|constraint|ràng buộc|đã thử", message, re.IGNORECASE):
            checkpoints = [str(m.content)[len(CHECKPOINT_PREFIX):] for m in active if str(m.content).startswith(CHECKPOINT_PREFIX)]
            cp = Checkpoint.model_validate_json(checkpoints[-1]) if checkpoints else Checkpoint.model_validate_json(OfflineCompactor().invoke(active).content)
            answer = "[Offline · đọc checkpoint/trích dẫn, không có LLM]\nBước kế tiếp: " + cp.next_action + "\nConstraints: " + "; ".join(cp.constraints) + "\nĐã thử: " + "; ".join(cp.failed_attempts)
        else:
            answer = "[Offline · không gọi model]\nChế độ này hỗ trợ kịch bản có cấu trúc: nạp phiên dài rồi compact; hỏi bước kế tiếp/ràng buộc; hỏi đếm lỗi log. Tôi không suy luận tự do. Chọn Provider nếu muốn chat tổng quát."
        additions.append(AIMessage(content=answer))
        working.save([*active, *additions], [*archive, *additions])
        write_history(self.settings.sessions_dir, thread, [*archive, *additions], title="Challenge B · Offline")
        measurement = {"requests": 0, "actual_input_tokens": 0, "actual_output_tokens": 0,
                       "estimated_input_tokens": 0, "kind": "offline", "source": "No API requests made; not provider usage"}
        ui = self._read_ui(thread)
        ui["turns"].append(measurement)
        ui["timeline"].extend([{"kind": "user", "content": message}, {"kind": "assistant", "content": answer,
                               "measurement": measurement, "mode": "offline", "events": events}])
        self._write_ui(thread, ui)
        return self.chat_view(thread)

    def _record_failure(self, thread, error, tools=(), *, kind):
        prompts, usage = getattr(error, "recorded_prompts", []), getattr(error, "recorded_usage", [])
        if not prompts:
            return
        measurement = input_metrics(prompts, tools, usage)
        measurement["actual_output_tokens"] = sum(u.get("output_tokens", 0) for u in usage) if len(usage) == len(prompts) else None
        measurement["kind"] = kind + "-failed"
        ui = self._read_ui(thread)
        ui["turns"].append(measurement)
        self._write_ui(thread, ui)
