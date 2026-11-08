# Contributing to novair

Thanks for your interest in improving novair! 🎉

## Dev setup

```bash
git clone https://github.com/<YOUR_USERNAME>/novair.git && cd novair
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # novair + pytest + ruff
python examples/mock_server.py &
export NOVAIR_BASE_URL=http://localhost:8931/v1 NOVAIR_API_KEY=mock NOVAIR_MODEL=mock-small
novair chat                       # develop against the zero-key mock
```

## Ground rules

- **Test what you touch** — `pytest` must stay green; add a test for every bugfix/feature.
- **Lint** — `ruff check novair tests` must pass (config lives in `pyproject.toml`).
- **No config files, ever** — novair's identity is *env-only configuration*. New settings belong
  in `novair/config.py` as `NOVAIR_*` env vars (or `NOVAIR_PROFILE_<NAME>_*` per profile).
- **Providers must stay compatible** — anything that speaks the OpenAI `/chat/completions`
  dialect should work. Don't add provider-specific request fields without a fallback.
- **Tools ask first** — new mutating tools must go through `ToolBox._allowed()` confirmation.

## Workflow

1. Fork → branch (`feat/my-thing` or `fix/my-thing`).
2. Commit small, write good messages.
3. `ruff check novair tests && pytest` locally.
4. Open a pull request — CI runs ruff + pytest (3.9–3.12) + a mock-server smoke test.

## Where things live

| path | what |
|---|---|
| `novair/config.py` | env-var → `Provider` resolution, presets |
| `novair/client.py` | OpenAI-compatible SSE client (+ retries) |
| `novair/agent.py` | the tool-calling agent loop |
| `novair/tools.py` | built-in tools & schemas |
| `novair/ui/app.py` | the Rich TUI (header/chat/status bar) |
| `novair/cli.py` | argparse entry point |
| `examples/mock_server.py` | zero-key OpenAI-compatible mock |

---

# Berkontribusi (Bahasa Indonesia)

Terima kasih mau ikut mengembangkan novair! Jalankan `pip install -e ".[dev]"`, uji dengan
mock server (`python examples/mock_server.py`), pastikan `ruff check novair tests` dan
`pytest` hijau sebelum bikin pull request. Prinsip utama: **konfigurasi tetap env-only**,
tool baru yang bersifat mengubah data **wajib lewat konfirmasi**, dan semua provider
OpenAI-compatible harus tetap didukung.
