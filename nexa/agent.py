"""The agent loop: user text -> (streamed answer | tool calls -> results -> ...)"""
from __future__ import annotations

import datetime
import platform
from typing import Any, Dict, Iterator, List, Optional

from .client import ChatClient
from .tools import TOOL_SCHEMAS, ToolBox

SYSTEM_TEMPLATE = """You are nexa, a sharp, pragmatic AI agent living in the user's terminal.
Environment: {os_name} {arch} · shell {shell} · cwd {cwd} · {date}

You can call tools: run_shell, read_file, write_file, list_dir.
Style: concise, direct, code-first. Prefer concrete commands and real file
contents over speculation — when a task needs information from the machine,
use tools instead of guessing. Keep final answers short unless depth is asked
for. Use markdown for structure and fenced code blocks with language tags."""


class Agent:
    def __init__(
        self,
        client: ChatClient,
        system_text: Optional[str] = None,
        confirm=None,
        yolo: bool = False,
        max_tool_rounds: int = 8,
        temperature: Optional[float] = None,
    ):
        self.client = client
        self.model = client.provider.model
        self.system_text = system_text or self.default_system_text()
        self.toolbox = ToolBox(confirm=confirm, yolo=yolo)
        self.max_tool_rounds = max_tool_rounds
        self.temperature = temperature
        self.messages: List[Dict[str, Any]] = []
        self.usage = {"prompt": 0, "completion": 0, "cost": 0.0, "estimated": False}

    # ── system prompt ────────────────────────────────────────────────────────
    @staticmethod
    def default_system_text() -> str:
        return SYSTEM_TEMPLATE.format(
            os_name=platform.system() or "?",
            arch=platform.machine() or "?",
            shell="bash" if platform.system() != "Windows" else "cmd",
            cwd="?",
            date=datetime.date.today().isoformat(),
        )

    def set_cwd(self, cwd: str) -> None:
        self.system_text = (self.system_text or "").replace("cwd ?", f"cwd {cwd}", 1)

    # ── usage tracking ───────────────────────────────────────────────────────
    def _bump_usage(self, usage: Optional[Dict]) -> None:
        if usage and usage.get("prompt_tokens") is not None:
            self.usage["prompt"] += int(usage.get("prompt_tokens") or 0)
            self.usage["completion"] += int(usage.get("completion_tokens") or 0)
            cost = usage.get("cost")
            if cost is not None:  # OpenRouter reports cost per request
                self.usage["cost"] = round(self.usage.get("cost", 0.0) + float(cost), 6)
        else:
            self.usage["estimated"] = True
            self.usage["prompt"] += self._estimate(self.messages) // 4

    @staticmethod
    def _estimate(messages: List[Dict]) -> int:
        total = 0
        for m in messages:
            total += len(str(m.get("content") or ""))
            for tc in m.get("tool_calls") or []:
                total += len(str(tc.get("function", {}).get("arguments") or ""))
        return total

    # ── healing interrupted tool rounds ─────────────────────────────────────
    def heal(self) -> None:
        """Ensure every assistant tool_call has a matching tool result."""
        result_ids = {
            m.get("tool_call_id")
            for m in self.messages
            if m.get("role") == "tool"
        }
        missing = []
        for m in self.messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    if tc.get("id") and tc["id"] not in result_ids:
                        missing.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": tc.get("function", {}).get("name", "tool"),
                                "content": "(interrupted by user before the tool finished)",
                            }
                        )
                        result_ids.add(tc["id"])
        if missing:
            self.messages = self.messages + missing

    # ── the main entry ───────────────────────────────────────────────────────
    def ask(self, user_text: str) -> Iterator[Dict[str, Any]]:
        """Send a user message; yield events until the final answer is done."""
        self.heal()
        self.messages.append({"role": "user", "content": user_text})
        yield {"type": "user_message"}

        for _round in range(self.max_tool_rounds):
            yield {"type": "round_start"}
            final = yield from self._stream_complete()

            if final["tool_calls"]:
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": final["content"] or None,
                        "tool_calls": [
                            {
                                "id": c["id"] or f"call_{i}",
                                "type": "function",
                                "function": {"name": c["name"], "arguments": c["args"]},
                            }
                            for i, c in enumerate(final["tool_calls"])
                        ],
                    }
                )
                for i, call in enumerate(final["tool_calls"]):
                    yield {
                        "type": "tool_call",
                        "name": call["name"],
                        "arguments": call["args"],
                    }
                    result = self.toolbox.execute(call["name"], call["args"])
                    yield {
                        "type": "tool_result",
                        "name": call["name"],
                        "ok": result["ok"],
                        "output": result["output"],
                    }
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"] or f"call_{i}",
                            "name": call["name"],
                            "content": result["output"],
                        }
                    )
                continue  # feed results back for the next round

            self.messages.append({"role": "assistant", "content": final["content"] or ""})
            yield {"type": "assistant_final", "text": final["content"] or ""}
            return

        self.messages.append(
            {
                "role": "assistant",
                "content": "(stopped: reached the tool-round limit — ask me to continue)",
            }
        )
        yield {
            "type": "assistant_final",
            "text": "⚠ reached the tool-round limit without a final answer.",
        }

    # ── one streaming completion ─────────────────────────────────────────────
    def _stream_complete(self) -> Iterator[Dict[str, Any]]:
        messages = (
            [{"role": "system", "content": self.system_text}] + self.messages
            if self.system_text
            else list(self.messages)
        )
        content = ""
        calls: Dict[int, Dict[str, str]] = {}
        usage = None
        finish = None

        for ev in self.client.chat_stream(
            messages, tools=TOOL_SCHEMAS, temperature=self.temperature
        ):
            if ev["type"] == "message":
                msg = ev["message"]
                content += msg.get("content") or ""
                if msg.get("content"):
                    yield {"type": "assistant_delta", "text": msg["content"]}
                for i, tc in enumerate(msg.get("tool_calls") or []):
                    fn = tc.get("function", {})
                    calls[i] = {
                        "id": tc.get("id") or f"call_{i}",
                        "name": fn.get("name", ""),
                        "args": fn.get("arguments") or "{}",
                    }
                usage = usage or ev.get("usage")
                finish = ev.get("finish_reason") or finish
                continue

            delta = ev.get("delta") or {}
            piece = delta.get("content")
            if piece:
                content += piece
                yield {"type": "assistant_delta", "text": piece}
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index") or 0
                slot = calls.setdefault(idx, {"id": "", "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                name = fn.get("name")
                if name:
                    cur = slot["name"]
                    if not cur:
                        slot["name"] = name
                    elif cur == name:
                        pass
                    elif name.startswith(cur):
                        slot["name"] = name  # provider resent the growing name
                    elif cur.startswith(name):
                        pass
                    else:
                        slot["name"] += name  # provider chunks the name
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]
            if ev.get("usage"):
                usage = ev["usage"]
            if ev.get("finish_reason"):
                finish = ev["finish_reason"]

        self._bump_usage(usage)
        return {
            "content": content,
            "tool_calls": [calls[i] for i in sorted(calls)],
            "usage": usage,
            "finish": finish,
        }
