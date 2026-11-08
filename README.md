#  Novair: Ai Agent 

**A terminal AI agent for any OpenAI-compatible provider.** Full TUI panels, streaming answers with markdown, real tool calling (shell / files / web), saved sessions — configured entirely with environment variables.

<p align="center"><img src="docs/preview.svg" alt="novair TUI preview" width="100%"></p>

<p align="center">
  <a href="#-dokumentasi-bahasa-indonesia">🇮🇩 Dokumentasi Bahasa Indonesia</a>
</p>

<p align="center">
  <a href="https://github.com/YOUR_USERNAME/novair/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/YOUR_USERNAME/novair/ci.yml?branch=main&label=CI" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
  <img src="https://img.shields.io/badge/deps-2%20only%20(rich%2C%20httpx)-orange" alt="deps">
</p>

---

## Features

| | |
|---|---|
| 🖥 **Full TUI** | btop-style layout: gradient ASCII banner, bordered chat panel, live status bar (provider · model · session · tokens · cost · state) |
| 🌊 **Streaming** | answers appear token-by-token, then re-render as markdown with syntax-highlighted code |
| 🔧 **11 built-in tools** | `run_shell`, `read_file`, `write_file`, `edit_file`, `list_dir`, `grep`, `glob`, `fetch_url`, `web_search`, `retain`, `recall` — mutating actions ask first (`--yolo` to skip) |
| 🌐 **Web-aware agent** | `web_search` (DuckDuckGo, no key) + `fetch_url` let the agent search and read docs pages, raw files and JSON APIs |
| 🧠 **Project memory** | the agent saves durable facts per-project (`retain`) and looks them up in later sessions (`recall`) — stored under `~/.local/share/novair/memory` |
| 🎨 **Themes** | `NOVAIR_THEME` or `/theme`: novair, catppuccin, tokyonight, gruvbox, dracula, matrix — repaints banner, panels and status bar |
| 🗿 **Multi-provider profiles** | preset **OpenRouter**, plus any OpenAI-compatible endpoint (OpenAI, Groq, Ollama, vLLM, llama.cpp, LM Studio…) via env vars — no config files |
| 💾 **Sessions** | every chat auto-saves to `~/.local/share/novair/sessions`; resume with `novair chat -s <id>` or `/resume`, export with `/export` |
| ⌨ **Shell completion** | `novair completions bash|zsh|fish` — generated from live profile metadata, never drifts |
| 🛡 **Resilient** | auto-retry on 429/5xx/connection errors, healed tool rounds after Ctrl-C, clear error messages with the env var to fix |
| 🧪 **Zero-key demo** | ships an OpenAI-compatible mock server to try everything without an API key |

## Install (Arch Linux — and friends)

```bash
git clone https://github.com/YOUR_USERNAME/novair.git && cd novair
./install.sh                  # → venv at ~/.local/share/novair, launcher at ~/.local/bin/novair
```

The installer:

1. detects `pacman` and installs `python` if missing (needs no AUR helper),
2. creates an isolated venv in `~/.local/share/novair/venv`,
3. pip-installs novair (only `rich` + `httpx`), symlinks `~/.local/bin/novair`,
4. warns if `~/.local/bin` is not on your `PATH`.

Other methods:

```bash
pipx install .                # if you prefer pipx
pipx install git+https://github.com/YOUR_USERNAME/novair.git
```

**AUR**: a ready `PKGBUILD` lives in [`packaging/`](packaging/) — fill in the checksum and
submit it to AUR, then `yay -S novair-cli` works.

Uninstall: `./install.sh --uninstall` (leaves session data in place).

## Configuration — env vars only

```bash
# featured preset — one key, hundreds of models
export NOVAIR_OPENROUTER_API_KEY="sk-or-v1-…"     # or OPENROUTER_API_KEY
export NOVAIR_OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"   # optional

# generic OpenAI-compatible default
export NOVAIR_API_KEY="sk-…"
export NOVAIR_BASE_URL="https://api.openai.com/v1"
export NOVAIR_MODEL="gpt-4o-mini"

# custom named profiles (multi-provider, still no config files)
export NOVAIR_PROFILE_GROQ_API_KEY="gsk_…"
export NOVAIR_PROFILE_GROQ_BASE_URL="https://api.groq.com/openai/v1"
export NOVAIR_PROFILE_GROQ_MODEL="llama-3.3-70b-versatile"
export NOVAIR_PROVIDER="openrouter"               # optional default profile
```

