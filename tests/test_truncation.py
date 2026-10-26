"""Deterministic B truncation: complete turns, loss visibility and unchanged archive."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from memory_agent.context import WorkingContext
from memory_agent.truncation import truncate


def test_drops_old_turn_without_semantic_summary_and_keeps_tool_pairs(tmp_path):
    policy = SystemMessage(content="Stable policy")
    call = AIMessage(content="", tool_calls=[{"id":"a","name":"read","args":{}},
                                               {"id":"b","name":"read","args":{}}])
    old = [HumanMessage(content="OLD_CONSTRAINT"), AIMessage(content="OLD_EVIDENCE")]
    recent = [HumanMessage(content="Recent question"), call,
              ToolMessage(content="Result B",tool_call_id="b"),
              ToolMessage(content="Result A",tool_call_id="a"), AIMessage(content="Recent answer")]
    original = [policy, *old, *recent]
    working = WorkingContext(tmp_path,"test")
    working.save(original,original)
    result = truncate(working,keep_turns=1)
    active, archive = WorkingContext(tmp_path,"test").load()
    assert active == [policy, *recent]
    assert archive == original
    assert result["dropped_messages"] == 2 and result["dropped_turns"] == 1
    assert result["compaction_requests"] == 0 and result["compaction_usage"] == []
    assert "checkpoint" not in result
    assert "OLD_CONSTRAINT" not in str(active) and "OLD_CONSTRAINT" in str(archive)
    assert result["after"]["serialized_bytes"] < result["before"]["serialized_bytes"]


@pytest.mark.parametrize("keep", [0, -1, 51, True, 1.5, "2"])
def test_invalid_retention_never_writes_context(tmp_path,keep):
    working=WorkingContext(tmp_path,"test")
    messages=[HumanMessage(content="Hi"),AIMessage(content="Hello")]
    working.save(messages,messages)
    before=working.path.read_bytes()
    with pytest.raises(ValueError): truncate(working,keep_turns=keep)
    assert working.path.read_bytes()==before


def test_too_few_turns_preserves_context_and_archive(tmp_path):
    working=WorkingContext(tmp_path,"test")
    messages=[HumanMessage(content="Important"),AIMessage(content="Response")]
    working.save(messages,messages)
    before=working.path.read_bytes()
    with pytest.raises(ValueError,match="Context giữ nguyên"): truncate(working)
    assert working.path.read_bytes()==before


@pytest.mark.parametrize("bad", [
    [ToolMessage(content="Orphan",tool_call_id="missing")],
    [AIMessage(content="",tool_calls=[{"id":"pending","name":"read","args":{}}])],
    [AIMessage(content="",tool_calls=[{"id":"pending","name":"read","args":{}}]),HumanMessage(content="Interrupted")],
])
def test_incomplete_or_orphan_tools_refuse_without_mutation(tmp_path,bad):
    messages=[HumanMessage(content="Old"),AIMessage(content="Old answer"),HumanMessage(content="New"),*bad]
    working=WorkingContext(tmp_path,"test")
    working.save(messages,messages)
    before=working.path.read_bytes()
    with pytest.raises(ValueError): truncate(working,keep_turns=1)
    assert working.path.read_bytes()==before
