import builtins
import json

import pytest

from typr import config


@pytest.fixture
def location(tmp_path, monkeypatch):
    directory = tmp_path / "Typr"
    directory.mkdir()
    monkeypatch.setattr(config, "config_dir", lambda: directory)
    return directory / "config.json"


def test_roundtrip_backup_utf8(location, trusted_test_directory):
    settings = config.AppConfig.load()
    settings.api_key = "fake-key"
    settings.transcription.prompt = "Привет 世界"
    settings.save()
    assert config.AppConfig.load().transcription.prompt == "Привет 世界"
    previous = location.read_bytes()
    settings.api_key = "fake-new"
    settings.save()
    assert location.with_suffix(".json.bak").read_bytes() == previous
    assert not list(location.parent.glob("*.tmp"))


@pytest.mark.parametrize("content", [b"\xff", b"{bad", b"[]"])
def test_invalid_config_never_overwritten(location, content):
    location.write_bytes(content)
    settings = config.AppConfig.load()
    assert settings._load_failed
    settings.save()
    assert location.read_bytes() == content


def test_read_error_guard(location, monkeypatch):
    location.write_text('{"api_key":"fake"}', encoding="utf-8")

    def fail(*args, **kwargs):
        raise PermissionError("denied")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", fail)
        settings = config.AppConfig.load()
    settings.save()
    assert json.loads(location.read_text(encoding="utf-8"))["api_key"] == "fake"


def test_tolerates_unknown_fields(location):
    location.write_text('{"unknown":1,"audio":{"unknown":2,"channels":2}}', encoding="utf-8")
    settings = config.AppConfig.load()
    assert not settings._load_failed
    assert settings.audio.channels == 2


def test_backup_failure_preserves_original(location, monkeypatch, trusted_test_directory):
    settings = config.AppConfig.load()
    settings.save()
    previous = location.read_bytes()

    def fail(*args):
        raise OSError("backup refused")

    monkeypatch.setattr(config, "atomic_write", fail)
    settings.api_key = "fake-new"
    with pytest.raises(OSError, match="backup refused"):
        settings.save()
    assert location.read_bytes() == previous


def test_lone_surrogate_load_save_roundtrip(location, trusted_test_directory):
    original = b'{"transcription":{"prompt":"\\ud800"}}'
    location.write_bytes(original)
    settings = config.AppConfig.load()
    assert not settings._load_failed
    assert settings.transcription.prompt == "\ud800"
    settings.save()
    assert config.AppConfig.load().transcription.prompt == "\ud800"
    assert b"\\ud800" in location.read_bytes()
    assert location.with_suffix(".json.bak").read_bytes() == original


def test_deep_json_read_failure_preserves_original(location, monkeypatch):
    original = b'{"unknown":' + b"[" * 100_000 + b"0" + b"]" * 100_000 + b"}"
    location.write_bytes(original)

    def forbidden_write(*args):
        pytest.fail("Failed config load must not attempt persistence")

    monkeypatch.setattr(config, "atomic_write", forbidden_write)
    settings = config.AppConfig.load()
    assert settings._load_failed
    settings.api_key = "fake-new"
    settings.save()
    assert location.read_bytes() == original
    assert not location.with_suffix(".json.bak").exists()
