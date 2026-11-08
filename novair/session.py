"""Chat session persistence — JSON files under $XDG_DATA_HOME/novair/sessions."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "novair"


def sessions_dir() -> Path:
    path = data_dir() / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _path_for(session_id: str) -> Path:
    sid = session_id if session_id.endswith(".json") else session_id + ".json"
    return sessions_dir() / sid


def save(session_id: str, messages: List[Dict[str, Any]], meta: Dict[str, Any]) -> Path:
    path = _path_for(session_id)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            created = old.get("created", now)
        except (json.JSONDecodeError, OSError):
            created = now
    else:
        created = now
    payload = {
        "id": session_id,
        "created": created,
        "updated": now,
        "meta": meta,
        "messages": messages,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(session_id: str) -> Optional[Dict[str, Any]]:
    path = _path_for(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete(session_id: str) -> bool:
    path = _path_for(session_id)
    if path.exists():
        path.unlink()
        return True
    return False


def _title_of(messages: List[Dict[str, Any]]) -> str:
    for m in messages:
        if m.get("role") == "user":
            text = " ".join(str(m.get("content") or "").split())
            return text[:60] + ("…" if len(text) > 60 else "")
    return "(empty session)"


def list_sessions() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    dir_path = sessions_dir()
    for file in dir_path.glob("*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        msgs = data.get("messages") or []
        meta = data.get("meta") or {}
        out.append(
            {
                "id": data.get("id") or file.stem,
                "updated": data.get("updated") or "?",
                "title": _title_of(msgs),
                "turns": sum(1 for m in msgs if m.get("role") == "user"),
                "provider": meta.get("provider", "?"),
                "model": meta.get("model", "?"),
            }
        )
    out.sort(key=lambda s: s["updated"], reverse=True)
    return out
