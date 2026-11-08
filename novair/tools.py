"""Built-in agent tools: run_shell, read_file, write_file, list_dir, fetch_url,
grep, glob, edit_file, web_search, retain, recall.

Every mutating action (run_shell, write_file, edit_file) goes through a
confirmation callback unless --yolo / /yolo is active.
"""
from __future__ import annotations

import glob as globmod
import json
import os
import re
import shutil
import subprocess
from typing import Callable, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import httpx

from . import __version__
from . import memory as memory_mod

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
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "Search file contents with a regex across a directory tree. "
                "Returns path:line:text matches. Faster and safer than run_shell grep."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python regex to search for."},
                    "path": {"type": "string", "description": "Directory to search (default '.')."},
                    "glob": {
                        "type": "string",
                        "description": "Only search filenames matching this fnmatch pattern, e.g. '*.py'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Stop after this many matches (1-200, default 50).",
                    },
                    "ignore_case": {"type": "boolean", "description": "Case-insensitive search (default false)."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files by wildcard pattern (supports **). Sorted newest first with sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern, e.g. 'src/**/*.py' or '*.md'."},
                    "path": {"type": "string", "description": "Directory to search (default '.')."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace an exact string in a text file. The old_string must match "
                "exactly once unless replace_all is set — include surrounding context "
                "to make it unique."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "old_string": {"type": "string", "description": "Exact text to find (must be unique in the file)."},
                    "new_string": {"type": "string", "description": "Replacement text."},
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace every occurrence instead of requiring a unique match (default false).",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web (DuckDuckGo, no API key) and return ranked results "
                "with title, URL and snippet. Follow up with fetch_url to read a page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "max_results": {"type": "integer", "description": "Results to return (1-10, default 5)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retain",
            "description": (
                "Save a durable fact about this project to persistent memory "
                "(build commands, conventions, decisions). Keep facts short and atomic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The fact to remember, one sentence."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Search previously retained project facts by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword(s) to look for."},
                    "limit": {"type": "integer", "description": "Max facts to return (default 10)."},
                },
                "required": ["query"],
            },
        },
    },
]

ConfirmFn = Callable[[str, str], bool]

