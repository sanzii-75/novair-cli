#!/usr/bin/env python3
"""A tiny OpenAI-compatible mock server so you can try novair with zero API keys.

    python examples/mock_server.py          # listens on http://localhost:8931/v1
    python examples/mock_server.py --port 9000

Then:
    novair --base-url http://localhost:8931/v1 --model mock-small chat

The mock:
  * streams a normal answer for plain messages (true SSE),
  * answers tool calls with run_shell("ls -la") when the prompt mentions
    "list" / "files" / "ls", then summarizes the result,
  * serves GET /models.
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8931

SSE_HEADERS = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}


def sse(obj: dict) -> bytes:
    return f"data: {json.dumps(obj)}\n\n".encode()


def chunk(delta: dict, finish=None, usage=None, model="mock-small") -> bytes:
    body = {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage:
        body["usage"] = usage
    return sse(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter
        print(f"[mock] {self.command} {self.path}")

    def _send_json(self, obj: dict, status: int = 200) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._send_json({
                "object": "list",
                "data": [
                    {"id": "mock-small", "object": "model", "owned_by": "novair-mock"},
                    {"id": "mock-large", "object": "model", "owned_by": "novair-mock"},
                ],
            })
        else:
            self._send_json({"error": {"message": f"unknown path {self.path}"}}, 404)

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json({"error": {"message": f"unknown path {self.path}"}}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length) or b"{}")
        messages = req.get("messages") or []
        wants_stream = bool(req.get("stream"))
        has_tools = bool(req.get("tools"))
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        last_user = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        lowered = str(last_user).lower()

        if wants_stream:
            self.send_response(200)
            for k, v in SSE_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

        usage = {"prompt_tokens": 21, "completion_tokens": 42}

        def stream_chunks(chunks):
            yield chunk({"role": "assistant"})
            for piece in chunks:
                yield chunk({"content": piece})
                time.sleep(0.04)
            yield chunk({}, finish="stop", usage=usage)
            yield b"data: [DONE]\n\n"

        if has_tool_result:
            # Second round: summarize whatever the tool returned.
            tool_msg = next(m for m in messages if m.get("role") == "tool")
            first = str(tool_msg.get("content", "")).splitlines()[:3]
            answer = (
                f"Mock agent here — the tool returned {len(str(tool_msg.get('content','')).splitlines())} lines:\n"
                "```\n" + "\n".join(first) + "\n```\n"
                "That's everything novair needed. ✔"
            )
            pieces = [answer[i:i + 24] for i in range(0, len(answer), 24)]
            if wants_stream:
                for block in stream_chunks(pieces):
                    self.wfile.write(block)
            else:
                self._send_json(self._whole(answer))
            return

        if has_tools and any(k in lowered for k in ("list", "files", "ls", "direktori")):
            # First round: ask for a tool call, name+args split across chunks.
            if wants_stream:
                self.wfile.write(chunk({"role": "assistant", "content": None}))
                self.wfile.write(chunk({"tool_calls": [{
                    "index": 0, "id": "call_mock_1", "type": "function",
                    "function": {"name": "run_shell", "arguments": "{\"command\": \"ls "},
                }]}))
                self.wfile.write(chunk({"tool_calls": [{
                    "index": 0,
                    "function": {"arguments": "-la\"}"},
                }]}))
                self.wfile.write(chunk({}, finish="tool_calls", usage=usage))
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                self._send_json({
                    "id": "chatcmpl-mock", "object": "chat.completion",
                    "created": int(time.time()), "model": "mock-small",
                    "choices": [{
                        "index": 0, "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant", "content": None,
                            "tool_calls": [{
                                "id": "call_mock_1", "type": "function",
                                "function": {"name": "run_shell",
                                             "arguments": "{\"command\": \"ls -la\"}"},
                            }],
                        },
                    }],
                    "usage": usage,
                })
            return

        answer = (
            f"Hello from the novair mock server! 🎈\n"
            f"You said: {last_user!r}\n\n"
            "Try asking me to *list the files* — I'll exercise novair's tool-calling loop.\n"
        )
        pieces = [answer[i:i + 24] for i in range(0, len(answer), 24)]
        if wants_stream:
            for block in stream_chunks(pieces):
                self.wfile.write(block)
        else:
            self._send_json(self._whole(answer))

    @staticmethod
    def _whole(answer: str) -> dict:
        return {
            "id": "chatcmpl-mock", "object": "chat.completion",
            "created": int(time.time()), "model": "mock-small",
            "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": answer},
            }],
            "usage": {"prompt_tokens": 21, "completion_tokens": 42},
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[mock] OpenAI-compatible mock on http://{args.host}:{args.port}/v1  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mock] bye")


if __name__ == "__main__":
    main()
