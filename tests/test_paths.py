import os
import subprocess
import sys
from pathlib import Path

import pytest

from typr.platforms import paths


def test_platform_import_does_not_require_evdev():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import typr.platforms.paths; "
         "import typr.config; import typr.core.history; "
         "assert 'evdev' not in sys.modules"],
        capture_output=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_linux_paths_ignore_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "ignored"))
    assert paths.config_dir() == tmp_path / ".config" / "typr"
    assert paths.history_dir() == tmp_path / ".local" / "share" / "typr"
    assert paths.log_dir() == paths.config_dir() / "logs"


def test_windows_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.config_dir() == tmp_path / "Typr"
    assert paths.history_dir() == paths.config_dir()
    monkeypatch.delenv("LOCALAPPDATA")
    with pytest.raises(OSError, match="LOCALAPPDATA"):
        paths.config_dir()
    monkeypatch.setenv("LOCALAPPDATA", "relative")
    with pytest.raises(OSError, match="absolute"):
        paths.config_dir()


def test_atomic_private_write_and_replace_failure(tmp_path, monkeypatch, trusted_test_directory):
    target = tmp_path / "private" / "config.json"
    paths.atomic_write(target, b"old")
    if sys.platform == "linux":
        assert target.stat().st_mode & 0o777 == 0o600

    def fail(*args):
        raise OSError("replace denied")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="replace denied"):
        paths.atomic_write(target, b"new")
    assert target.read_bytes() == b"old"
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.skipif(sys.platform != "win32", reason="Native read-only Windows security check")
def test_windows_acl_on_temporary_directory(tmp_path):
    from typr.platforms.windows_security import check_private_path

    with pytest.raises(OSError, match="profile"):
        check_private_path(Path("C:/"))
    try:
        check_private_path(tmp_path)
    except OSError as error:
        # Exercise actual refusal before marking the positive native gate unmet.
        target = tmp_path / "refused" / "config.json"
        with pytest.raises(OSError):
            paths.atomic_write(target, b"fake-key")
        assert not target.exists()
        pytest.xfail(f"Native private-profile acceptance gate unavailable: {error}")
    # Real binding, real inherited ACLs, only a temporary directory and fake key.
    from typr.config import AppConfig

    target = tmp_path / "native" / "config.json"
    settings = AppConfig(CONFIG_DIR=target.parent, CONFIG_FILE=target, api_key="fake-key")
    settings.save()
    settings.api_key = "fake-new"
    settings.save()
    check_private_path(target)
    check_private_path(target.with_suffix(".json.bak"))
    assert b"fake-key" in target.with_suffix(".json.bak").read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows security boundary")
def test_windows_acl_failure_precedes_secret_creation(tmp_path, monkeypatch):
    from typr.platforms import windows_security

    def deny(*args, **kwargs):
        raise OSError("unsafe DACL")

    monkeypatch.setattr(windows_security, "check_private_path", deny)
    target = tmp_path / "must-not-exist" / "config.json"
    with pytest.raises(OSError, match="unsafe DACL"):
        paths.atomic_write(target, b"fake-secret")
    assert not target.parent.exists()
