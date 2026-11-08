# AGENTS.md — Context for AI Coding Agents

You are working on **novair** — a slick terminal AI agent CLI (Python + Rich TUI) that talks to
**any OpenAI-compatible `/chat/completions` endpoint** (OpenRouter, OpenAI, llama.cpp, vLLM, ollama…).
Repo: `github.com/sanzii-75/novair`. Current release: **v0.2.0**. Read this file fully before coding.

## Non-negotiable design decisions

- **Config is env-vars ONLY.** There is intentionally no config file. Do not add one.
- **Only 2 runtime deps**: `rich>=13.4`, `httpx>=0.27`. No new dependencies without strong justification.
- **Python >= 3.9**: keep the `List[...]` / `Optional[...]` typing idiom (no `X | Y`, no builtin generics).
- **Bilingual docs** (English + Bahasa Indonesia) in README.md — keep both halves in sync.
- **Tests must never hit real APIs.** Use the mock server or httpx `MockTransport`.

## Repo map

| Path | Role |
| --- | --- |
| `novair/config.py` | Env-only provider config. Presets: `openrouter`, `openai`; default = `NOVAIR_API_KEY`/`NOVAIR_BASE_URL`/`NOVAIR_MODEL` (falls back to `OPENAI_*`). Custom profiles: `NOVAIR_PROFILE_<NAME>_API_KEY/_BASE_URL/_MODEL`, select via `NOVAIR_PROVIDER`. Auto-detects available profiles, generates export snippets. |
| `novair/client.py` | httpx SSE streaming client for any `/chat/completions` dialect. Non-stream fallback, OpenRouter attribution headers, friendly errors for 401/404/429/5xx. |
| `novair/tools.py` | 5 tools: `run_shell`, `read_file`, `write_file`, `list_dir`, `fetch_url`. Dangerous ops require y/n/a confirmation (bypass with `--yolo`). |
| `novair/agent.py` | The agent loop. Stitches `tool_call` deltas across stream chunks, heals interrupted tool rounds (assistant msg with dangling `tool_calls` gets a synthetic error result), tracks token usage. |
| `novair/session.py` | JSON session persistence in `~/.local/share/novair/sessions`. |
| `novair/ui/app.py` | Rich TUI: gradient "NOVAIR" banner, bordered chat panel (`ChatView`), `StatusBar`, compact mode for narrow terminals, ~12 slash commands (`/help /new /sessions /resume /provider /model /models /system /tools /yolo /clear /export`). A `Bridge` forwards tool confirmations into the TUI. |
| `novair/cli.py` | Entry point. Subcommands: `chat`, `run`, `providers`, `models`, `sessions`. Flags include `--base-url`, `--model`, `--yolo`. |
| `install.sh` | Arch installer: auto-installs python via pacman, isolated venv at `~/.local/share/novair`, launcher `~/.local/bin/novair`, `--uninstall` support. |
| `examples/mock_server.py` | Zero-key OpenAI-compatible mock on **http://localhost:8931/v1**. Use it for ALL end-to-end testing. |
| `tests/` | pytest suite (client, agent, tools, ui, config, session) with mocked HTTP transports. |
| `packaging/PKGBUILD` | AUR package for Arch. |
| `.github/workflows/` | CI: ruff + pytest (3.9–3.12) + mock-server smoke test. Keep it green. |

## Commands

```bash
python -m pytest                 # run tests (configured in pyproject: -q, testpaths=tests)
ruff check novair tests            # lint (line-length 100, target py39)
ruff format novair tests           # format (double quotes)

# End-to-end run without any API key:
python examples/mock_server.py &          # serves http://localhost:8931/v1
NOVAIR_API_KEY=mock NOVAIR_BASE_URL=http://127.0.0.1:8931/v1 NOVAIR_MODEL=mock-small \
  python -m novair chat

./install.sh                     # Arch install; ./install.sh --uninstall to remove
```

## Hard-won gotchas — do NOT re-learn these the hard way

1. **Rich `render_lines()` returns `List[List[Segment]]`.** The correct output path is
   `yield from render_lines(...)` chunks directly. Do **not** wrap in
   `Segments(chunks, new_lines=True)` — it inserts a newline after every segment and mangles lines.
2. **`Bridge.app` must be an instance attribute** set in `__init__` (`self.app = None`). Making it a
   class attribute silently broke the TUI tool-confirmation callback.
3. **Tool-call deltas arrive split across many chunks.** Never dispatch a tool call until
   `name`/`arguments` are fully stitched; then validate JSON before executing.
4. **Interrupted tool rounds need healing**: a streamed assistant message with `tool_calls` but no
   results would make the next request invalid. `agent.py` appends synthetic error tool-results.
5. **`novair run -s` must persist the session** exactly like `chat` does.
6. **`install.sh`**: all `C_*` color variables are defined in one block near the top — reference
   them only after that block (a missing `C_YELLOW` once broke the installer).
7. **pyproject**: use SPDX `license = "MIT"` with `setuptools>=77` (the old license classifiers are
   deprecated). Keep it that way.
8. **Git identity**: NEVER commit as `nexa <nexa@users.noreply.github.com>` — that noreply email is
   bound to a real stranger's GitHub account (username `nexa`), and GitHub attributed every commit
   to them. Commits must use the maintainer's verified identity.
9. **Ruff ignores are intentional** — `B008` (call-default APIs), `RUF001` (❯ › ⚙ are deliberate TUI
   glyphs), `RUF005` (clearer concat). Don't "fix" code to satisfy them. Same for UP-rules: they are
   unselected on purpose for 3.9 typing compatibility.
10. **Test the TUI in a real PTY** (`script -qec "python -m novair chat" /dev/null`) and at **80x20**
    for compact mode before shipping UI changes. Screenshots for the README are rendered from there.

## Conventions

- Conventional Commits: `feat:` `fix:` `test:` `chore:` `ci:` `docs:`.
- Keep PRs/tests aligned with the module table above; when you add a feature, update README (both
  languages) and this file if the architecture shifts.
- UI strings should render well on dark terminals; prefer the existing glyph set (`❯ › ⚙ □ ◨`).

## Where things stand (v0.3.0)

**v0.3.0 rename note:** this project was previously named **nexa**. Everything is now `novair` (command, package, env prefix `NOVAIR_`, data dir `~/.local/share/novair`). Old local data dirs can be migrated with `mv ~/.local/share/nexa ~/.local/share/novair`.

Shipped: streaming chat, tool calling + confirmations, env-only multi-provider config, session
save/resume, full TUI, Arch installer, mock server, pytest suite, CI, AUR PKGBUILD, bilingual docs.
Roadmap ideas: publish to AUR properly, more tools (web search, RAG), model-parameter flags
(temperature/max tokens), shell completion.
