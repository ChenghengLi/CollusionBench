"""OpenAI-format chat -> Anthropic Messages conversion used by AnthropicMessagesBackend."""

from collusiongen.agents.backends import anthropic_tools, to_anthropic
from collusiongen.agents.llm import native_history
from collusiongen.core.types import function_tool


def test_tool_session_converts_to_alternating_turns():
    history = [
        {"name": "read", "arguments": {"path": "/tmp/a.txt"}, "result": "hello"},
        {"name": None, "arguments": {}, "result": "Please call a tool."},
        {"name": "list", "arguments": {}, "result": ""},
    ]
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "start"}]
    msgs += native_history(history)
    system, out = to_anthropic(msgs)
    assert system == "sys"
    assert [m["role"] for m in out] == ["user", "assistant", "user", "assistant", "user",
                                        "assistant", "user"]
    use = out[1]["content"][0]
    assert use == {"type": "tool_use", "id": "call_0", "name": "read",
                   "input": {"path": "/tmp/a.txt"}}
    assert out[2]["content"][0] == {"type": "tool_result", "tool_use_id": "call_0",
                                    "content": "hello"}
    assert out[3]["content"] == [{"type": "text", "text": "(no tool call)"}]
    assert out[6]["content"][0]["content"] == "(empty)"  # empty results are not allowed


def test_consecutive_tool_results_share_one_user_turn():
    msgs = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "x", "arguments": "{}"}},
            {"id": "b", "type": "function", "function": {"name": "y", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "a", "content": "1"},
        {"role": "tool", "tool_call_id": "b", "content": "2"},
    ]
    _, out = to_anthropic(msgs)
    assert len(out) == 3
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["a", "b"]


def test_tools_convert():
    tool = function_tool("send", "Send a message", {"to": {"type": "integer"}}, ["to"])
    assert anthropic_tools([tool]) == [{
        "name": "send", "description": "Send a message",
        "input_schema": {"type": "object", "properties": {"to": {"type": "integer"}},
                         "required": ["to"]},
    }]
