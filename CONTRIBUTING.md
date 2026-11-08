# Contributing to nexa

Thanks for your interest in improving nexa! 🎉

## Dev setup

```bash
git clone https://github.com/<YOUR_USERNAME>/nexa.git && cd nexa
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # nexa + pytest + ruff
python examples/mock_server.py &
export NEXA_BASE_URL=http://localhost:8931/v1 NEXA_API_KEY=mock NEXA_MODEL=mock-small
nexa chat                       # develop against the zero-key mock
```

## Ground rules

- **Test what you touch** — `pytest` must stay green; add a test for every bugfix/feature.
- **Lint** — `ruff check nexa tests` must pass (config lives in `pyproject.toml`).
- **No config files, ever** — nexa's identity is *env-only configuration*. New settings belong
  in `nexa/config.py` as `NEXA_*` env vars (or `NEXA_PROFILE_<NAME>_*` per profile).
- **Providers must stay compatible** — anything that speaks the OpenAI `/chat/completions`
  dialect should work. Don't add provider-specific request fields without a fallback.
- **Tools ask first** — new mutating tools must go through `ToolBox._allowed()` confirmation.

## Workflow

1. Fork → branch (`feat/my-thing` or `fix/my-thing`).
2. Commit small, write good messages.
3. `ruff check nexa tests && pytest` locally.
4. Open a pull request — CI runs ruff + pytest (3.9–3.12) + a mock-server smoke test.

## Where things live

| path | what |
|---|---|
| `nexa/config.py` | env-var → `Provider` resolution, presets |
| `nexa/client.py` | OpenAI-compatible SSE client (+ retries) |
| `nexa/agent.py` | the tool-calling agent loop |
| `nexa/tools.py` | built-in tools & schemas |
| `nexa/ui/app.py` | the Rich TUI (header/chat/status bar) |
| `nexa/cli.py` | argparse entry point |
| `examples/mock_server.py` | zero-key OpenAI-compatible mock |

---

# Berkontribusi (Bahasa Indonesia)

Terima kasih mau ikut mengembangkan nexa! Jalankan `pip install -e ".[dev]"`, uji dengan
mock server (`python examples/mock_server.py`), pastikan `ruff check nexa tests` dan
`pytest` hijau sebelum bikin pull request. Prinsip utama: **konfigurasi tetap env-only**,
tool baru yang bersifat mengubah data **wajib lewat konfirmasi**, dan semua provider
OpenAI-compatible harus tetap didukung.
