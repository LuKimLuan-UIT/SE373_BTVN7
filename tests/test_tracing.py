from memory_agent.tracing import load_trace
from tests.test_agent_memory import FakeToolChatModel, make_runtime, tool_call
from langchain_core.messages import AIMessage


def test_trace_contains_actual_tool_result_and_sent_prompt(tmp_path):
    runtime = make_runtime(tmp_path, FakeToolChatModel(responses=[
        tool_call("remember", {"topic": "auth", "content": "Dùng JWT"}),
        AIMessage(content="Đã ghi."),
    ]))
    data = runtime.chat_with_trace("s1", "Dùng JWT")
    trace = data["trace"]
    assert trace["events"][0]["name"] == "remember"
    assert "Đã ghi memory" in trace["events"][1]["content"]
    assert "Dùng JWT" not in trace["memory_before"]
    assert "Dùng JWT" in trace["memory_after"]
    assert any(m["content"] == "Dùng JWT" for m in trace["prompts"][0])
    assert load_trace(runtime.settings.sessions_dir, "s1") == trace


def test_new_turn_trace_does_not_replay_previous_tools(tmp_path):
    runtime = make_runtime(tmp_path, FakeToolChatModel(responses=[AIMessage(content="Xin chào")]))
    runtime.chat("s1", "Chào")
    result = runtime.chat_with_trace("s1", "Tiếp tục")
    assert result["trace"]["history_messages"] == 2
    assert result["trace"]["events"] == []
