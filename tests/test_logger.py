import logging
import sys
import uuid

import pytest

from typr.utils import logger as module


def test_consoleless_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    log = module.setup_logger(f"test-{uuid.uuid4()}")
    try:
        log.info("Привет 世界")
        assert len(log.handlers) == 1
        assert isinstance(log.handlers[0], logging.FileHandler)
        log.handlers[0].flush()
        assert "Привет 世界" in (tmp_path / "typr.log").read_text(encoding="utf-8")
        assert module.setup_logger(log.name) is log
    finally:
        for handler in log.handlers[:]:
            handler.close()
            log.removeHandler(handler)


def test_log_error_is_explicit_and_retryable(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(module, "log_dir", lambda: blocker)
    name = f"test-{uuid.uuid4()}"
    with pytest.raises(OSError, match="Cannot initialize Typr log"):
        module.setup_logger(name)
    assert not logging.getLogger(name).handlers
