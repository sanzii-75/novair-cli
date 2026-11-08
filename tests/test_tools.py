"""Tests for novair.tools — shell, files, dirs, fetch_url, confirmation gating."""
import json

import httpx

from novair.tools import ToolBox


def test_run_shell_echo(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("run_shell", json.dumps({"command": "echo hello"}))
    assert res["ok"] and "hello" in res["output"] and "exit_code=0" in res["output"]


def test_run_shell_nonzero_exit(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("run_shell", json.dumps({"command": "exit 3"}))
    assert not res["ok"] and "exit_code=3" in res["output"]


def test_run_shell_declined(tmp_path):
    box = ToolBox(cwd=str(tmp_path), confirm=lambda name, summary: False)
    res = box.execute("run_shell", json.dumps({"command": "echo x"}))
    assert not res["ok"] and "declined" in res["output"]


def test_run_shell_yolo_mid_session(tmp_path):
    box = ToolBox(cwd=str(tmp_path))
    box.yolo = True  # /yolo toggled mid-session
    res = box.execute("run_shell", json.dumps({"command": "echo x"}))
    assert res["ok"]


def test_write_then_read_file(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("write_file", json.dumps({"path": "sub/a.txt", "content": "data"}))
    assert res["ok"]
    res = box.execute("read_file", json.dumps({"path": "sub/a.txt"}))
    assert res["ok"] and "data" in res["output"]


def test_write_file_declined(tmp_path):
    box = ToolBox(cwd=str(tmp_path), confirm=lambda name, summary: False)
    res = box.execute("write_file", json.dumps({"path": "a.txt", "content": "x"}))
    assert not res["ok"] and "declined" in res["output"]


def test_list_dir(tmp_path):
    (tmp_path / "b.txt").write_text("xx")
    (tmp_path / "subdir").mkdir()
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("list_dir", json.dumps({"path": "."}))
    assert res["ok"] and "subdir/" in res["output"] and "b.txt" in res["output"]


def test_invalid_json_args(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("run_shell", "{not json")
    assert not res["ok"] and "Invalid tool arguments" in res["output"]


def test_unknown_tool(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("nope", "{}")
    assert not res["ok"] and "Unknown tool" in res["output"]


def test_read_file_missing(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("read_file", json.dumps({"path": "ghost.txt"}))
    assert not res["ok"]


def test_fetch_url_requires_http(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("fetch_url", json.dumps({"url": "ftp://x"}))
    assert not res["ok"] and "http" in res["output"]


def test_fetch_url_html_stripped():
    html = b"<html><head><style>x{}</style></head><body><h1>Hi</h1><p>there</p></body></html>"

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=html)

    box = ToolBox(yolo=True, transport=httpx.MockTransport(handler))
    res = box.execute("fetch_url", json.dumps({"url": "http://x.test/a"}))
    assert res["ok"]
    assert "Hi" in res["output"] and "there" in res["output"]
    assert "<h1>" not in res["output"] and "<style>" not in res["output"]


def test_fetch_url_error_status():
    def handler(request):
        return httpx.Response(404, content=b"nope")

    box = ToolBox(yolo=True, transport=httpx.MockTransport(handler))
    res = box.execute("fetch_url", json.dumps({"url": "http://x.test/missing"}))
    assert not res["ok"] and "404" in res["output"]


def test_schemas_are_wellformed():
    from novair.tools import TOOL_SCHEMAS
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert names == {
        "run_shell", "read_file", "write_file", "list_dir", "fetch_url",
        "grep", "glob", "edit_file", "web_search", "retain", "recall",
    }
    for s in TOOL_SCHEMAS:
        assert s["type"] == "function"
        assert "parameters" in s["function"]


# ── grep ─────────────────────────────────────────────────────────────────────
def test_grep_finds_pattern(tmp_path):
    (tmp_path / "a.py").write_text("def main():\n    return 42\n")
    (tmp_path / "b.py").write_text("value = 42\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("grep", json.dumps({"pattern": "42", "path": "."}))
    assert res["ok"]
    assert "a.py:2" in res["output"] and "b.py:1" in res["output"]


def test_grep_glob_filter_and_cap(tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text("needle here\n")
    (tmp_path / "skip.md").write_text("needle here\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("grep", json.dumps({"pattern": "needle", "glob": "*.py", "max_results": 3}))
    assert res["ok"]
    assert "skip.md" not in res["output"]
    assert "result cap 3" in res["output"]


def test_grep_invalid_regex(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("grep", json.dumps({"pattern": "[unclosed"}))
    assert not res["ok"] and "invalid regex" in res["output"]


def test_grep_skips_git_dir(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "x.txt").write_text("secretneedle\n")
    (tmp_path / "ok.txt").write_text("secretneedle\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("grep", json.dumps({"pattern": "secretneedle"}))
    assert res["ok"] and ".git" not in res["output"] and "ok.txt" in res["output"]


# ── glob ─────────────────────────────────────────────────────────────────────
def test_glob_matches_with_recursion(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "deep.py").write_text("x = 1\n")
    (tmp_path / "top.py").write_text("x = 2\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("glob", json.dumps({"pattern": "**/*.py"}))
    assert res["ok"] and "src/deep.py" in res["output"] and "top.py" in res["output"]


def test_glob_no_match(tmp_path):
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("glob", json.dumps({"pattern": "*.ghost"}))
    assert res["ok"] and "No files match" in res["output"]


# ── edit_file ────────────────────────────────────────────────────────────────
def test_edit_file_unique_replacement(tmp_path):
    (tmp_path / "a.txt").write_text("hello world\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("edit_file", json.dumps({"path": "a.txt", "old_string": "world", "new_string": "there"}))
    assert res["ok"]
    assert (tmp_path / "a.txt").read_text() == "hello there\n"


def test_edit_file_missing_string(tmp_path):
    (tmp_path / "a.txt").write_text("hello\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("edit_file", json.dumps({"path": "a.txt", "old_string": "zzz", "new_string": "y"}))
    assert not res["ok"] and "not found" in res["output"]


def test_edit_file_ambiguous(tmp_path):
    (tmp_path / "a.txt").write_text("x x x\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("edit_file", json.dumps({"path": "a.txt", "old_string": "x", "new_string": "y"}))
    assert not res["ok"] and "appears 3 times" in res["output"]


def test_edit_file_replace_all(tmp_path):
    (tmp_path / "a.txt").write_text("x x x\n")
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("edit_file",
                      json.dumps({"path": "a.txt", "old_string": "x", "new_string": "y", "replace_all": True}))
    assert res["ok"]
    assert (tmp_path / "a.txt").read_text() == "y y y\n"


def test_edit_file_declined(tmp_path):
    (tmp_path / "a.txt").write_text("data\n")
    box = ToolBox(cwd=str(tmp_path), confirm=lambda name, summary: False)
    res = box.execute("edit_file", json.dumps({"path": "a.txt", "old_string": "data", "new_string": "x"}))
    assert not res["ok"] and "declined" in res["output"]


# ── web_search ───────────────────────────────────────────────────────────────
DDG_HTML = b"""<html><body>
<div class="result">
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.test%2F1&amp;rut=abc">First <b>Result</b></a>
<a class="result__snippet" href="#">Snippet <em>one</em> text</a>
</div>
<div class="result">
<a rel="nofollow" class="result__a" href="https://direct.test/page">Second Result</a>
<a class="result__snippet" href="#">Snippet two</a>
</div>
</body></html>"""


def test_web_search_parses_results():
    def handler(request):
        assert "html.duckduckgo.com" in str(request.url)
        return httpx.Response(200, content=DDG_HTML)

    box = ToolBox(yolo=True, transport=httpx.MockTransport(handler))
    res = box.execute("web_search", json.dumps({"query": "test query", "max_results": 2}))
    assert res["ok"]
    assert "First Result" in res["output"] and "https://example.test/1" in res["output"]
    assert "Second Result" in res["output"] and "https://direct.test/page" in res["output"]
    assert "Snippet one text" in res["output"]


def test_web_search_error_status():
    def handler(request):
        return httpx.Response(503, content=b"busy")

    box = ToolBox(yolo=True, transport=httpx.MockTransport(handler))
    res = box.execute("web_search", json.dumps({"query": "q"}))
    assert not res["ok"] and "503" in res["output"]


# ── retain / recall ──────────────────────────────────────────────────────────
def test_retain_recall_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    box = ToolBox(yolo=True, cwd=str(tmp_path))
    res = box.execute("retain", json.dumps({"text": "tests run with pytest -q"}))
    assert res["ok"] and "Saved" in res["output"]
    res = box.execute("retain", json.dumps({"text": "tests run with pytest -q"}))
    assert res["ok"] and "Already known" in res["output"]
    res = box.execute("recall", json.dumps({"query": "pytest"}))
    assert res["ok"] and "tests run with pytest -q" in res["output"]
    res = box.execute("recall", json.dumps({"query": "missingkeyword"}))
    assert res["ok"] and "No saved facts" in res["output"]
