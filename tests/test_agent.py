"""Tests for nexa.agent — loop structure, healing, usage accounting."""
import json

import httpx

from nexa.agent import Agent
from nexa.client import ChatClient
from nexa.config import Provider


def make_agent(responses, yolo=True):
    p = Provider(name="test", base_url="http://mock.test/v1", api_key="k", model="m")
    it = iter(responses)
    transport = httpx.MockTransport(lambda request: next(it))
    return Agent(ChatClient(p, transport=transport), yolo=yolo)


def sse(*chunks):
    out = [f"data: {json.dumps(c)}\n\n".encode() for c in chunks]
    out.append(b"data: [DONE]\n\n")
    return b"".join(out)


def test_plain_answer_roundtrip():
    body = sse(
        {"choices": [{"index": 0, "delta": {"content": "hel"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 7, "completion_tokens": 2}},
    )
    agent = make_agent([httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)])
    events = list(agent.ask("hi"))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "user_message" and kinds[1] == "round_start"
    assert kinds[-1] == "assistant_final"
    deltas = [e["text"] for e in events if e["type"] == "assistant_delta"]
    assert "".join(deltas) == "hello"
    assert agent.messages[-1] == {"role": "assistant", "content": "hello"}
    assert agent.usage["prompt"] == 7 and agent.usage["completion"] == 2


def test_multi_round_tool_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # keep write_file tests out of the repo
    tool_round = sse(
        {"choices": [{"index": 0, "delta": {"tool_calls": [{
            "index": 0, "id": "c9", "type": "function",
            "function": {"name": "write_file",
                         "arguments": "{\"path\": \"out.txt\", \"content\": \"abc\"}"},
        }]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    )
    final_round = sse(
        {"choices": [{"index": 0, "delta": {"content": "wrote it"}, "finish_reason": "stop"}]},
    )
    agent = make_agent([
        httpx.Response(200, headers={"content-type": "text/event-stream"}, content=tool_round),
        httpx.Response(200, headers={"content-type": "text/event-stream"}, content=final_round),
    ])
    events = list(agent.ask("write out.txt"))
    assert sum(1 for e in events if e["type"] == "round_start") == 2
    assert [e["type"] for e in events[-1:]] == ["assistant_final"]
    tool_msgs = [m for m in agent.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1 and "Wrote" in tool_msgs[0]["content"]


def test_heal_fills_missing_tool_results():
    agent = make_agent([])
    agent.messages = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "run_shell", "arguments": "{}"}},
            {"id": "t2", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "t1", "name": "run_shell", "content": "ok"},
    ]
    agent.heal()
    tool_ids = [m.get("tool_call_id") for m in agent.messages if m.get("role") == "tool"]
    assert tool_ids == ["t1", "t2"]
    assert "interrupted" in agent.messages[-1]["content"]


def test_estimate_used_when_usage_missing():
    body = sse({"choices": [{"index": 0, "delta": {"content": "12345678"}, "finish_reason": "stop"}]})
    agent = make_agent([httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)])
    list(agent.ask("hi"))
    assert agent.usage["estimated"] is True
    assert agent.usage["completion"] == 0


def test_system_text_injected():
    seen = {}

    def handler(request: httpx.Request):
        seen["messages"] = json.loads(request.content)["messages"]
        body = sse({"choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": "stop"}]})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    p = Provider(name="test", base_url="http://mock.test/v1", api_key="k", model="m")
    agent = Agent(ChatClient(p, transport=httpx.MockTransport(handler)), system_text="BE NICE")
    list(agent.ask("hi"))
    assert seen["messages"][0] == {"role": "system", "content": "BE NICE"}
    assert seen["messages"][1]["role"] == "user"
