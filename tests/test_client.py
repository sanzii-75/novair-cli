"""Tests for nexa.client — SSE parsing, non-stream fallback, error mapping, retries."""
import json

import httpx
import pytest

from nexa.agent import Agent
from nexa.client import ChatClient, ProviderError
from nexa.config import Provider


def make_provider(base="http://mock.test/v1"):
    return Provider(name="test", base_url=base, api_key="k", model="m",
                    key_env_hint="NEXA_TEST_API_KEY")


def sse_body(*chunks):
    out = []
    for c in chunks:
        out.append(f"data: {json.dumps(c)}\n\n".encode())
    out.append(b"data: [DONE]\n\n")
    return b"".join(out)


def sse_response(body):
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


def test_stream_parses_content_deltas():
    body = sse_body(
        {"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": "He"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": "llo"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
    )
    client = ChatClient(make_provider(), transport=httpx.MockTransport(lambda r: sse_response(body)))
    events = list(client.chat_stream([{"role": "user", "content": "hi"}]))
    text = "".join(e["delta"].get("content") or "" for e in events if e["type"] == "chunk")
    assert text == "Hello"
    assert events[-1]["usage"]["prompt_tokens"] == 3


def test_tool_call_deltas_accumulate_in_agent():
    body1 = sse_body(
        {"choices": [{"index": 0, "delta": {"tool_calls": [{
            "index": 0, "id": "c1", "type": "function",
            "function": {"name": "run_shell", "arguments": "{\"command\": \"echo "},
        }]}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": "hi\"}"},
        }]}, "finish_reason": "tool_calls"}]},
    )
    body2 = sse_body(
        {"choices": [{"index": 0, "delta": {"content": "done"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    )
    responses = iter([sse_response(body1), sse_response(body2)])
    transport = httpx.MockTransport(lambda request: next(responses))
    client = ChatClient(make_provider(), transport=transport)
    agent = Agent(client, yolo=True)
    events = list(agent.ask("run something"))
    finals = [e for e in events if e["type"] == "assistant_final"]
    tools = [e for e in events if e["type"] == "tool_call"]
    assert len(tools) == 1 and tools[0]["name"] == "run_shell"
    assert json.loads(tools[0]["arguments"]) == {"command": "echo hi"}
    assert finals and finals[0]["text"] == "done"
    assert any(m.get("role") == "tool" and "exit_code=0" in m["content"] for m in agent.messages)


def test_non_stream_fallback():
    body = json.dumps({
        "choices": [{"message": {"role": "assistant", "content": "whole"}, "finish_reason": "stop"}],
    }).encode()

    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    client = ChatClient(make_provider(), transport=httpx.MockTransport(handler))
    events = list(client.chat_stream([{"role": "user", "content": "hi"}]))
    assert events[0]["type"] == "message"
    assert events[0]["message"]["content"] == "whole"


def test_401_error_is_actionable():
    body = json.dumps({"error": {"message": "bad key"}}).encode()

    def handler(request):
        return httpx.Response(401, headers={"content-type": "application/json"}, content=body)

    client = ChatClient(make_provider(), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc:
        list(client.chat_stream([{"role": "user", "content": "hi"}]))
    assert "authentication failed" in str(exc.value)
    assert "NEXA_TEST_API_KEY" in str(exc.value)  # mentions the env var hint


def test_retries_on_503_then_succeeds(monkeypatch):
    monkeypatch.setattr("nexa.client.time.sleep", lambda s: None)
    ok = sse_body({"choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": "stop"}]})
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"content-type": "text/plain"}, content=b"down")
        return sse_response(ok)

    client = ChatClient(make_provider(), transport=httpx.MockTransport(handler))
    events = list(client.chat_stream([{"role": "user", "content": "hi"}]))
    assert calls["n"] == 2
    text = "".join(e["delta"].get("content") or "" for e in events if e["type"] == "chunk")
    assert text == "ok"


def test_no_retry_on_401():
    body = json.dumps({"error": {"message": "nope"}}).encode()
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, headers={"content-type": "application/json"}, content=body)

    client = ChatClient(make_provider(), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError):
        list(client.chat_stream([{"role": "user", "content": "hi"}]))
    assert calls["n"] == 1


def test_openrouter_attribution_headers():
    p = Provider(name="openrouter", base_url="https://openrouter.ai/api/v1", api_key="k", model="m")
    client = ChatClient(p)
    h = client._headers()
    assert h["HTTP-Referer"].startswith("https://")
    assert h["X-Title"] == "nexa-cli"
    assert h["Authorization"] == "Bearer k"


def test_list_models():
    body = json.dumps({"data": [{"id": "a"}, {"id": "b"}]}).encode()

    def handler(request):
        assert request.url.path.endswith("/models")
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    client = ChatClient(make_provider(), transport=httpx.MockTransport(handler))
    assert [m["id"] for m in client.list_models()] == ["a", "b"]


def test_cost_accumulates():
    body = sse_body(
        {"choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.01}},
    )
    client = ChatClient(make_provider(), transport=httpx.MockTransport(lambda r: sse_response(body)))
    agent = Agent(client, yolo=True)
    list(agent.ask("hi"))
    assert agent.usage["cost"] == pytest.approx(0.01)
    assert agent.usage["prompt"] == 10
