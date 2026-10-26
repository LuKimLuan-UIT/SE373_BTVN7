"""Deterministic demo compactor. No network, no LLM, no fake provider usage."""
import json
import re

from langchain_core.messages import AIMessage

from .context import CHECKPOINT_PREFIX, Checkpoint


class OfflineCompactor:
    def invoke(self, messages, config=None):
        humans = [str(m.content) for m in messages if m.type == "human"]
        narratives = [str(m.content) for m in messages if m.type == "ai" and str(m.content).strip()
                      and not getattr(m, "tool_calls", None)]
        previous = next((Checkpoint.model_validate_json(str(m.content)[len(CHECKPOINT_PREFIX):])
                         for m in reversed(messages) if str(m.content).startswith(CHECKPOINT_PREFIX)), None)
        recent = narratives[-1] if narratives else (previous.current_state if previous else "Chưa có kết quả xử lý; cần đọc yêu cầu người dùng.")
        action = re.search(r"(?:Tiếp theo|Bước kế tiếp|Next action|Next step)\s*[:：]?\s+(.+)", recent, re.IGNORECASE)
        findings = list(previous.findings) if previous else []
        for m in messages:
            if m.type != "tool":
                continue
            text = str(m.content)
            try:
                result = json.loads(text)
                if isinstance(result, dict) and "error_summary" in result:
                    for group in result["error_summary"][:5]:
                        findings.append(f"{group['type']}: count={group['count']}; evidence=" + json.dumps(group.get("evidence", [])[:2], ensure_ascii=False)[:700])
                    continue
            except (TypeError, ValueError):
                pass
            # Keep source-bearing lines, never try to infer facts from arbitrary prose.
            for line in text.splitlines():
                if re.search(r"[\w./-]+\.(?:py|log|md|json):\d+", line):
                    findings.append("Trích bằng chứng: " + line[:900])
                    if len(findings) >= 30:
                        break
        failed = list(previous.failed_attempts) if previous else []
        failed.extend("Trích hội thoại: " + line[:900] for text in narratives for line in text.splitlines()
                      if re.search(r"không hiệu quả|không giải quyết|ineffective|failed", line, re.IGNORECASE))
        files = sorted({p for text in [recent, *findings] for p in re.findall(r"[\w./-]+\.(?:py|log|md|json)(?::\d+)?", text)})[:30]
        checkpoint = Checkpoint(
            goal=(previous.goal if previous else (humans[0][:1000] if humans else "Tiếp tục công việc trong phiên")),
            current_state=recent[:2000], constraints=[x[:1000] for x in humans[-30:]],
            findings=list(dict.fromkeys(findings))[:30], failed_attempts=list(dict.fromkeys(failed))[:30], files=files,
            next_action=(action[1][:1000] if action else previous.next_action if previous else
                         "Tiếp tục theo yêu cầu gần nhất: " + (humans[-1][:800] if humans else "đọc và kiểm tra trạng thái phiên")),
            open_questions=["Offline chỉ trích xuất theo cấu trúc/mẫu đã công bố; chưa suy luận hoặc kiểm chứng ngữ nghĩa tổng quát."],
        )
        return AIMessage(content=checkpoint.model_dump_json())
