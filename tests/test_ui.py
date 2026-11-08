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


def test_themes_are_wellformed():
    from novair.ui.themes import THEMES

    assert "novair" in THEMES
    for name, theme in THEMES.items():
        assert len(theme.gradient) == 5, name
        for hex_ in theme.gradient + [theme.accent, theme.user, theme.tool,
                                      theme.dim, theme.sys, theme.bar_bg, theme.bar_fg]:
            assert hex_.startswith("#") and len(hex_) == 7, (name, hex_)


def test_resolve_theme_case_insensitive_and_unknown():
    from novair.ui.themes import resolve_theme

    assert resolve_theme("GRUVBOX").name == "gruvbox"
    assert resolve_theme("  dracula ") is not None
    assert resolve_theme("nope") is None
    assert resolve_theme(None) is None


def test_apply_theme_rebinds_palette():
    import novair.ui.app as app
    from novair.ui.themes import THEMES

    original = list(app.GRADIENT)
    original_accent = app.C_ACCENT
    try:
        app.apply_theme(THEMES["gruvbox"])
        assert app.GRADIENT == THEMES["gruvbox"].gradient
        assert app.C_ACCENT == THEMES["gruvbox"].accent
        assert app.BAR_BG == THEMES["gruvbox"].bar_bg
    finally:
        app.apply_theme(type(THEMES["novair"])(  # restore for other tests
            name="novair", gradient=original, accent=original_accent,
            user="#E9E9EF", tool="#FBBF24", dim="#6C7280", sys="#94A3B8",
            bar_bg="#11111B", bar_fg="#A6ADC8",
        ))


def test_switch_theme_command_lists_and_applies(tmp_path):
    from rich.console import Console

    from novair.config import Provider
    from novair.session import new_id
    from novair.ui.app import ChatApp

    class FakeToolbox:
        yolo = False

    class FakeAgent:
        def __init__(self):
            self.toolbox = FakeToolbox()
            self.usage = {"prompt": 0, "completion": 0, "cost": 0.0, "estimated": False}

    p = Provider(name="test", base_url="http://mock.test/v1", api_key="k", model="m")
    console = Console()
    app_obj = ChatApp(console, None, p, FakeAgent(), new_id())
    app_obj._command("/theme")
    app_obj._command("/theme gruvbox")
    assert app_obj.theme_name == "gruvbox"
    app_obj._command("/theme bogus")
    assert app_obj.theme_name == "gruvbox"  # unchanged
