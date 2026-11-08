"""Tests for novair.memory — per-project fact storage."""
from novair import memory


def _set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def test_add_and_search_facts(tmp_path, monkeypatch):
    _set_data_dir(tmp_path, monkeypatch)
    memory.add_fact(str(tmp_path), "build with make -j4")
    memory.add_fact(str(tmp_path), "tests use pytest -q")
    assert memory.count_facts(str(tmp_path)) == 2
    hits = memory.search_facts(str(tmp_path), "pytest")
    assert len(hits) == 1 and "pytest" in hits[0]["text"]
    assert memory.search_facts(str(tmp_path), "MISSING") == []


def test_duplicate_fact_ignored(tmp_path, monkeypatch):
    _set_data_dir(tmp_path, monkeypatch)
    assert memory.add_fact(str(tmp_path), "same fact")["added"] is True
    assert memory.add_fact(str(tmp_path), "same fact")["added"] is False
    assert memory.count_facts(str(tmp_path)) == 1


def test_projects_are_scoped(tmp_path, monkeypatch):
    _set_data_dir(tmp_path, monkeypatch)
    proj_a = tmp_path / "projA"
    proj_b = tmp_path / "projB"
    proj_a.mkdir()
    proj_b.mkdir()
    memory.add_fact(str(proj_a), "only in A")
    memory.add_fact(str(proj_b), "only in B")
    assert memory.search_facts(str(proj_a), "only") [0]["text"] == "only in A"
    assert memory.search_facts(str(proj_b), "only") [0]["text"] == "only in B"
    # two distinct files on disk
    files = list((tmp_path / "data" / "novair" / "memory").glob("*.json"))
    assert len(files) == 2


def test_clear(tmp_path, monkeypatch):
    _set_data_dir(tmp_path, monkeypatch)
    memory.add_fact(str(tmp_path), "fact one")
    memory.add_fact(str(tmp_path), "fact two")
    assert memory.clear(str(tmp_path)) == 2
    assert memory.count_facts(str(tmp_path)) == 0


def test_corrupt_file_treated_as_empty(tmp_path, monkeypatch):
    _set_data_dir(tmp_path, monkeypatch)
    memory.add_fact(str(tmp_path), "keep me")
    path = memory.memory_path(str(tmp_path))
    path.write_text("{corrupt json", encoding="utf-8")
    assert memory.count_facts(str(tmp_path)) == 0
    assert memory.list_facts(str(tmp_path)) == []
