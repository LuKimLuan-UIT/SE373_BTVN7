"""Challenge B truncation: drop old complete turns, without summarizing or calling a model."""
from .context import context_size


RISK = "Truncation có thể làm mất mục tiêu, ràng buộc và bằng chứng trong các lượt bị bỏ."


def _validate_tools(messages):
    pending = set()
    for message in messages:
        if message.type == "tool":
            call_id = getattr(message, "tool_call_id", None)
            if call_id not in pending:
                raise ValueError("Tool result không có tool call tương ứng; không thay context.")
            pending.remove(call_id)
        else:
            if pending:
                raise ValueError("Còn tool call chưa hoàn tất; không thay context.")
            for call in getattr(message, "tool_calls", []):
                call_id = call.get("id")
                if not call_id or call_id in pending:
                    raise ValueError("Tool call ID không hợp lệ; không thay context.")
                pending.add(call_id)
    if pending:
        raise ValueError("Còn tool call chưa hoàn tất; không thay context.")


def truncate(working, *, keep_turns=2):
    """Keep leading policy messages plus the newest N human-led, complete turns.

    No semantic selection: old user constraints may be lost. Retained messages are
    byte-for-byte unchanged and the full archive remains available for audit only.
    """
    if isinstance(keep_turns, bool) or not isinstance(keep_turns, int) or not 1 <= keep_turns <= 50:
        raise ValueError("Số lượt giữ lại phải là số nguyên từ 1 đến 50.")
    active, archive = working.load()
    _validate_tools(active)
    starts = [i for i, message in enumerate(active) if message.type == "human"]
    if len(starts) <= keep_turns:
        raise ValueError(f"Chỉ có {len(starts)} lượt hội thoại; cần nhiều hơn {keep_turns} lượt để truncation. Context giữ nguyên.")
    prefix = active[:starts[0]]
    if any(message.type not in {"system", "developer"} for message in prefix):
        raise ValueError("History không bắt đầu bằng một lượt user hợp lệ; không thay context.")
    cut = starts[-keep_turns]
    retained = [*prefix, *active[cut:]]
    _validate_tools(retained)
    before, after = context_size(active), context_size(retained)
    if after["serialized_bytes"] >= before["serialized_bytes"]:
        raise ValueError("Truncation không làm context nhỏ hơn; giữ nguyên context.")
    working.save(retained, archive)
    return {
        "technique": "truncation", "keep_turns": keep_turns,
        "before": before, "after": after,
        "dropped_turns": len(starts) - keep_turns,
        "dropped_messages": len(active) - len(retained),
        "active_messages": len(retained), "archive_messages": len(archive),
        "archive_preserved": True, "risk": RISK,
        "compaction_requests": 0, "compaction_usage": [], "compaction_input_estimate": 0,
    }
