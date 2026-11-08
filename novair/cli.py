"""novair command-line interface."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .agent import Agent
from .client import ChatClient, ProviderError
from .config import Provider, available_profiles, env_hint, resolve
from .session import delete as delete_session
from .session import list_sessions
from .ui import gradient_text

EXAMPLES = """\
examples:
  export NOVAIR_OPENROUTER_API_KEY=sk-or-v1-...      # one key, hundreds of models
  novair chat                                        # interactive TUI
  novair run "summarize this repo"                   # one-shot prompt
  novair run --yolo "run the test suite"             # tools without confirmation
  novair --provider openrouter --model anthropic/claude-3.5-sonnet chat
  novair --base-url http://localhost:11434/v1 --model llama3.1 chat
  novair providers                                   # profiles detected from env
  novair models                                      # models the provider offers
  novair sessions --rm 20261108-120001               # delete a saved session
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novair",
        description=(
            "⚡ novair — a slick terminal AI agent for any OpenAI-compatible provider "
            "(OpenRouter, OpenAI, Groq, Ollama, vLLM, llama.cpp …). "
            "Configuration lives entirely in environment variables."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"novair {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--provider", metavar="NAME",
                        help="provider profile: openrouter, openai, or a NOVAIR_PROFILE_<NAME>_* name")
    common.add_argument("--model", metavar="ID", help="model id, e.g. openrouter/auto")
    common.add_argument("--base-url", metavar="URL",
                        help="OpenAI-compatible base URL (usually ends in /v1)")
    common.add_argument("--api-key", metavar="KEY", help="API key (env vars are safer)")
    common.add_argument("--system", metavar="TEXT", help="override the system prompt")
    common.add_argument("--temperature", type=float, default=None, metavar="T",
                        help="sampling temperature (0.0-2.0)")
    common.add_argument("--yolo", action="store_true",
                        help="run tools without confirmation prompts")
    common.add_argument("-s", "--session", metavar="ID",
                        help="session id (created/resumed under ~/.local/share/novair/sessions)")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("chat", parents=[common],
                   help="interactive TUI chat (default when no command given)")

    run_p = sub.add_parser("run", parents=[common], help="one-shot prompt → streamed answer")
    run_p.add_argument("prompt", nargs="+", help="the prompt (joined with spaces)")

    sub.add_parser("providers", help="list provider profiles detected in your environment")
    sub.add_parser("models", parents=[common], help="list models offered by the provider")

    sess = sub.add_parser("sessions", help="list or delete saved chat sessions")
    sess.add_argument("--rm", metavar="ID", help="delete a session by id")

    return parser


# ── shared plumbing ──────────────────────────────────────────────────────────
def _client_and_agent(args: argparse.Namespace, console: Console, confirm=None):
    provider = resolve(
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
    )
    client = ChatClient(provider)
    agent = Agent(
        client,
        system_text=args.system,
        confirm=confirm,
        yolo=args.yolo,
        temperature=args.temperature,
    )
    agent.set_cwd(os.getcwd())
    return provider, client, agent


def _print_hint(provider: Provider, console: Console) -> None:
    if provider.api_key:
        return
    msg = (
        f"no API key for '{provider.name}' — local endpoints work without one, "
        "most cloud providers do not\n\n"
    )
    console.print(
        Panel(
            Text.assemble(
                (msg, "yellow"),
                ("\n".join(env_hint(provider.name)) + "\n", "bold"),
                ("\nnovair providers   # see every profile detected in your env", "dim"),
            ),
            title="⚠ setup", border_style="yellow", box=box.ROUNDED,
        )
    )


