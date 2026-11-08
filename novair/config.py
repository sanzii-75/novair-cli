"""Provider & profile resolution — environment variables only, no config files.

Resolution order per field:  CLI flag  >  NOVAIR_*  >  profile env  >  preset default.

Profiles
--------
default      NOVAIR_API_KEY / NOVAIR_BASE_URL / NOVAIR_MODEL  (fallbacks: OPENAI_API_KEY ...)
openrouter   NOVAIR_OPENROUTER_API_KEY or OPENROUTER_API_KEY   (featured preset)
openai       NOVAIR_OPENAI_API_KEY or OPENAI_API_KEY           (preset)
<custom>     NOVAIR_PROFILE_<NAME>_API_KEY / _BASE_URL / _MODEL
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

PRESETS: dict = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openrouter/auto",
        "api_key_envs": ("NOVAIR_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
        "model_envs": ("NOVAIR_OPENROUTER_MODEL", "OPENROUTER_MODEL"),
        "docs": "https://openrouter.ai/keys",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_envs": ("NOVAIR_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "model_envs": ("NOVAIR_OPENAI_MODEL", "OPENAI_MODEL"),
        "docs": "https://platform.openai.com/api-keys",
    },
}

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str = ""
    model: str = ""
    key_env_hint: str = ""

    def summary(self) -> str:
        key = "set" if self.api_key else "not set"
        return f"{self.name} · {self.base_url} · model={self.model} · key={key}"


def _env_first(names, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


def _suffix(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", (name or "").upper()).strip("_") or "DEFAULT"


def resolve(
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> Provider:
    """Build a Provider from CLI flags + environment variables."""
    name = provider or os.environ.get("NOVAIR_PROVIDER")
    if not name:
        # Auto-pick the featured preset when its key is around.
        if _env_first(PRESETS["openrouter"]["api_key_envs"]):
            name = "openrouter"
        else:
            name = "default"

    sfx = _suffix(name)
    prof_api = f"NOVAIR_PROFILE_{sfx}_API_KEY"
    prof_base = f"NOVAIR_PROFILE_{sfx}_BASE_URL"
    prof_model = f"NOVAIR_PROFILE_{sfx}_MODEL"

    if name in PRESETS:
        preset = PRESETS[name]
        final_base = base_url or os.environ.get(prof_base) or preset["base_url"]
        final_key = (
            api_key
            or os.environ.get(prof_api)
            or _env_first(preset["api_key_envs"])
        )
        final_model = (
            model
            or os.environ.get(prof_model)
            or _env_first(preset["model_envs"])
            or preset["model"]
        )
        key_hint = preset["api_key_envs"][0]
    else:
        final_base = (
            base_url
            or os.environ.get(prof_base)
            or os.environ.get(f"{sfx}_BASE_URL")
            or os.environ.get("NOVAIR_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or DEFAULT_BASE_URL
        )
        final_key = (
            api_key
            or os.environ.get(prof_api)
            or os.environ.get(f"{sfx}_API_KEY")
            or os.environ.get("NOVAIR_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        final_model = (
            model
            or os.environ.get(prof_model)
            or os.environ.get(f"{sfx}_MODEL")
            or os.environ.get("NOVAIR_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or DEFAULT_MODEL
        )
        key_hint = "NOVAIR_API_KEY" if name == "default" else prof_api

    return Provider(
        name=name,
        base_url=final_base.rstrip("/"),
        api_key=final_key.strip(),
        model=final_model,
        key_env_hint=key_hint,
    )


def available_profiles() -> list[dict]:
    """All profiles detectable from the environment, for `novair providers`."""
    found: dict[str, dict] = {}

    for pname, preset in PRESETS.items():
        key_env = next(
            (e for e in preset["api_key_envs"] if os.environ.get(e)), None
        )
        found[pname] = {
            "name": pname,
            "kind": "preset",
            "base_url": preset["base_url"],
            "model": _env_first(preset["model_envs"]) or preset["model"],
            "key_env": key_env or preset["api_key_envs"][0],
            "has_key": bool(key_env),
            "selected": os.environ.get("NOVAIR_PROVIDER") == pname,
        }

    pat = re.compile(r"^NOVAIR_PROFILE_([A-Z0-9_]+)_(API_KEY|BASE_URL|MODEL)$")
    customs: dict[str, dict] = {}
    for env_name in sorted(os.environ):
        m = pat.match(env_name)
        if not m:
            continue
        cname = m.group(1).lower()
        slot = m.group(2)
        entry = customs.setdefault(
            cname,
            {
                "name": cname,
                "kind": "custom",
                "base_url": "",
                "model": "",
                "key_env": f"NOVAIR_PROFILE_{m.group(1)}_API_KEY",
                "has_key": False,
                "selected": os.environ.get("NOVAIR_PROVIDER", "").lower() == cname,
            },
        )
        if slot == "API_KEY":
            entry["has_key"] = True
        elif slot == "BASE_URL":
            entry["base_url"] = os.environ[env_name]
        elif slot == "MODEL":
            entry["model"] = os.environ[env_name]

    default = {
        "name": "default",
        "kind": "generic",
        "base_url": os.environ.get("NOVAIR_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL,
        "model": os.environ.get("NOVAIR_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or DEFAULT_MODEL,
        "key_env": "NOVAIR_API_KEY",
        "has_key": bool(os.environ.get("NOVAIR_API_KEY") or os.environ.get("OPENAI_API_KEY")),
        "selected": not os.environ.get("NOVAIR_PROVIDER"),
    }

    ordered = [found.pop("openrouter"), found.pop("openai")] + list(customs.values())
    ordered.append(default)
    return ordered


def env_hint(provider_name: str) -> list[str]:
    """`export` lines that configure the given provider."""
    sfx = _suffix(provider_name)
    if provider_name in PRESETS:
        preset = PRESETS[provider_name]
        lines = [f'export {preset["api_key_envs"][0]}="your-api-key"']
        if provider_name == "openrouter":
            lines.append('export NOVAIR_OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"  # optional')
        return lines
    return [
        f'export NOVAIR_PROFILE_{sfx}_API_KEY="your-api-key"',
        f'export NOVAIR_PROFILE_{sfx}_BASE_URL="https://your-endpoint/v1"',
        f'export NOVAIR_PROFILE_{sfx}_MODEL="model-id"',
    ]
