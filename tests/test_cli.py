"""Tests for novair.cli — argparse wiring and completion scripts."""
from novair.cli import _env_opt, build_parser


def test_new_model_flags_parse():
    args = build_parser().parse_args(
        ["chat", "--max-tokens", "512", "--top-p", "0.9", "--temperature", "0.2"]
    )
    assert args.max_tokens == 512
    assert args.top_p == 0.9
    assert args.temperature == 0.2


def test_theme_flag_only_on_chat():
    args = build_parser().parse_args(["chat", "--theme", "gruvbox"])
    assert args.theme == "gruvbox"
    args = build_parser().parse_args(["chat"])
    assert args.theme is None
    args = build_parser().parse_args(["run", "hello"])
    assert not hasattr(args, "theme")


def test_completions_subcommand():
    for shell in ("bash", "zsh", "fish"):
        args = build_parser().parse_args(["completions", shell])
        assert args.shell == shell


def test_env_opt_casts_and_tolerates_garbage(monkeypatch):
    monkeypatch.setenv("NOVAIR_MAX_TOKENS", "256")
    assert _env_opt("NOVAIR_MAX_TOKENS", int) == 256
    monkeypatch.setenv("NOVAIR_TOP_P", "0.7")
    assert _env_opt("NOVAIR_TOP_P") == 0.7
    monkeypatch.setenv("NOVAIR_TEMPERATURE", "not-a-float")
    assert _env_opt("NOVAIR_TEMPERATURE") is None
    monkeypatch.delenv("NOVAIR_MAX_TOKENS", raising=False)
    assert _env_opt("NOVAIR_MAX_TOKENS", int) is None


def test_client_and_agent_reads_env_fallbacks(tmp_path, monkeypatch):
    """NOVAIR_MAX_TOKENS / NOVAIR_TOP_P reach the Agent when flags are unset."""
    import novair.cli as cli

    monkeypatch.setenv("NOVAIR_MAX_TOKENS", "999")
    monkeypatch.setenv("NOVAIR_TOP_P", "0.55")
    monkeypatch.setenv("NOVAIR_API_KEY", "k")
    monkeypatch.setenv("NOVAIR_BASE_URL", "http://mock.test/v1")
    monkeypatch.setenv("NOVAIR_MODEL", "m")
    monkeypatch.chdir(tmp_path)

    parser = build_parser()
    args = parser.parse_args(["run", "hi"])
    _provider, _client, agent = cli._client_and_agent(args, None)
    assert agent.max_tokens == 999
    assert agent.top_p == 0.55
    assert agent.temperature is None


def test_completions_scripts_embed_metadata():
    from novair.completions import script_for

    for shell in ("bash", "zsh", "fish"):
        script = script_for(shell)
        assert len(script.splitlines()) > 10
        for sub in ("chat", "run", "providers", "models", "sessions", "completions"):
            assert sub in script
        assert "openrouter" in script  # preset provider embedded
        assert "max-tokens" in script and "top-p" in script  # fish uses -l top-p


def test_completions_reject_unknown_shell():
    import pytest

    from novair.completions import script_for

    with pytest.raises(ValueError):
        script_for("tcsh")
