"""Đo tất cả request, ghi nhãn rõ usage thật và heuristic (kể cả tool schemas)."""
import json

from langchain_core.utils.function_calling import convert_to_openai_tool


def input_metrics(prompts, tools=(), usage=()):
    schemas = [convert_to_openai_tool(t) for t in tools]
    estimated = sum((len(json.dumps({"messages": p, "tools": schemas},
                                   ensure_ascii=False).encode("utf-8")) + 3) // 4 for p in prompts)
    # Chỉ dùng actual khi mọi lượt đều có usage, không lấy tổng thiếu lượt.
    actual = (sum(u["input_tokens"] for u in usage)
              if len(usage) == len(prompts) and prompts
              and all(isinstance(u.get("input_tokens"), int) for u in usage) else None)
    return {"requests": len(prompts), "estimated_input_tokens": estimated,
            "actual_input_tokens": actual,
            "method": "ceil(JSON messages incl tool calls + tool schemas UTF-8 bytes / 4), each request",
            "usage_field": "usage_metadata.input_tokens" if actual is not None else None}


def reduction(baseline, optimized):
    if baseline is None or optimized is None or baseline <= 0:
        return None
    return round((baseline - optimized) / baseline * 100, 2)
