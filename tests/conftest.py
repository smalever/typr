"""Isolate persistence BEFORE test-module imports (including the default logger)."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

_profile = tempfile.TemporaryDirectory(prefix="typr-tests-")
_original = {key: os.environ.get(key) for key in ("HOME", "USERPROFILE", "LOCALAPPDATA")}
for _key in _original:
    os.environ[_key] = str(Path(_profile.name))


@pytest.fixture
def trusted_test_directory(monkeypatch):
    """Unit persistence tests don't assume the developer's profile has safe ACLs.

    Native acceptance/rejection is checked separately, never globally bypassed.
    """
    if sys.platform == "win32":
        from typr.platforms import windows_security

        monkeypatch.setattr(windows_security, "check_private_path", lambda *a, **k: None)


def pytest_unconfigure(config):
    import logging

    logging.shutdown()
    for key, value in _original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    _profile.cleanup()
