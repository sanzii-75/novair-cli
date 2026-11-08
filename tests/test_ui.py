"""Tests for novair.ui — message renderables and export."""
from novair.ui.app import (
    BANNER_ROWS,
    _fmt_tokens,
    gradient_text,
    sys_note,
    tool_call_msg,
    tool_result_msg,
    user_msg,
)


def test_banner_rows_have_six_lines():
    assert len(BANNER_ROWS) == 6
    assert all(len(r) == len(BANNER_ROWS[0]) for r in BANNER_ROWS)


def test_gradient_text_styled():
    t = gradient_text("NOVAIR")
    assert t.plain == "NOVAIR"
    assert any(span.style for span in t.spans)


def test_fmt_tokens():
    assert _fmt_tokens(999) == "999"
    assert _fmt_tokens(12840) == "12.8k"


def test_user_and_tool_renderables():
    assert user_msg("hi").plain.endswith("hi")
    assert "run_shell" in tool_call_msg("run_shell", "{}").plain
    ok = tool_result_msg(True, "line1\nline2")
    assert "line1" in ok.plain
    bad = tool_result_msg(False, "boom")
    assert "boom" in bad.plain
    assert "·" in sys_note("x").plain


def test_export_writes_markdown(tmp_path, monkeypatch):
    from rich.console import Console

    from novair.agent import Agent
    from novair.client import ChatClient
    from novair.config import Provider
    from novair.ui.app import ChatApp

    p = Provider(name="test", base_url="http://mock.test/v1", api_key="k", model="m")
    agent = Agent(ChatClient(p), yolo=True)
    agent.messages = [
        {"role": "user", "content": "pertanyaan"},
        {"role": "assistant", "content": "jawaban **markdown**"},
    ]
    console = Console()
    app = ChatApp(console, ChatClient(p), p, agent, session_id="ses1")
    target = tmp_path / "out.md"
    app._export(str(target))
    text = target.read_text(encoding="utf-8")
    assert "pertanyaan" in text and "jawaban" in text and "ses1" in text
