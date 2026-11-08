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
    assert names == {"run_shell", "read_file", "write_file", "list_dir", "fetch_url"}
    for s in TOOL_SCHEMAS:
        assert s["type"] == "function"
        assert "parameters" in s["function"]