See [`novair-env.example.sh`](novair-env.example.sh) for a copy-paste template.

| Variable | Meaning |
|---|---|
| `NOVAIR_PROVIDER` | profile used when `--provider` is not given |
| `NOVAIR_API_KEY` / `NOVAIR_BASE_URL` / `NOVAIR_MODEL` | the default profile |
| `NOVAIR_OPENROUTER_API_KEY` (or `OPENROUTER_API_KEY`) | OpenRouter preset |
| `NOVAIR_PROFILE_<NAME>_API_KEY` / `_BASE_URL` / `_MODEL` | any custom profile |
| `NOVAIR_TEMPERATURE` / `NOVAIR_MAX_TOKENS` / `NOVAIR_TOP_P` | default sampling params (CLI flags override) |
| `NOVAIR_THEME` | TUI theme: novair, catppuccin, tokyonight, gruvbox, dracula, matrix |
| `XDG_DATA_HOME` | where sessions & memory live (default `~/.local/share/novair`) |

## Usage

```bash
novair chat                        # interactive TUI (default command)
novair run "summarize this repo"   # one-shot prompt, streamed
novair run --yolo "run the tests"  # tools without confirmation
novair chat --temperature 0.2 --max-tokens 2048 --top-p 0.9   # sampling knobs
novair chat --theme gruvbox        # repaint the TUI (or export NOVAIR_THEME)
novair --provider openrouter --model anthropic/claude-3.5-sonnet chat
novair --base-url http://localhost:11434/v1 --model llama3.1 chat   # Ollama
novair providers                   # profiles detected from your env
novair models                      # models the provider offers
novair sessions [--rm ID]          # list / delete saved sessions
novair completions zsh             # shell completion script (bash/zsh/fish)
```

### Shell completion

```bash
eval "$(novair completions zsh)"          # add to ~/.zshrc
eval "$(novair completions bash)"         # add to ~/.bashrc
novair completions fish > ~/.config/fish/completions/novair.fish
```

Scripts are generated live from your detected provider profiles, so
`--provider <TAB>` always matches what novair can actually use.

### Inside the TUI

| command | effect |
|---|---|
| `/help` | all commands |
| `/new` | fresh session |
| `/sessions` + `/resume <id|#>` | revisit saved chats |
| `/provider [name]` | switch profile mid-chat |
| `/model [id]` · `/models` | inspect/switch model |
| `/system [text]` | show/override the system prompt |
| `/theme [name]` | list or switch the color theme |
| `/memory [clear]` | list or wipe saved project facts |
| `/tools` · `/yolo` | tool list · toggle confirmations |
| `/export [file.md]` | save the conversation as markdown |
| `/clear` · `/exit` | reset view · quit |

`Ctrl-C` interrupts a running answer (twice at the prompt quits); `Ctrl-D` quits.

### Tool calling & safety

The agent can run shell commands, read/write/edit files, search code (`grep`/`glob`),
fetch URLs and search the web. **Mutating tools (`run_shell`, `write_file`, `edit_file`)
ask before acting** (`y / n / a-always`); read-only tools (`read_file`, `list_dir`,
`grep`, `glob`, `fetch_url`, `web_search`, `retain`, `recall`) don't. `--yolo` or
`/yolo` disables prompts — use it inside trusted containers/VMs only. Tool output is
truncated before it re-enters the model context.

### Try it with zero keys

```bash
python examples/mock_server.py & \
  novair --base-url http://localhost:8931/v1 --model mock-small chat
```

## Troubleshooting

