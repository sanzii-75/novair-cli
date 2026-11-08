"""Tests for nexa.session — save/load/list/delete under a temp data dir."""
from nexa import session


def test_save_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sid = "test-session"
    msgs = [{"role": "user", "content": "halo"}, {"role": "assistant", "content": "hai"}]
    path = session.save(sid, msgs, {"provider": "openrouter", "model": "m1"})
    assert path.exists()

    data = session.load(sid)
    assert data["id"] == sid
    assert data["messages"] == msgs
    assert data["meta"]["provider"] == "openrouter"
    assert data["meta"]["model"] == "m1"


def test_save_preserves_created(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    session.save("s1", [{"role": "user", "content": "a"}], {})
    first = session.load("s1")["created"]
    session.save("s1", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}], {})
    assert session.load("s1")["created"] == first


def test_list_and_delete(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    session.save("alpha", [{"role": "user", "content": "pertanyaan pertama saya"}], {"provider": "p"})
    session.save("beta", [], {})
    listed = session.list_sessions()
    ids = {s["id"] for s in listed}
    assert {"alpha", "beta"} <= ids
    alpha = next(s for s in listed if s["id"] == "alpha")
    assert "pertanyaan" in alpha["title"] and alpha["provider"] == "p"

    assert session.delete("alpha") is True
    assert session.delete("alpha") is False
    assert session.load("alpha") is None


def test_load_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert session.load("does-not-exist") is None
