"""nexa TUI — btop-style panels: gradient banner header, live chat body, status bar."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .. import __version__
from ..agent import Agent
from ..client import ChatClient, ProviderError
from ..config import Provider, env_hint
from ..session import list_sessions, new_id
from ..session import load as load_session
from ..session import save as save_session

# ── palette ──────────────────────────────────────────────────────────────────
GRADIENT = ["#5EEAD4", "#38BDF8", "#818CF8", "#C084FC", "#F472B6"]
C_ACCENT = "#38BDF8"
C_USER = "#E9E9EF"
C_TOOL = "#FBBF24"
C_DIM = "#6C7280"
C_SYS = "#94A3B8"
BAR_BG = "#11111B"
BAR_FG = "#A6ADC8"

_BANNER_LETTERS = {
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "██║  ╚███║"],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "X": ["██╗  ██╗", "╚██╗██╔╝", " ╚███╔╝ ", " ██╔██╗ ", "██╔╝╚██╗", "╚═╝  ╚═╝"],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
}
BANNER_ROWS = [
    "".join(parts) for parts in zip(_BANNER_LETTERS["N"], _BANNER_LETTERS["E"],
                                    _BANNER_LETTERS["X"], _BANNER_LETTERS["A"])
]


def gradient_text(text: str, palette: Optional[List[str]] = None) -> Text:
    """Per-column gradient across the whole string."""
    palette = palette or GRADIENT
    out = Text()
    span = max(len(text) - 1, 1)
    for x, ch in enumerate(text):
        idx = int((x / span) * (len(palette) - 1) + 0.5)
        out.append(ch, style=palette[idx])
    return out


def _fmt_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


# ── chat view (cropped to panel height) ──────────────────────────────────────
class ChatView:
    """Accumulates rendered messages and shows only the last N lines."""

    def __init__(self) -> None:
        self.items: List[Any] = []
        self._flags: List[bool] = []  # transient → never cached
        self._cache: Dict[int, Any] = {}
        self._width: Optional[int] = None

    def add(self, renderable: Any, transient: bool = False) -> int:
        self.items.append(renderable)
        self._flags.append(transient)
        return len(self.items) - 1

    def replace(self, index: int, renderable: Any, transient: bool = False) -> None:
        self.items[index] = renderable
        self._flags[index] = transient
        self._cache.pop(index, None)

    def clear(self) -> None:
        self.items = []
        self._flags = []
        self._cache = {}

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        height = options.height or 20
        width = options.max_width
        if width != self._width:
            self._cache.clear()
            self._width = width
        opts = options.update(width=width)
        opts.height = None
        all_lines: List[List[Any]] = []
        for i, item in enumerate(self.items):
            if not self._flags[i]:
                cached = self._cache.get(i)
                if cached is None:
                    cached = console.render_lines(item, opts, pad=False, new_lines=True)
                    self._cache[i] = cached
                lines = cached
            else:
                lines = console.render_lines(item, opts, pad=False, new_lines=True)
            all_lines.extend(lines)
        for chunks in all_lines[-height:]:
            yield from chunks  # segments already end with "\n" (new_lines=True)


# ── renderables ──────────────────────────────────────────────────────────────
def user_msg(text: str) -> Text:
    return Text.assemble(("❯ ", f"bold {C_ACCENT}"), (text, f"bold {C_USER}"))


def sys_note(text: str) -> Text:
    return Text(f"  · {text}", style=f"italic {C_SYS}")


def tool_call_msg(name: str, arguments: str) -> Text:
    args_short = " ".join(arguments.split())
    if len(args_short) > 100:
        args_short = args_short[:100] + "…"
    return Text.assemble(
        ("  ⚙ ", C_TOOL),
        (name, f"bold {C_TOOL}"),
        (" ▸ ", C_DIM),
        (args_short, C_SYS),
    )


def tool_result_msg(ok: bool, output: str) -> Text:
    lines = [ln for ln in output.splitlines() if ln.strip()]
    shown = lines[:12]
    more = len(lines) - len(shown)
    style = "dim" if ok else "dim red"
    body = "\n".join("    │ " + ln for ln in shown)
    if more > 0:
        body += f"\n    │ … +{more} more lines"
    t = Text(body, style=style)
    if not ok:
        t = Text.assemble(("    ✖ ", "bold red"), Text(body, style="dim red"))
    return t


def interrupted_msg() -> Text:
    return Text("  ✻ interrupted", style=f"italic {C_DIM}")


def help_table() -> Table:
    rows = [
        ("/help", "show this help"),
        ("/new", "start a fresh session"),
        ("/sessions", "list saved sessions"),
        ("/resume <id|n>", "continue a saved session"),
        ("/provider [name]", "show or switch provider profile"),
        ("/model [id]", "show or switch the model"),
        ("/models", "list models offered by the provider"),
        ("/system [text]", "show or set the system prompt"),
        ("/tools", "list the tools the agent can use"),
        ("/export [file.md]", "save the conversation as markdown"),
        ("/yolo", "toggle tool confirmation prompts"),
        ("/clear", "reset the conversation view"),
        ("/exit", "quit nexa (Ctrl-D works too)"),
    ]
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=f"bold {C_ACCENT}", expand=False)
    t.add_column("command", style="bold", no_wrap=True)
    t.add_column("description", style=C_SYS)
    for cmd, desc in rows:
        t.add_row(cmd, desc)
    return t


def setup_warning(provider: Provider) -> Panel:
    exports = "\n".join(env_hint(provider.name))
    body = Text.assemble(
        (f"No API key detected for provider '{provider.name}'.\n\n", "bold yellow"),
        ("Set one of these (then restart nexa):\n", C_SYS),
        (exports + "\n", f"bold {C_ACCENT}"),
        ("\nOr point nexa at any OpenAI-compatible endpoint:\n", C_SYS),
        ("nexa --base-url http://localhost:11434/v1 --model llama3.1 chat", "bold"),
        ("\nZero-key demo:  python examples/mock_server.py  then use --base-url http://localhost:8931/v1", C_DIM),
    )
    return Panel(body, title="[yellow]⚠ setup", border_style="yellow", box=box.ROUNDED, padding=(0, 1))


# ── header / status bar ──────────────────────────────────────────────────────
def header_panel(provider: Provider, session_id: str, agent: Agent, compact: bool) -> Panel:
    if compact:
        logo = gradient_text("⚡ NEXA")
        info_col = Text.assemble(
            ("provider ", C_DIM), (provider.name, f"bold {C_ACCENT}"),
            ("  model ", C_DIM), (provider.model, "bold"),
        )
        content = Table.grid(padding=(0, 2))
        content.add_row(logo, info_col)
        return Panel(content, border_style=C_ACCENT, box=box.ROUNDED, padding=(0, 1))

    grad_banner = Text()
    width = max(len(r) for r in BANNER_ROWS)
    for r, row in enumerate(BANNER_ROWS):
        for x, ch in enumerate(row):
            idx = int((x / max(width - 1, 1)) * (len(GRADIENT) - 1) + 0.5)
            grad_banner.append(ch, style=GRADIENT[idx])
        if r < len(BANNER_ROWS) - 1:
            grad_banner.append("\n")

    tagline = Text.assemble(
        ("⚡ ", ""), ("terminal AI agent", f"bold {GRADIENT[1]}"),
        ("  ·  any OpenAI-compatible provider", C_DIM),
    )

    key_state = "✓ set" if provider.api_key else "✗ missing"
    info = Text()
    for label, value, vstyle in [
        ("provider", provider.name, f"bold {C_ACCENT}"),
        ("model", provider.model, "bold white"),
        ("api key", f"{key_state}", "green" if provider.api_key else "red"),
        ("session", session_id, C_SYS),
        ("tokens", f"{_fmt_tokens(agent.usage['prompt'])} in · {_fmt_tokens(agent.usage['completion'])} out", C_SYS),
        ("help", "/help · /exit", C_DIM),
    ]:
        info.append(f"{label:<9}", style=C_DIM)
        info.append(f"{value}\n", style=vstyle)

    grid = Table.grid(padding=(0, 3))
    grid.add_row(grad_banner, Group(tagline, Text(""), info))
    return Panel(grid, border_style=GRADIENT[2], box=box.ROUNDED, padding=(0, 1))


class StatusBar:
    def __init__(self) -> None:
        self.provider = ""
        self.model = ""
        self.session = ""
        self.state = "idle"  # idle | streaming | tool
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost = 0.0
        self.yolo = False

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        state_style, state_dot = {
            "idle": ("green", "●"),
            "streaming": (C_ACCENT, "◆"),
            "tool": ("yellow", "⚙"),
        }[self.state]
        bar = Text(style=f"{BAR_FG} on {BAR_BG}")
        bar.append(" ⚡ nexa ", style=f"bold {GRADIENT[0]} on {BAR_BG}")
        bar.append("│ ", style=f"on {BAR_BG}")
        bar.append(f"{self.provider}", style=f"bold {C_ACCENT} on {BAR_BG}")
        bar.append(" · ", style=f"on {BAR_BG}")
        bar.append(self.model, style=f"bold on {BAR_BG}")
        bar.append("  │  session ", style=f"on {BAR_BG}")
        bar.append(self.session, style=f"on {BAR_BG}")
        bar.append(f"  │  tok {(_fmt_tokens(self.tokens_in))} in · {(_fmt_tokens(self.tokens_out))} out", style=f"on {BAR_BG}")
        if self.cost:
            bar.append(f" · ${self.cost:.4f}", style=f"bold green on {BAR_BG}")
        if self.yolo:
            bar.append("  │  YOLO ", style="bold black on yellow")
        right = Text(style=f"{BAR_FG} on {BAR_BG}")
        right.append(f"v{__version__} ", style=f"on {BAR_BG}")
        right.append(state_dot + " " + self.state, style=f"bold {state_style} on {BAR_BG}")
        pad = width - bar.cell_len - right.cell_len - 1
        if pad > 0:
            bar.append(" " * pad, style=f"on {BAR_BG}")
        yield Text.assemble(bar, " ", right)


# ── the app ──────────────────────────────────────────────────────────────────
class ChatApp:
    def __init__(
        self,
        console: Console,
        client: ChatClient,
        provider: Provider,
        agent: Agent,
        session_id: Optional[str] = None,
    ):
        self.console = console
        self.client = client
        self.provider = provider
        self.agent = agent
        self.session_id = session_id or new_id()
        self.view = ChatView()
        self.status = StatusBar()
        self.yolo = agent.toolbox.yolo
        self._quit = False

    # ── confirm callback (used by ToolBox) ───────────────────────────────────
    def _confirm(self, name: str, summary: str) -> bool:
        self.view.add(tool_call_msg(name, summary))
        self.status.state = "tool"
        self._refresh()
        try:
            ans = self.console.input(
                Text("   allow? [y]es · [n]o · [a]lways › ", style="bold yellow")
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.view.add(sys_note("denied"))
            return False
        if ans in ("a", "always"):
            self.yolo = True
            self.agent.toolbox.yolo = True
            self.view.add(sys_note("tool confirmations OFF for this session (/yolo to re-enable)"))
            return True
        ok = ans in ("", "y", "yes")
        if not ok:
            self.view.add(sys_note("denied — told the agent"))
        return ok

    # ── layout plumbing ──────────────────────────────────────────────────────
    def _layout(self) -> Layout:
        size = self.console.size
        compact = size.height < 26
        header_height = 3 if compact else 10
        root = Layout(name="root")
        root.split_column(
            Layout(name="header", size=header_height),
            Layout(name="body"),
            Layout(name="status", size=1),
        )
        root["header"].update(
            header_panel(self.provider, self.session_id, self.agent, compact)
        )
        root["body"].update(self.view)
        root["status"].update(self.status)
        return root

    def _refresh(self) -> None:
        self.status.provider = self.provider.name
        self.status.model = self.provider.model
        self.status.session = self.session_id
        self.status.tokens_in = self.agent.usage["prompt"]
        self.status.tokens_out = self.agent.usage["completion"]
        self.status.cost = self.agent.usage.get("cost", 0.0)
        self.status.yolo = self.yolo

    # ── slash commands ───────────────────────────────────────────────────────
    def _command(self, line: str) -> None:
        parts = line[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else "help"
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("exit", "quit", "q"):
            self._quit = True
        elif cmd == "help":
            self.view.add(help_table())
        elif cmd == "new":
            self.agent.messages.clear()
            self.view.clear()
            self.session_id = new_id()
            self.view.add(sys_note(f"new session {self.session_id}"))
        elif cmd == "sessions":
            sess = list_sessions()
            if not sess:
                self.view.add(sys_note("no saved sessions yet"))
                return
            t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_ACCENT}")
            t.add_column("#", justify="right", style=C_DIM)
            t.add_column("id", style="bold")
            t.add_column("title", overflow="fold")
            t.add_column("turns", justify="right")
            t.add_column("provider", style=C_DIM)
            for i, s in enumerate(sess[:15], 1):
                t.add_row(str(i), s["id"], s["title"], str(s["turns"]), s["provider"])
            self.view.add(t)
            self.view.add(sys_note("resume with /resume <id or #>"))
        elif cmd == "resume":
            self._resume(arg)
        elif cmd == "provider":
            self._switch_provider(arg)
        elif cmd == "model":
            if arg:
                self.provider.model = arg
                self.client.provider = self.provider
                self.agent.model = arg
                self.view.add(sys_note(f"model → {arg}"))
            else:
                self.view.add(sys_note(f"model = {self.provider.model}"))
        elif cmd == "models":
            self._list_models()
        elif cmd == "system":
            if arg:
                self.agent.system_text = arg
                self.view.add(sys_note("system prompt updated"))
            else:
                self.view.add(
                    Panel(
                        Text(self.agent.system_text or "(none)", style=C_SYS),
                        title="[bold]system prompt", border_style=C_DIM, box=box.ROUNDED,
                    )
                )
        elif cmd == "tools":
            from ..tools import TOOL_SCHEMAS
            names = ", ".join(s["function"]["name"] for s in TOOL_SCHEMAS)
            self.view.add(
                sys_note(f"tools: {names}" + ("  · confirmations OFF (/yolo)" if self.yolo else "  · confirmations ON"))
            )
        elif cmd == "yolo":
            self.yolo = not self.yolo
            self.agent.toolbox.yolo = self.yolo
            self.view.add(
                sys_note("YOLO ON — tools run without asking")
                if self.yolo
                else sys_note("YOLO OFF — tools will ask first")
            )
        elif cmd == "clear":
            self.agent.messages.clear()
            self.view.clear()
        elif cmd == "export":
            self._export(arg)
        else:
            self.view.add(sys_note(f"unknown command /{cmd} — try /help"))

    def _export(self, arg: str) -> None:
        path = arg.strip() or f"nexa-{self.session_id}.md"
        lines = [f"# nexa session · {self.session_id}",
                 f"provider: {self.provider.name} · model: {self.provider.model}", ""]
        for m in self.agent.messages:
            role = m.get("role")
            if role == "user":
                lines += ["## ❯ user", "", str(m.get("content") or ""), ""]
            elif role == "assistant":
                content = m.get("content")
                if content:
                    lines += ["## ⚡ nexa", "", str(content), ""]
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    lines.append(f"> ⚙ **{fn.get('name')}** `{fn.get('arguments', '')}`")
            elif role == "tool":
                out = str(m.get("content") or "")
                lines += ["", "```", out[:2000], "```", ""]
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            self.view.add(sys_note(f"exported → {path}"))
        except OSError as e:
            self.view.add(sys_note(f"export failed: {e}"))

    def _resume(self, arg: str) -> None:
        sess = list_sessions()
        target = None
        if not arg:
            self._command("/sessions")
            return
        if arg.isdigit() and 1 <= int(arg) <= len(sess):
            target = sess[int(arg) - 1]["id"]
        else:
            target = arg
        data = load_session(target)
        if not data:
            self.view.add(sys_note(f"session '{target}' not found"))
            return
        self.session_id = data["id"]
        self.agent.messages = data.get("messages") or []
        meta = data.get("meta") or {}
        if meta.get("provider"):
            from ..config import resolve as resolve_provider
            self.provider = resolve_provider(provider=meta["provider"], model=meta.get("model"))
            self.client.provider = self.provider
        self.view.clear()
        self._replay(self.agent.messages)
        self.view.add(sys_note(f"resumed {self.session_id} — continue chatting"))

    def _replay(self, messages: List[Dict[str, Any]]) -> None:
        for m in messages:
            role = m.get("role")
            if role == "user":
                self.view.add(user_msg(str(m.get("content") or "")))
            elif role == "assistant":
                content = m.get("content")
                if content:
                    self.view.add(Markdown(str(content), code_theme="monokai"))
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    self.view.add(tool_call_msg(fn.get("name", "?"), fn.get("arguments", "")))
            elif role == "tool":
                self.view.add(tool_result_msg(True, str(m.get("content") or "")))

    def _switch_provider(self, name: str) -> None:
        from ..config import available_profiles
        from ..config import resolve as resolve_provider
        if not name:
            for p in available_profiles():
                mark = "→" if p["name"] == self.provider.name else " "
                key = "✓" if p["has_key"] else "✗"
                self.view.add(
                    sys_note(f"{mark} {p['name']:<12} {key} key · {p['base_url']} · {p['model']}")
                )
            self.view.add(sys_note("switch with /provider <name>"))
            return
        new_provider = resolve_provider(provider=name, model=self.provider.model)
        self.provider = new_provider
        self.client.provider = new_provider
        self.view.add(sys_note(f"provider → {new_provider.name} ({new_provider.base_url})"))
        if not new_provider.api_key:
            self.view.add(setup_warning(new_provider))

    def _list_models(self) -> None:
        try:
            models = self.client.list_models()
        except ProviderError as e:
            self.view.add(sys_note(f"could not list models: {e}"))
            return
        t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {C_ACCENT}")
        t.add_column("model id", style="bold")
        t.add_column("owned by", style=C_DIM)
        for m in models[:40]:
            t.add_row(str(m.get("id", "?")), str(m.get("owned_by", "")))
        self.view.add(t)

    # ── one turn ─────────────────────────────────────────────────────────────
    def _run_turn(self, text: str) -> None:
        pending: Optional[int] = None
        buf = ""

        def finalize_pending(markdown: bool = True) -> None:
            nonlocal pending, buf
            if pending is None:
                return
            if buf.strip():
                self.view.replace(
                    pending,
                    Markdown(buf, code_theme="monokai") if markdown else Text(buf),
                )
            elif buf:
                self.view.replace(pending, Text(buf, style=C_DIM))
            else:
                self.view.items.pop(pending)
                self.view._flags.pop(pending)
            pending = None
            buf = ""

        try:
            for ev in self.agent.ask(text):
                kind = ev["type"]
                if kind == "round_start":
                    finalize_pending()
                    pending = self.view.add(
                        Spinner("dots", Text(" thinking…", style=f"italic {C_SYS}")),
                        transient=True,
                    )
                elif kind == "assistant_delta":
                    buf += ev["text"]
                    if pending is None:
                        pending = self.view.add(Text("", transient=True))
                    self.view.replace(pending, Text(buf + " ▌", style=C_USER), transient=True)
                    self.status.state = "streaming"
                elif kind == "tool_call":
                    finalize_pending()
                    self.view.add(tool_call_msg(ev["name"], ev["arguments"]), transient=True)
                    self.status.state = "tool"
                elif kind == "tool_result":
                    self.view.add(tool_result_msg(ev["ok"], ev["output"]), transient=True)
                    self.status.state = "streaming"
                elif kind == "assistant_final":
                    finalize_pending()
                self._refresh()
        except KeyboardInterrupt:
            self.agent.heal()
            finalize_pending(markdown=False)
            self.view.add(interrupted_msg())
        self.status.state = "idle"
        self._refresh()

    # ── main loops ───────────────────────────────────────────────────────────
    def run(self) -> None:
        if not self.console.is_terminal:
            self._run_headless()
            return

        if not self.provider.api_key:
            self.view.add(setup_warning(self.provider))
        self.view.add(
            sys_note("type a message · /help for commands · Ctrl-D to quit")
        )
        self._refresh()

        layout = self._layout()
        with Live(
            layout,
            console=self.console,
            screen=False,
            refresh_per_second=12,
            vertical_overflow="crop",
        ) as live:
            ctrl_c = 0
            while not self._quit:
                live.update(self._layout())
                try:
                    line = self.console.input(Text("\n❯ ", style=f"bold {C_ACCENT}"))
                except KeyboardInterrupt:
                    ctrl_c += 1
                    if ctrl_c >= 2:
                        break
                    self.console.print(
                        Text("  (press Ctrl-C again or Ctrl-D to quit, /help for commands)",
                             style=f"italic {C_DIM}")
                    )
                    continue
                except EOFError:
                    break
                ctrl_c = 0
                line = line.strip()
                if not line:
                    continue
                if line.startswith("/"):
                    self._command(line)
                else:
                    self._run_turn(line)
                    save_session(
                        self.session_id,
                        self.agent.messages,
                        {"provider": self.provider.name, "model": self.provider.model,
                         "system": self.agent.system_text},
                    )

    def _run_headless(self) -> None:
        """Plain REPL when stdout is not a terminal (pipes, CI, tests)."""
        self.console.print(
            gradient_text("NEXA"), "· headless mode (no TTY detected)", style=C_DIM
        )
        while not self._quit:
            try:
                line = input("❯ ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            if line.startswith("/"):
                before = len(self.view.items)
                self._command(line)
                for item in self.view.items[before:]:
                    self.console.print(item)
                continue
            self.console.print(user_msg(line))
            buf = ""
            try:
                for ev in self.agent.ask(line):
                    kind = ev["type"]
                    if kind == "assistant_delta":
                        buf += ev["text"]
                        self.console.print(ev["text"], end="")
                    elif kind == "tool_call":
                        self.console.print()
                        self.console.print(tool_call_msg(ev["name"], ev["arguments"]))
                    elif kind == "tool_result":
                        self.console.print(tool_result_msg(ev["ok"], ev["output"]))
                    elif kind == "assistant_final":
                        self.console.print()
            except KeyboardInterrupt:
                self.agent.heal()
                self.console.print(interrupted_msg())
            save_session(
                self.session_id,
                self.agent.messages,
                {"provider": self.provider.name, "model": self.provider.model,
                 "system": self.agent.system_text},
            )


def run_chat(
    console: Console,
    provider: Provider,
    client: ChatClient,
    agent: Agent,
    session_id: Optional[str] = None,
    confirm_hook=None,
) -> None:
    app = ChatApp(console, client, provider, agent, session_id)
    if confirm_hook is not None:
        confirm_hook.app = app
    try:
        app.run()
    except ProviderError as e:
        console.print(Panel(
            Text(str(e), style="bold red"),
            title="provider error", border_style="red", box=box.ROUNDED,
        ))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        pass