# ── commands ─────────────────────────────────────────────────────────────────
def cmd_chat(args: argparse.Namespace) -> int:
    from .ui.app import run_chat

    console = Console()

    confirm_hook = None
    if not args.yolo:
        class _Bridge:
            """Wires the agent's ToolBox to the TUI confirmation prompt."""

            def __init__(self) -> None:
                self.app = None

            def __call__(self, name: str, summary: str) -> bool:
                if self.app is not None:
                    return self.app._confirm(name, summary)
                return False

        confirm_hook = _Bridge()

    provider, client, agent = _client_and_agent(args, console, confirm=confirm_hook)
    run_chat(console, provider, client, agent,
             session_id=args.session, confirm_hook=confirm_hook)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    console = Console()
    prompt_text = " ".join(args.prompt)

    def confirm(name: str, summary: str) -> bool:
        console.print(Text(f"  ⚙ {name} ▸ {summary}", style="bold yellow"))
        if not sys.stdin.isatty():
            return False
        try:
            ans = input("   allow? [y/N] › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return ans in ("y", "yes")

    provider, _client, agent = _client_and_agent(args, console, confirm=confirm)
    _print_hint(provider, console)

    status = 0
    buf = ""
    try:
        for ev in agent.ask(prompt_text):
            kind = ev["type"]
            if kind == "assistant_delta":
                buf += ev["text"]
                console.print(ev["text"], end="")
            elif kind == "tool_call":
                if buf:
                    console.print()
                    buf = ""
                console.print(Text(f"  ⚙ {ev['name']} ▸ {' '.join(ev['arguments'].split())[:120]}",
                                   style="bold yellow"))
            elif kind == "tool_result":
                lines = ev["output"].splitlines()
                for ln in lines[:8]:
                    console.print(Text(f"  │ {ln}", style="dim"))
                if len(lines) > 8:
                    console.print(Text(f"  │ … +{len(lines) - 8} more lines", style="dim"))
            elif kind == "assistant_final":
                console.print()
    except ProviderError as e:
        console.print(Panel(Text(str(e), style="bold red"),
                            title="provider error", border_style="red", box=box.ROUNDED))
        status = 1
    except KeyboardInterrupt:
        console.print(Text("\n✻ interrupted", style="dim italic"))
        agent.heal()
        status = 130

    if args.session:
        from .session import save as save_session
        save_session(args.session, agent.messages,
                     {"provider": provider.name, "model": provider.model,
                      "system": agent.system_text})
    return status


def cmd_providers(args: argparse.Namespace) -> int:
    console = Console()
    table = Table(title=gradient_text("novair · provider profiles"),
                  box=box.ROUNDED, header_style="bold", expand=True)
    table.add_column("profile", style="bold cyan", no_wrap=True)
    table.add_column("kind", style="dim")
    table.add_column("base url", overflow="fold")
    table.add_column("model", style="magenta", overflow="fold")
    table.add_column("key env", style="dim")
    table.add_column("key", justify="center")
    for p in available_profiles():
        table.add_row(
            ("→ " if p["selected"] else "") + p["name"],
            p["kind"],
            p["base_url"] or "(unset — defaults to OpenAI)",
            p["model"] or "—",
            p["key_env"],
            "[green]✓ set" if p["has_key"] else "[red]✗ missing",
        )
    console.print(table)
    console.print(Text("select: novair --provider <name> chat · or export NOVAIR_PROVIDER=<name>", style="dim"))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    console = Console()
    provider, client, _ = _client_and_agent(args, console)
    try:
        models = client.list_models()
    except ProviderError as e:
        console.print(Panel(Text(str(e), style="bold red"),
                            title="provider error", border_style="red", box=box.ROUNDED))
        return 1
    table = Table(title=f"models @ {provider.base_url}", box=box.ROUNDED, header_style="bold")
    table.add_column("id", style="bold cyan")
    table.add_column("owned by", style="dim")
    for m in models:
        table.add_row(str(m.get("id", "?")), str(m.get("owned_by", "")))
    console.print(table)
    console.print(Text(f"{len(models)} models · use one: novair --model <id> chat", style="dim"))
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    console = Console()
    if args.rm:
        ok = delete_session(args.rm)
        console.print(f"[green]deleted[/] {args.rm}" if ok else f"[red]not found:[/] {args.rm}")
        return 0 if ok else 1
    sess = list_sessions()
    if not sess:
        console.print(Text("no saved sessions yet — chat with -s <id> or just novair chat", style="dim"))
        return 0
    table = Table(title=gradient_text("novair · sessions"), box=box.ROUNDED, header_style="bold", expand=True)
    table.add_column("id", style="bold cyan")
    table.add_column("updated", style="dim")
    table.add_column("title", overflow="fold")
    table.add_column("turns", justify="right")
    table.add_column("provider", style="dim")
    table.add_column("model", style="magenta", overflow="fold")
    for s in sess[:30]:
        table.add_row(s["id"], s["updated"], s["title"], str(s["turns"]), s["provider"], s["model"])
    console.print(table)
    console.print(Text("resume in TUI: /resume <id> · delete: novair sessions --rm <id>", style="dim"))
    return 0


# ── entry point ──────────────────────────────────────────────────────────────
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        args.command = "chat"

    handlers = {
        "chat": cmd_chat,
        "run": cmd_run,
        "providers": cmd_providers,
        "models": cmd_models,
        "sessions": cmd_sessions,
    }
    try:
        return handlers[args.command](args)
    except ProviderError as e:
        console = Console()
        console.print(Panel(Text(str(e), style="bold red"),
                            title="provider error", border_style="red", box=box.ROUNDED))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
