"""Facade contracts and lazy platform loading without native registration."""

import importlib
import sys
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication

from typr.config import HotkeyConfig
from typr.core.hotkey_manager import HotkeyManager
from typr.platforms.windows_hotkeys import WindowsHotkeys


def test_lazy_selector_never_loads_evdev_on_windows(monkeypatch):
    from typr.platforms import hotkey_backend

    monkeypatch.setattr(sys, "platform", "win32")
    assert hotkey_backend() is WindowsHotkeys
    assert "evdev" not in sys.modules


def test_invalid_update_preserves_registration_and_active_state(monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication([])
    backend = WindowsHotkeys(HotkeyConfig())
    backend.initialize = lambda: True
    monkeypatch.setattr("typr.core.hotkey_manager.hotkey_backend", lambda: lambda _: backend)
    manager = HotkeyManager()
    events, errors = [], []
    manager.recording_started.connect(lambda: events.append("start"))
    manager.recording_stopped.connect(lambda: events.append("stop"))
    manager.hotkey_error.connect(errors.append)
    assert manager.initialize()
    backend.event.emit(0, 0, "start", "")
    app.processEvents()
    assert not manager.update_shortcut("Ctrl+X, Ctrl+Z")
    assert events == ["start"] and errors
    assert manager.config.push_to_talk == "Ctrl+Alt+Z"
    assert manager.update_shortcut("Shift+F1")
    assert events == ["start", "stop"]
    backend.event.emit(0, 0, "start", "")  # old shortcut event queued before update
    app.processEvents()
    assert events == ["start", "stop"]
    backend.event.emit(0, 1, "start", "")
    app.processEvents()
    manager.cleanup()
    manager.cleanup()
    backend.event.emit(0, 1, "start", "")
    app.processEvents()
    assert events == ["start", "stop", "start", "stop"]


def test_linux_evdev_events_update_reset_and_hotplug(monkeypatch):
    # Fake evdev only in this test, never a production fallback/device access.
    constants = {"EV_KEY": 1, "KEY_SPACE": 57, "KEY_A": 30,
                 "KEY_LEFTMETA": 125, "KEY_RIGHTMETA": 126,
                 "KEY_LEFTSHIFT": 42, "KEY_RIGHTSHIFT": 54,
                 "KEY_LEFTCTRL": 29, "KEY_RIGHTCTRL": 97,
                 "KEY_LEFTALT": 56, "KEY_RIGHTALT": 100,
                 "KEY_ENTER": 28, "KEY_ESC": 1, "KEY_TAB": 15, "KEY_BACKSPACE": 14}
    constants.update({f"KEY_F{i}": i + 58 for i in range(1, 13)})
    from pathlib import Path

    path = str(Path("/fake/event1"))
    device = SimpleNamespace(fd=10, path=path, name="fake",
                             capabilities=lambda: {1: [57]})
    fake = SimpleNamespace(ecodes=SimpleNamespace(**constants), InputDevice=lambda _: device)
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "evdev", fake)
        module = importlib.import_module("typr.platforms.linux_hotkeys")
        try:
            backend = module.LinuxHotkeys(HotkeyConfig())
            events = []
            backend.event.connect(lambda _, kind, message: events.append(kind))
            for code in (29, 56, 44):
                backend._handle_key_event(SimpleNamespace(code=code, value=1))
            backend._handle_key_event(SimpleNamespace(code=44, value=2))
            assert events == ["start"]
            backend.update_shortcut("Shift+F2")
            assert events == ["start", "stop"]
            assert backend._target_key == 60
            patch.setattr(module.Path, "glob", lambda *_: [module.Path("/fake/event1")])
            devices = {}
            backend._scan_for_new_devices(devices)
            assert devices == {10: device}
            backend._scan_for_new_devices(devices)
            assert backend._devices == [device]
            backend._handle_key_event(SimpleNamespace(code=42, value=1))
            backend._handle_key_event(SimpleNamespace(code=60, value=1))
            backend._reset_state()
            assert events[-2:] == ["start", "stop"]
        finally:
            sys.modules.pop("typr.platforms.linux_hotkeys", None)


def test_settings_rejects_invalid_before_mutation_and_does_not_close(monkeypatch):
    from PyQt6.QtGui import QKeySequence

    from typr.ui.settings_dialog import SettingsDialog

    warnings = []
    monkeypatch.setattr("typr.ui.settings_dialog.QMessageBox.warning",
                        lambda *args: warnings.append(args))
    fake = SimpleNamespace(_ptt_hotkey_edit=SimpleNamespace(
        keySequence=lambda: QKeySequence("Ctrl+X, Ctrl+Z")))
    # No config or other widgets: validation must precede every mutation.
    assert SettingsDialog._save_settings(fake) is False
    assert warnings
    fake._save_settings = lambda: False
    fake.settings_saved = SimpleNamespace(emit=lambda: pytest.fail("invalid saved"))
    fake.accept = lambda: pytest.fail("invalid closed")
    SettingsDialog._apply(fake)
    SettingsDialog._save_and_close(fake)
