"""Controller tests with no QApplication, audio dependency, desktop or devices."""

import importlib.util
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer

from typr.core.text_injector import TextInjector
from typr.platforms.linux_injector import LinuxInjector


@pytest.fixture
def controller():
    core = QCoreApplication.instance() or QCoreApplication([])
    audio = ModuleType("typr.core.audio_recorder")
    audio.AudioRecorder = Mock()
    # Stub only the test import boundary; no production fallback for missing PyAudio.
    path = Path(__file__).parents[1] / "src" / "typr" / "app.py"
    spec = importlib.util.spec_from_file_location("typr._stage3_app_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"typr.core.audio_recorder": audio}):
        spec.loader.exec_module(module)
    app = module.TyprApp.__new__(module.TyprApp)
    QObject.__init__(app)
    app._state = module.AppState.TRANSCRIBING
    app._shutting_down = False
    app._quit_completed = False
    app._injection_token = None
    app._injection_text = ""
    app.config = SimpleNamespace(
        ui=SimpleNamespace(show_notifications=True, notification_duration=3000),
        history=SimpleNamespace(enabled=True),
        transcription=SimpleNamespace(model="fake", language="ru"), save=Mock())
    app.history = Mock()
    app.text_injector = Mock()
    app.tray_icon = Mock()
    app.audio_recorder = Mock()
    app.hotkey_manager = Mock()
    yield module, app, core


def test_typing_history_token_and_late_completion(controller):
    module, app, _ = controller
    app._on_transcription_complete("текст")
    token = app.text_injector.request_injection.call_args.args[1]
    assert app._injection_token is token
    assert app.get_state() == module.AppState.TYPING
    app.history.add.assert_called_once()
    app._on_injection_completed(object())
    assert app.get_state() == module.AppState.TYPING
    app._on_recording_start()
    app.audio_recorder.start_recording.assert_not_called()
    app._on_injection_completed(token)
    assert app.get_state() == module.AppState.IDLE
    app._on_injection_failed(token, "late failure")
    assert app.get_state() == module.AppState.IDLE


def test_immediate_callback_has_token_and_failure_keeps_history(controller):
    module, app, _ = controller

    def request(text, token):
        assert app._injection_token is token
        app._on_injection_failed(token, "SendInput failure")

    app.text_injector.request_injection.side_effect = request
    app._on_transcription_complete("text")
    assert app.get_state() == module.AppState.ERROR
    app.history.add.assert_called_once()


def test_quit_invalidates_before_failed_save_and_finally_cleans(controller, monkeypatch):
    module, app, _ = controller
    app._on_transcription_complete("text")
    token = app._injection_token
    order = []
    app.text_injector.cleanup.side_effect = lambda: order.append("injection cleanup")

    def save():
        assert app._injection_token is None
        assert app._shutting_down
        order.append("save")
        raise OSError("mock save failure")

    app.config.save.side_effect = save
    app.audio_recorder.cleanup.side_effect = OSError("mock audio cleanup failure")
    quit_app = Mock()
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    app._quit()
    assert order == ["injection cleanup", "save"]
    app.hotkey_manager.cleanup.assert_called_once()
    quit_app.assert_called_once()
    app._on_injection_completed(token)
    app._on_transcription_complete("late")
    app._on_audio_ready(b"late")
    app._recover_from_error()
    assert app.get_state() == module.AppState.TYPING
    assert app.history.add.call_count == 1
    app._quit()
    assert app.text_injector.cleanup.call_count == 1


@pytest.mark.parametrize("save_fails,close_fails", [(False, False), (True, False), (True, True)])
def test_quit_waits_for_worker_finally_without_blocking_qt(
        controller, monkeypatch, save_fails, close_fails):
    module, app, core = controller
    entered, release = threading.Event(), threading.Event()
    closed = threading.Event()

    class Session:
        deadline = None

        def __init__(self, stop):
            pass

        def paste(self, *args):
            pass

        def close(self):
            entered.set()
            assert release.wait(3)
            closed.set()
            if close_fails:
                raise OSError("mock close failure")

    monkeypatch.setattr("typr.platforms.linux_injector.LinuxSession", Session)
    backend = LinuxInjector()
    monkeypatch.setattr("typr.core.text_injector.injection_backend", lambda: lambda: backend)
    app.text_injector = TextInjector()
    app.text_injector.request_injection("text", object())
    core.processEvents()
    if save_fails:
        app.config.save.side_effect = OSError("mock save failure")
    quit_app = Mock()
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    app._quit()
    assert entered.wait(2)
    try:
        app._quit()
        assert not app.text_injector.is_cleanup_complete()
        responsive = []
        QTimer.singleShot(0, lambda: responsive.append(True))
        core.processEvents()
        assert responsive == [True]
        quit_app.assert_not_called()
    finally:
        release.set()
    loop = QEventLoop()
    quit_app.side_effect = loop.quit
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(2000)
    loop.exec()
    timeout.stop()
    assert closed.is_set()
    assert not backend._thread.is_alive()
    assert app.text_injector.is_cleanup_complete()
    quit_app.assert_called_once()
    app._quit()
    app._finish_quit_when_injection_closed()
    quit_app.assert_called_once()
    app.config.save.assert_called_once()
