import builtins

import pytest

from typr.core import history


@pytest.fixture
def location(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_DIR", tmp_path)
    file = tmp_path / "history.json"
    monkeypatch.setattr(history, "HISTORY_FILE", file)
    return file


def test_unicode_roundtrip(location, trusted_test_directory):
    manager = history.HistoryManager(max_entries=1)
    manager.add(history.HistoryEntry.create("старое"))
    manager.add(history.HistoryEntry.create("世界"))
    assert [e.text for e in history.HistoryManager().entries()] == ["世界"]


@pytest.mark.parametrize("content", [b"\xff", b"bad", b"null", b'[1]',
                                     b'{"entries":{}}', b'{"entries":[{}]}'])
def test_bad_history_preserved_after_all_mutations(location, content):
    location.write_bytes(content)
    manager = history.HistoryManager()
    assert manager._load_failed
    manager.add(history.HistoryEntry.create("new"))
    manager.set_max_entries(1)
    manager.delete(manager.entries()[0].id)
    manager.clear()
    assert location.read_bytes() == content


def test_history_read_oserror_guard(location, monkeypatch):
    location.write_bytes(b"original")

    def fail(*args, **kwargs):
        raise PermissionError("denied")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", fail)
        manager = history.HistoryManager()
    manager.clear()
    assert location.read_bytes() == b"original"


def test_lone_surrogate_load_save_add_roundtrip(location, trusted_test_directory):
    location.write_bytes(
        b'{"entries":[{"id":"existing","timestamp":"2026-11-03T00:00:00",'
        b'"text":"\\ud800"}]}'
    )
    manager = history.HistoryManager()
    assert not manager._load_failed
    assert manager.entries()[0].text == "\ud800"
    manager._save()
    assert history.HistoryManager().entries()[0].text == "\ud800"
    manager.add(history.HistoryEntry.create("new \ud800"))
    assert [entry.text for entry in history.HistoryManager().entries()] == [
        "new \ud800", "\ud800"
    ]
    assert b"\\ud800" in location.read_bytes()


def test_deep_json_read_failure_preserves_original(location, monkeypatch):
    original = b'{"entries":' + b"[" * 100_000 + b"0" + b"]" * 100_000 + b"}"
    location.write_bytes(original)

    def forbidden_write(*args):
        pytest.fail("Failed history load must not attempt persistence")

    monkeypatch.setattr(history, "atomic_write", forbidden_write)
    manager = history.HistoryManager()
    assert manager._load_failed
    manager.add(history.HistoryEntry.create("new"))
    manager.set_max_entries(1)
    manager.delete(manager.entries()[0].id)
    manager.clear()
    assert location.read_bytes() == original
