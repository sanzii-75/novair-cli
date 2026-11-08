"""Built-in agent tools: run_shell, read_file, write_file, list_dir.

Every mutating action (run_shell, write_file) goes through a confirmation
callback unless --yolo / /yolo is active.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Callable, Dict, List, Optional

import httpx

from . import __version__

# ── OpenAI function-calling schemas ──────────────────────────────────────────
TOOL_SCHEMAS: List[Dict] = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command in the current working directory and get "
                "stdout/stderr plus the exit code. Use for ls, git, grep, cat, "
                "builds, package queries and anything else best answered by the "
                "system itself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run."},
                    "timeout": {
                        "type": "integer",
                        "description": "Seconds to wait before killing the command (1-120, default 30).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the local filesystem and return its contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (absolute or relative to cwd)."},
                    "max_bytes": {
                        "type": "integer",
                        "description": "Read at most this many bytes (default 20000).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a text file with the given content. Parent directories are created automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write."},
                    "content": {"type": "string", "description": "Full content to write (UTF-8)."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the entries of a directory (name, type, size).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default '.')."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "GET an http(s) URL and return the response text — use it to read "
                "documentation pages, raw files, JSON APIs. Not a search engine: "
                "you need the exact URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute http(s) URL to fetch."},
                    "max_bytes": {
                        "type": "integer",
                        "description": "Return at most this many characters (default 20000).",
                    },
                },
                "required": ["url"],
            },
        },
    },
]

ConfirmFn = Callable[[str, str], bool]


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit // 2] + f"\n… (+{len(text) - limit} chars clipped) …\n" + text[-limit // 2 :]


class ToolBox:
    def __init__(
        self,
        confirm: Optional[ConfirmFn] = None,
        yolo: bool = False,
        cwd: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.confirm = confirm
        self.yolo = yolo
        self.cwd = cwd or os.getcwd()
        self.transport = transport

    # ── dispatch ─────────────────────────────────────────────────────────────
    def execute(self, name: str, arguments_json: str) -> Dict:
        """Run a tool call; returns {"ok": bool, "output": str} for the model."""
        try:
            args = json.loads(arguments_json or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            return {"ok": False, "output": f"Invalid tool arguments: {e}"}

        handler = {
            "run_shell": self._run_shell,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_dir": self._list_dir,
            "fetch_url": self._fetch_url,
        }.get(name)

        if handler is None:
            return {"ok": False, "output": f"Unknown tool: {name}"}
        try:
            return handler(args)
        except KeyboardInterrupt:
            return {"ok": False, "output": "Interrupted by user before completion."}
        except Exception as e:  # never crash the loop on tool errors
            return {"ok": False, "output": f"{type(e).__name__}: {e}"}

    # ── confirmation ─────────────────────────────────────────────────────────
    def _allowed(self, name: str, summary: str) -> bool:
        if self.yolo:
            return True
        if self.confirm is None:
            return True
        return bool(self.confirm(name, summary))

    # ── implementations ──────────────────────────────────────────────────────
    def _run_shell(self, args: Dict) -> Dict:
        command = str(args.get("command", "")).strip()
        if not command:
            return {"ok": False, "output": "run_shell: 'command' is required."}
        timeout = max(1, min(int(args.get("timeout") or 30), 120))

        if not self._allowed("run_shell", command):
            return {"ok": False, "output": "User declined to run this command."}

        bash = shutil.which("bash")
        proc = subprocess.run(
            command,
            shell=True,
            executable=bash,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = proc.stdout or ""
        err = proc.stderr or ""
        body = (
            f"exit_code={proc.returncode}\n"
            f"--- stdout ---\n{out.strip() or '(empty)'}\n"
            f"--- stderr ---\n{err.strip() or '(empty)'}"
        )
        return {"ok": proc.returncode == 0, "output": _clip(body, 8000)}

    def _read_file(self, args: Dict) -> Dict:
        path = str(args.get("path", "")).strip()
        if not path:
            return {"ok": False, "output": "read_file: 'path' is required."}
        max_bytes = max(1, min(int(args.get("max_bytes") or 20000), 200_000))
        full = os.path.abspath(os.path.join(self.cwd, path))
        with open(full, "rb") as fh:
            data = fh.read(max_bytes + 1)
        if len(data) > max_bytes:
            return {
                "ok": True,
                "output": _clip(data[:max_bytes].decode("utf-8", "replace"), max_bytes)
                + f"\n(file is larger than {max_bytes} bytes — truncated)",
            }
        return {"ok": True, "output": _clip(data.decode("utf-8", "replace"), 24000)}

    def _write_file(self, args: Dict) -> Dict:
        path = str(args.get("path", "")).strip()
        content = args.get("content")
        if not path or content is None:
            return {"ok": False, "output": "write_file: 'path' and 'content' are required."}
        full = os.path.abspath(os.path.join(self.cwd, path))
        size = len(content.encode("utf-8"))
        if not self._allowed("write_file", f"{path} ({size} bytes)"):
            return {"ok": False, "output": "User declined to write this file."}
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
        return {"ok": True, "output": f"Wrote {size} bytes to {path}"}

    def _list_dir(self, args: Dict) -> Dict:
        path = str(args.get("path") or ".").strip()
        full = os.path.abspath(os.path.join(self.cwd, path))
        entries = []
        try:
            scandir = list(os.scandir(full))
        except FileNotFoundError:
            return {"ok": False, "output": f"No such directory: {path}"}
        scandir.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in scandir[:300]:
            try:
                if entry.is_dir(follow_symlinks=False):
                    entries.append(f"{entry.name}/")
                else:
                    entries.append(f"{entry.name}  ({entry.stat().st_size} B)")
            except OSError:
                entries.append(f"{entry.name}  (unreadable)")
        if len(scandir) > 300:
            entries.append(f"… (+{len(scandir) - 300} more entries)")
        return {"ok": True, "output": "\n".join(entries) or "(empty directory)"}

    def _fetch_url(self, args: Dict) -> Dict:
        url = str(args.get("url", "")).strip()
        if not re.match(r"^https?://", url, re.I):
            return {"ok": False, "output": "fetch_url: 'url' must start with http:// or https://"}
        max_bytes = max(1, min(int(args.get("max_bytes") or 20000), 200_000))
        try:
            with httpx.Client(
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": f"novair/{__version__} (+terminal-agent)"},
                transport=self.transport,
            ) as client:
                with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        return {"ok": False, "output": f"fetch_url: HTTP {resp.status_code} for {url}"}
                    ctype = resp.headers.get("content-type", "")
                    buf = b""
                    for chunk in resp.iter_bytes():
                        buf += chunk
                        if len(buf) >= max_bytes * 4:  # decode headroom
                            break
        except httpx.HTTPError as e:
            return {"ok": False, "output": f"fetch_url: {type(e).__name__}: {e}"}

        text = buf.decode(resp.charset_encoding or "utf-8", "replace")
        if "html" in ctype or text.lstrip()[:15].lower().startswith(("<!doctype html", "<html")):
            text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = re.sub(r"[ \t\r\f\v]+", " ", text)
            text = re.sub(r"\n\s*\n+", "\n", text)
        header = f"HTTP {resp.status_code} · {ctype or 'unknown type'} · {url}\n\n"
        return {"ok": True, "output": _clip(header + text.strip(), max_bytes)}