| symptom | fix |
|---|---|
| `401 authentication failed` | wrong/expired key — check the env var printed in the error |
| `404 endpoint not found` | base URL must end in `/v1` (e.g. `…/api/v1`) |
| `Could not connect` | server down / typo in `--base-url`; for Ollama: `ollama serve` first |
| TUI looks garbled | use a 256-color/truecolor terminal (kitty, alacritty, foot…) |
| `novair: command not found` | add `~/.local/bin` to `PATH` (the installer prints the line) |

## Design notes

- **stdlib + 2 deps**: `rich` (TUI) and `httpx` (SSE streaming) — nothing else.
- **Any dialect**: tolerates non-streaming providers, resends full names, missing usage, weird SSE framing.
- **Healed loops**: an interrupted tool round is patched with synthetic results so the conversation stays API-valid.
- **Tested**: pytest suite with mocked HTTP transports + GitHub Actions CI (Python 3.9 → 3.12, incl. a live mock-server smoke test).

## Roadmap

- [x] ~~`web_search` tool~~ — shipped in v0.4.0 (DuckDuckGo, no key)
- [ ] token-cost estimate table (`/cost`) with per-model pricing
- [ ] AUR package accepted (`yay -S novair-cli`)
- [ ] memory upgrades: reflect/forget + cross-project recall (v0.5)
- [ ] subagent fan-out (`task` tool) with isolated worktrees (v0.5)
- [ ] streaming tool-args preview in the TUI
- [ ] multi-turn one-shot mode for scripting (`novair run --continue`)

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Contributing

```bash
pip install -e ".[dev]"       # pytest + ruff
ruff check novair tests && pytest
```

CI must stay green; new settings = env vars; new mutating tools must ask first.

## License

MIT — see [LICENSE](LICENSE).

---

# 🇮🇩 Dokumentasi Bahasa Indonesia

## ⚡ Novair — AI agent terminal, siap untuk Arch Linux

**Tampilan penuh panel ala btop, jawaban streaming ber-markdown, tool calling sungguhan (shell & file & web), riwayat sesi tersimpan — semuanya dikonfigurasi lewat environment variable, tanpa file config.**

### Fitur

- 🖥 **Full TUI panel** — banner ASCII gradasi, panel chat ber-border, status bar hidup (provider · model · sesi · token · biaya · status)
- 🌊 **Chat streaming** — respons mengalir realtime lalu di-render ulang sebagai markdown + syntax highlighting
- 🔧 **11 tool bawaan** — `run_shell`, `read_file`, `write_file`, `edit_file`, `list_dir`, `grep`, `glob`, `fetch_url`, `web_search`, `retain`, `recall`, dengan **konfirmasi tiap aksi mutasi** (`--yolo` untuk lewati)
- 🌐 **Paham web** — `web_search` (DuckDuckGo, tanpa key) + `fetch_url` bikin agent bisa mencari & membaca halaman dokumentasi, file mentah, dan API JSON
- 🧠 **Memori proyek** — agent menyimpan fakta penting per-proyek (`retain`) dan mengingatnya lagi di sesi berikutnya (`recall`) — tersimpan di `~/.local/share/novair/memory`
- 🎨 **Tema warna** — `NOVAIR_THEME` atau `/theme`: novair, catppuccin, tokyonight, gruvbox, dracula, matrix — banner, panel, dan status bar ikut berubah
- 🗿 **Multi-profil provider** — preset **OpenRouter** + endpoint OpenAI-compatible apa pun (OpenAI, Groq, Ollama, vLLM, llama.cpp, LM Studio…)
- 💾 **Riwayat sesi** — otomatis tersimpan di `~/.local/share/novair/sessions`, lanjutkan dengan `novair chat -s <id>` atau `/resume`, ekspor ke markdown via `/export`
- ⌨ **Shell completion** — `novair completions bash|zsh|fish`, di-generate dari metadata profil yang terdeteksi
- 🛡 **Tahan banting** — auto-retry untuk 429/5xx/koneksi, putaran tool yang terputus otomatis "diobati", pesan error jelas
- 🧪 **Demo tanpa API key** — ada mock server OpenAI-compatible bawaan

### Instalasi di Arch Linux

```bash
git clone https://github.com/YOUR_USERNAME/novair.git && cd novair
./install.sh
```

