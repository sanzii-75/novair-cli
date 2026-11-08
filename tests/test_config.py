"""Tests for nexa.config — env-only provider/profile resolution."""
import pytest

from nexa.config import available_profiles, env_hint, resolve


def test_default_profile_from_openai_env(monkeypatch):
    monkeypatch.delenv("NEXA_PROVIDER", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("NEXA_OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    p = resolve()
    assert p.name == "default"
    assert p.api_key == "sk-test"
    assert p.base_url == "https://api.openai.com/v1"
    assert p.model == "gpt-4o-mini"


def test_openrouter_autopicked_when_key_present(monkeypatch):
    monkeypatch.delenv("NEXA_PROVIDER", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-1")
    p = resolve()
    assert p.name == "openrouter"
    assert p.base_url == "https://openrouter.ai/api/v1"
    assert p.model == "openrouter/auto"


def test_custom_profile_resolution(monkeypatch):
    monkeypatch.setenv("NEXA_PROFILE_GROQ_API_KEY", "gsk_1")
    monkeypatch.setenv("NEXA_PROFILE_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("NEXA_PROFILE_GROQ_MODEL", "llama-3.3-70b-versatile")
    p = resolve(provider="groq")
    assert p.name == "groq"
    assert p.api_key == "gsk_1"
    assert p.base_url == "https://api.groq.com/openai/v1"
    assert p.model == "llama-3.3-70b-versatile"
    assert p.key_env_hint == "NEXA_PROFILE_GROQ_API_KEY"


def test_cli_flags_beat_env(monkeypatch):
    monkeypatch.setenv("NEXA_API_KEY", "env-key")
    monkeypatch.setenv("NEXA_MODEL", "env-model")
    p = resolve(base_url="http://localhost:9999/v1", api_key="flag-key", model="flag-model")
    assert p.api_key == "flag-key"
    assert p.model == "flag-model"
    assert p.base_url == "http://localhost:9999/v1"


def test_profile_env_beats_generic_env(monkeypatch):
    monkeypatch.setenv("NEXA_MODEL", "generic")
    monkeypatch.setenv("NEXA_PROFILE_LOCAL_MODEL", "specific")
    p = resolve(provider="local")
    assert p.model == "specific"
    p2 = resolve()
    assert p2.model == "generic"


def test_available_profiles_lists_custom(monkeypatch):
    monkeypatch.setenv("NEXA_PROFILE_GROQ_API_KEY", "gsk_1")
    names = {p["name"] for p in available_profiles()}
    assert {"openrouter", "openai", "default", "groq"} <= names


def test_env_hint_shapes(monkeypatch):
    assert env_hint("openrouter")[0].startswith("export NEXA_OPENROUTER_API_KEY")
    assert env_hint("myprov")[0].startswith("export NEXA_PROFILE_MYPROV_API_KEY")


def test_default_profile_hint_is_nexa_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("NEXA_OPENROUTER_API_KEY", raising=False)
    p = resolve()
    assert p.key_env_hint == "NEXA_API_KEY"


def test_base_url_trailing_slash_stripped(monkeypatch):
    monkeypatch.setenv("NEXA_BASE_URL", "http://x.test/v1/")
    assert resolve().base_url == "http://x.test/v1"


@pytest.mark.parametrize("name,suffix", [("My Provider", "MY_PROVIDER"), ("groq", "GROQ")])
def test_suffix_normalization(name, suffix):
    from nexa.config import _suffix
    assert _suffix(name) == suffix
