"""Project-scoped memory bank — JSON facts under $XDG_DATA_HOME/novair/memory.

Each project (identified by its absolute cwd) gets its own file so facts the
agent retains in one repo never leak into another. Inspired by omp's memory
tools, scaled down to zero dependencies.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from .session import data_dir

MAX_FACTS = 200


def memory_path(project_dir: str) -> Path:
    """Stable per-project file: sha1 of the absolute cwd, first 12 hex chars."""
    key = hashlib.sha1(os.path.abspath(project_dir).encode("utf-8")).hexdigest()[:12]
    return data_dir() / "memory" / f"{key}.json"


def _load(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("facts"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"project": "", "updated": "", "facts": []}


def _save(path: Path, data: Dict[str, Any], project_dir: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["project"] = os.path.abspath(project_dir)
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_fact(project_dir: str, text: str) -> Dict[str, Any]:
    """Store a fact; exact duplicates are ignored. Returns {"added", "total"}."""
    text = text.strip()
    path = memory_path(project_dir)
    data = _load(path)
    if any(f.get("text") == text for f in data["facts"]):
        return {"added": False, "total": len(data["facts"])}
    fact = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "created": time.strftime("%Y-%m-%d"),
    }
    facts = data["facts"] + [fact]
    if len(facts) > MAX_FACTS:  # keep the newest MAX_FACTS entries
        facts = facts[-MAX_FACTS:]
    data["facts"] = facts
    _save(path, data, project_dir)
    return {"added": True, "total": len(facts)}


def search_facts(project_dir: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Case-insensitive substring search over stored facts, newest last."""
    path = memory_path(project_dir)
    data = _load(path)
    needle = query.strip().lower()
    if not needle:
        return []
    hits = [f for f in data["facts"] if needle in str(f.get("text", "")).lower()]
    return hits[-limit:]


def list_facts(project_dir: str) -> List[Dict[str, Any]]:
    return _load(memory_path(project_dir))["facts"]


def count_facts(project_dir: str) -> int:
    return len(_load(memory_path(project_dir))["facts"])


def clear(project_dir: str) -> int:
    """Delete every fact for this project; returns how many were removed."""
    path = memory_path(project_dir)
    removed = len(_load(path)["facts"])
    if path.exists():
        path.unlink()
    return removed