Script installer akan:

1. mendeteksi `pacman` dan memasang `python` bila belum ada (tanpa perlu helper AUR),
2. membuat venv terisolasi di `~/.local/share/novair/venv`,
3. memasang novair via pip (hanya butuh `rich` + `httpx`) dan membuat launcher `~/.local/bin/novair`,
4. mengingatkan bila `~/.local/bin` belum ada di `PATH`.

Alternatif: `pipx install .` · **AUR**: `PKGBUILD` siap pakai ada di [`packaging/`](packaging/). Uninstall: `./install.sh --uninstall`.

### Konfigurasi (env var saja)

```bash
# Preset utama — OpenRouter (satu key, ratusan model)
export NOVAIR_OPENROUTER_API_KEY="sk-or-v1-…"        # atau OPENROUTER_API_KEY
export NOVAIR_OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"   # opsional

# Default generik OpenAI-compatible
export NOVAIR_API_KEY="sk-…"
export NOVAIR_BASE_URL="https://api.openai.com/v1"
export NOVAIR_MODEL="gpt-4o-mini"

# Profil kustom — pola: NOVAIR_PROFILE_<NAMA>_*
export NOVAIR_PROFILE_GROQ_API_KEY="gsk_…"
export NOVAIR_PROFILE_GROQ_BASE_URL="https://api.groq.com/openai/v1"
export NOVAIR_PROFILE_GROQ_MODEL="llama-3.3-70b-versatile"
export NOVAIR_PROVIDER="openrouter"                  # profil default (opsional)
```

Template siap salin: [`novair-env.example.sh`](novair-env.example.sh).

### Cara pakai

```bash
novair chat                        # TUI interaktif (perintah default)
novair run "ringkas repo ini"      # sekali jalan, hasil streaming
novair run --yolo "jalankan test"  # tool tanpa konfirmasi
novair chat --temperature 0.2 --max-tokens 2048 --top-p 0.9   # parameter sampling
novair chat --theme gruvbox        # ganti tema TUI (atau export NOVAIR_THEME)
novair --base-url http://localhost:11434/v1 --model llama3.1 chat   # Ollama lokal
novair providers                   # daftar profil yang terdeteksi
novair models                      # daftar model dari provider
novair sessions [--rm ID]          # kelola sesi tersimpan
novair completions zsh             # script completion shell (bash/zsh/fish)
```

Shell completion — tambahkan ke rc file shell-mu:

```bash
eval "$(novair completions zsh)"          # ~/.zshrc
eval "$(novair completions bash)"         # ~/.bashrc
novair completions fish > ~/.config/fish/completions/novair.fish
```

Perintah di dalam TUI: `/help` `/new` `/sessions` `/resume` `/provider` `/model` `/models` `/system` `/theme` `/memory` `/tools` `/export` `/yolo` `/clear` `/exit`. `Ctrl-C` memotong jawaban yang sedang berjalan; `Ctrl-D` keluar.

### Keamanan tool

Tool yang **memutasi** (`run_shell`, `write_file`, `edit_file`) **selalu minta konfirmasi** (`y / n / a`), kecuali `--yolo` atau `/yolo` aktif — gunakan hanya di container/VM terpercaya. Tool read-only (`read_file`, `list_dir`, `grep`, `glob`, `fetch_url`, `web_search`, `retain`, `recall`) tidak perlu konfirmasi. Output tool dipangkas sebelum masuk konteks model.

### Coba tanpa API key

```bash
python examples/mock_server.py & \
  novair --base-url http://localhost:8931/v1 --model mock-small chat
```

### Berkontribusi & roadmap

Roadmap: tabel estimasi biaya `/cost`, upgrade memori (reflect/forget), subagent fan-out (`task`), paket AUR resmi, preview tool-args saat streaming. Gas ke [CONTRIBUTING.md](CONTRIBUTING.md) — ada versi Indonesia-nya juga. CI harus tetap hijau (`ruff check novair tests && pytest`).

### Lisensi

MIT — lihat [LICENSE](LICENSE).