# directories grep never descends into
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


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
            "grep": self._grep,
            "glob": self._glob,
            "edit_file": self._edit_file,
            "web_search": self._web_search,
            "retain": self._retain,
            "recall": self._recall,
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

    # ── search ───────────────────────────────────────────────────────────────
    def _grep(self, args: Dict) -> Dict:
        pattern = str(args.get("pattern", ""))
        if not pattern:
            return {"ok": False, "output": "grep: 'pattern' is required."}
        try:
            flags = re.I if args.get("ignore_case") else 0
            rx = re.compile(pattern, flags)
        except re.error as e:
            return {"ok": False, "output": f"grep: invalid regex: {e}"}
        path = str(args.get("path") or ".").strip()
        name_filter = str(args.get("glob") or "").strip()
        max_results = max(1, min(int(args.get("max_results") or 50), 200))

        root = os.path.abspath(os.path.join(self.cwd, path))
        if not os.path.isdir(root):
            return {"ok": False, "output": f"No such directory: {path}"}

        hits: List[str] = []
        truncated = False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if name_filter and not globmod.fnmatch.fnmatch(fname, name_filter):
                    continue
                full = os.path.join(dirpath, fname)
                try:
                    with open(full, "rb") as fh:
                        head = fh.read(1024)
                        if b"\0" in head:  # binary — skip
                            continue
                        lines = head + fh.read()
                    text = lines.decode("utf-8", "replace")
                except OSError:
                    continue
                rel = os.path.relpath(full, self.cwd)
                for lineno, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        if len(hits) >= max_results:
                            truncated = True
                            break
                        hits.append(f"{rel}:{lineno}:{line.strip()[:200]}")
                if truncated:
                    break
            if truncated:
                break
        if not hits:
            return {"ok": True, "output": f"No matches for {pattern!r} under {path}"}
        suffix = f"\n… (result cap {max_results} reached)" if truncated else ""
        return {"ok": True, "output": _clip("\n".join(hits), 20000) + suffix}

    def _glob(self, args: Dict) -> Dict:
        pattern = str(args.get("pattern", "")).strip()
        if not pattern:
            return {"ok": False, "output": "glob: 'pattern' is required."}
        path = str(args.get("path") or ".").strip()
        root = os.path.abspath(os.path.join(self.cwd, path))
        if not os.path.isdir(root):
            return {"ok": False, "output": f"No such directory: {path}"}
        matches = globmod.glob(os.path.join(root, pattern), recursive=True)
        files = [m for m in matches if os.path.isfile(m)]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        files = files[:200]
        if not files:
            return {"ok": True, "output": f"No files match {pattern!r} under {path}"}
        rels = [os.path.relpath(f, self.cwd) for f in files]
        sizes = [f"  ({os.path.getsize(f)} B)" for f in files]
        out = "\n".join(f"{r}{s}" for r, s in zip(rels, sizes))
        if len(matches) > 200:
            out += f"\n… (+{len(matches) - 200} more matches)"
        return {"ok": True, "output": _clip(out, 20000)}

    def _edit_file(self, args: Dict) -> Dict:
        path = str(args.get("path", "")).strip()
        old = args.get("old_string")
        new = args.get("new_string")
        if not path or old is None or new is None:
            return {
                "ok": False,
                "output": "edit_file: 'path', 'old_string' and 'new_string' are required.",
            }
        full = os.path.abspath(os.path.join(self.cwd, path))
        try:
            with open(full, "r", encoding="utf-8") as fh:
                content = fh.read()
        except FileNotFoundError:
            return {"ok": False, "output": f"No such file: {path}"}
        except OSError as e:
            return {"ok": False, "output": f"Cannot read {path}: {e}"}

        count = content.count(old)
        if count == 0:
            return {"ok": False, "output": f"edit_file: {old!r} not found in {path}"}
        replace_all = bool(args.get("replace_all"))
        if count > 1 and not replace_all:
            return {
                "ok": False,
                "output": (
                    f"edit_file: {old!r} appears {count} times in {path}. "
                    "Provide more surrounding context or set replace_all=true."
                ),
            }

        summary = f"{path} ({count if replace_all else 1} replacement(s))"
        if not self._allowed("edit_file", summary):
            return {"ok": False, "output": "User declined to edit this file."}
        updated = content.replace(old, new) if replace_all else content.replace(old, new, 1)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(updated)
        return {"ok": True, "output": f"Edited {summary}"}

    # ── web & memory ─────────────────────────────────────────────────────────
    def _web_search(self, args: Dict) -> Dict:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"ok": False, "output": "web_search: 'query' is required."}
        max_results = max(1, min(int(args.get("max_results") or 5), 10))
        url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
        try:
            with httpx.Client(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": f"novair/{__version__} (+terminal-agent)",
                    "Accept": "text/html",
                },
                transport=self.transport,
            ) as client:
                resp = client.get(url)
        except httpx.HTTPError as e:
            return {"ok": False, "output": f"web_search: {type(e).__name__}: {e}"}
        if resp.status_code != 200:
            return {"ok": False, "output": f"web_search: HTTP {resp.status_code} from search backend"}

        html = resp.text
        results = []
        block_re = re.compile(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
        snippet_re = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
        snippets = snippet_re.findall(html)
        for i, (href, title) in enumerate(block_re.findall(html)):
            if len(results) >= max_results:
                break
            link = self._clean_ddg_href(href)
            if not link:
                continue
            title = re.sub(r"(?s)<[^>]+>", "", title).strip()
            snippet = re.sub(r"(?s)<[^>]+>", "", snippets[i] if i < len(snippets) else "").strip()
            results.append(f"{len(results) + 1}. {title}\n   {link}" + (f"\n   {snippet}" if snippet else ""))
        if not results:
            return {"ok": True, "output": f"No results for {query!r}"}
        return {"ok": True, "output": _clip("\n".join(results), 12000)}

    @staticmethod
    def _clean_ddg_href(href: str) -> str:
        """DDG wraps results in /l/?uddg=<encoded>; unwrap to the real URL."""
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            return unquote(target) if target else ""
        return href if href.startswith("http") else ""

    def _retain(self, args: Dict) -> Dict:
        text = str(args.get("text", "")).strip()
        if not text:
            return {"ok": False, "output": "retain: 'text' is required."}
        res = memory_mod.add_fact(self.cwd, text)
        verb = "Saved" if res["added"] else "Already known"
        return {"ok": True, "output": f"{verb}: {text[:120]} (project has {res['total']} facts)"}

    def _recall(self, args: Dict) -> Dict:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"ok": False, "output": "recall: 'query' is required."}
        limit = max(1, min(int(args.get("limit") or 10), 50))
        facts = memory_mod.search_facts(self.cwd, query, limit)
        if not facts:
            return {"ok": True, "output": f"No saved facts match {query!r}."}
        out = "\n".join(f"[{f['id']}] {f['text']}" for f in facts)
        return {"ok": True, "output": _clip(out, 12000)}
