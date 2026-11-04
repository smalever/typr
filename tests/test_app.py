"""Controller tests with no QApplication, audio dependency, desktop or devices."""

import importlib.util
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PyQt6 import sip
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
    app.audio_recorder.is_operation_complete.return_value = True
    app.audio_recorder.is_cleanup_complete.return_value = True
    app.transcriber = Mock()
    app.transcriber.is_cleanup_complete.return_value = True
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
    app.transcriber.cleanup.assert_called_once()
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


@pytest.fixture
def live_audio(controller, monkeypatch):
    """Real facade with a worker-owned, gated PortAudio test boundary."""
    module, app, core = controller
    entered = {name: threading.Event() for name in ("open", "read", "stop", "close", "terminate")}
    gates = {name: threading.Event() for name in entered}
    for gate in gates.values():
        gate.set()

    class Audio:
        def step(self, name):
            assert threading.get_ident() != threading.main_thread().ident
            entered[name].set()
            assert gates[name].wait(3)

        def RawInputStream(self, **kwargs):
            self.step("open")
            return self

        def start(self):
            pass

        def read(self, *args, **kwargs):
            self.step("read")
            return b"\0\0", False

        def get_sample_size(self, format):
            return 2

        def stop(self, *, ignore_errors):
            assert not ignore_errors
            self.step("stop")

        def close(self, *, ignore_errors):
            assert not ignore_errors
            self.step("close")

        def terminate(self):
            self.step("terminate")

    path = Path(__file__).parents[1] / "src/typr/core/audio_recorder.py"
    spec = importlib.util.spec_from_file_location("typr._app_audio_test", path)
    audio_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audio_module)
    from contextlib import contextmanager
    from types import SimpleNamespace

    @contextmanager
    def session():
        audio = Audio()
        try:
            yield audio
        finally:
            audio.terminate()

    monkeypatch.setattr(audio_module, "OWNER", SimpleNamespace(session=session))
    app.audio_recorder = audio_module.AudioRecorder()
    app.audio_recorder.audio_ready.connect(app._on_audio_ready)
    app.audio_recorder.recording_error.connect(app._on_error)
    app.transcriber = Mock()
    yield module, app, core, entered, gates
    app.audio_recorder.cleanup()
    for gate in gates.values():
        gate.set()
    app.audio_recorder._thread.join(2)
    assert app.audio_recorder.is_cleanup_complete()


def test_quick_release_opening_returns_idle_without_transcription(live_audio):
    module, app, core, entered, gates = live_audio
    gates["open"].clear()
    app._state = module.AppState.IDLE
    app._on_recording_start()
    assert entered["open"].wait(2)
    app._on_recording_stop()
    assert app.get_state() == module.AppState.TRANSCRIBING
    app._on_recording_start()
    gates["open"].set()
    loop, poll, timeout = QEventLoop(), QTimer(), QTimer()
    poll.timeout.connect(lambda: loop.quit() if app.get_state() == module.AppState.IDLE else None)
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    poll.start(1)
    timeout.start(2000)
    loop.exec()
    poll.stop()
    timeout.stop()
    assert app.get_state() == module.AppState.IDLE
    assert not entered["read"].is_set()
    app.transcriber.transcribe.assert_not_called()


@pytest.mark.parametrize("state", ["RECORDING", "TRANSCRIBING", "TYPING"])
@pytest.mark.parametrize("phase", ["open", "read", "stop", "close", "terminate"])
def test_quit_audio_actual_completion_all_states_failed_save(live_audio, monkeypatch, state, phase):
    module, app, core, entered, gates = live_audio
    gates["open"].clear()
    gates[phase].clear()
    app._state = module.AppState.IDLE
    app._on_recording_start()
    assert entered["open"].wait(2)
    if phase in ("read", "stop"):
        gates["open"].set()
        assert entered["read"].wait(2)
    app._state = getattr(module.AppState, state)
    app.config.save.side_effect = OSError("mock save failure")
    app._injection_token = token = object()
    app._injection_text = "pending"
    quit_app = Mock()
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    app._quit()
    if phase != "open":
        gates["open"].set()
        assert entered[phase].wait(2)
    assert not app.audio_recorder.is_cleanup_complete()
    assert app._injection_token is None
    app._on_injection_completed(token)
    app._on_transcription_complete("stale")
    app._on_audio_ready(b"stale")
    responsive = []
    QTimer.singleShot(0, lambda: responsive.append(True))
    core.processEvents()
    assert responsive == [True]
    quit_app.assert_not_called()
    app.transcriber.transcribe.assert_not_called()
    app.history.add.assert_not_called()
    gates[phase].set()
    loop, timeout = QEventLoop(), QTimer()
    quit_app.side_effect = loop.quit
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(2000)
    loop.exec()
    timeout.stop()
    assert app.audio_recorder.is_cleanup_complete()
    assert entered["terminate"].is_set()
    quit_app.assert_called_once()
    app._quit()
    app._finish_quit_when_injection_closed()
    quit_app.assert_called_once()
    app.config.save.assert_called_once()


def test_recovery_and_start_require_completed_audio(controller):
    module, app, _ = controller
    app._state = module.AppState.ERROR
    app.audio_recorder.is_operation_complete.return_value = False
    app._recover_from_error()
    assert app.get_state() == module.AppState.ERROR
    app._state = module.AppState.IDLE
    app._on_recording_start()
    app.audio_recorder.start_recording.assert_not_called()
    app._state = module.AppState.ERROR
    app.audio_recorder.is_operation_complete.return_value = True
    app._recover_from_error()
    assert app.get_state() == module.AppState.IDLE
    app._on_recording_start()
    app.audio_recorder.start_recording.assert_called_once()


def test_quit_requires_both_independent_completion_predicates(controller, monkeypatch):
    module, app, _ = controller
    app.audio_recorder.is_cleanup_complete.return_value = False
    app.text_injector.is_cleanup_complete.return_value = False
    quit_app = Mock()
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    scheduled = []
    monkeypatch.setattr(module.QTimer, "singleShot",
                        lambda delay, callback: scheduled.append(callback))
    app._quit()
    quit_app.assert_not_called()
    app.audio_recorder.is_cleanup_complete.return_value = True
    scheduled.pop()()
    quit_app.assert_not_called()
    app.text_injector.is_cleanup_complete.return_value = True
    scheduled.pop()()
    quit_app.assert_called_once()


@pytest.mark.parametrize("created", [False, True])
def test_settings_lazy_cleanup_joins_existing_barrier(controller, monkeypatch, created):
    module, app, _ = controller
    settings = Mock() if created else None
    app._settings_dialog = settings
    scheduled = []
    monkeypatch.setattr(module.QTimer, "singleShot", lambda ms, cb: scheduled.append(cb))
    quit_app = Mock()
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    if settings is not None:
        settings.is_cleanup_complete.return_value = False
    app._quit()
    if settings is not None:
        settings.cleanup.assert_called_once()
        quit_app.assert_not_called()
        settings.is_cleanup_complete.return_value = True
        scheduled.pop()()
    quit_app.assert_called_once()


@pytest.mark.parametrize("save_fails", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_quit_waits_for_transcriber_http_context_actual_exit(
        controller, monkeypatch, save_fails, fail):
    import httpx

    from typr.core.transcriber import WhisperTranscriber

    module, app, core = controller
    entered, release = threading.Event(), threading.Event()
    closed = threading.Event()

    class Client:
        def __init__(self, **kwargs):
            assert threading.get_ident() != threading.main_thread().ident

        def __enter__(self):
            return self

        def post(self, url, **kwargs):
            if fail:
                raise httpx.ReadTimeout("fake timeout")
            return httpx.Response(200, request=httpx.Request("POST", url), json={"text": "late"})

        def __exit__(self, *args):
            assert threading.get_ident() != threading.main_thread().ident
            entered.set()
            assert release.wait(5)
            closed.set()

    monkeypatch.setattr("typr.core.transcriber.httpx.Client", Client)
    app.transcriber = WhisperTranscriber("fake", "https://fake.invalid/v1")
    app.transcriber.transcription_complete.connect(app._on_transcription_complete)
    app.transcriber.transcription_error.connect(app._on_error)
    app.transcriber.transcribe(b"fake wav")
    worker = app.transcriber._worker
    if save_fails:
        app.config.save.side_effect = OSError("mock save failure")
    quit_app = Mock()
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    try:
        assert entered.wait(2)
        app._quit()
        app._quit()
        responsive = []
        QTimer.singleShot(0, lambda: responsive.append(True))
        core.processEvents()
        assert responsive == [True]
        assert app.transcriber._worker is worker
        native_handle = worker._native_thread
        assert worker.isRunning()
        assert not app.transcriber.is_cleanup_complete()
        quit_app.assert_not_called()
        app.history.add.assert_not_called()
        app.text_injector.request_injection.assert_not_called()
    finally:
        release.set()
        loop, timeout, poll = QEventLoop(), QTimer(), QTimer()
        poll.timeout.connect(lambda: loop.quit() if quit_app.called else None)
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        poll.start(1)
        timeout.start(2000)
        loop.exec()
        poll.stop()
        timeout.stop()
    assert closed.is_set()
    assert app.transcriber.is_cleanup_complete()
    assert sip.isdeleted(worker) or worker.wait(0)
    if native_handle is not None:
        assert native_handle._handle is None
    app._finish_quit_when_injection_closed()
    quit_app.assert_called_once()
    app.config.save.assert_called_once()
    app.history.add.assert_not_called()
    app.text_injector.request_injection.assert_not_called()


def test_quit_requires_transcriber_independent_completion(controller, monkeypatch):
    module, app, _ = controller
    app.transcriber.is_cleanup_complete.return_value = False
    quit_app, scheduled = Mock(), []
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    monkeypatch.setattr(module.QTimer, "singleShot", lambda ms, cb: scheduled.append(cb))
    app._quit()
    app.transcriber.cleanup.assert_called_once()
    quit_app.assert_not_called()
    app.transcriber.is_cleanup_complete.return_value = True
    scheduled.pop()()
    quit_app.assert_called_once()


def test_quit_retains_transcriber_until_native_exit_probe_succeeds(controller, monkeypatch):
    from typr.core.transcriber import WhisperTranscriber

    module, app, core = controller
    app.transcriber = WhisperTranscriber("fake")
    worker = Mock()
    worker.isRunning.return_value = False
    worker.wait.return_value = False
    worker.is_native_exit_complete.side_effect = lambda: worker.wait(0)
    app.transcriber._worker = worker
    app.transcriber._outcome = (True, "late")
    scheduled, outcomes = [], []
    app.transcriber.transcription_complete.connect(outcomes.append)
    monkeypatch.setattr(module.QTimer, "singleShot", lambda ms, cb: scheduled.append(cb))
    quit_app = Mock()
    monkeypatch.setattr(module.QApplication, "quit", quit_app)
    app.config.save.side_effect = OSError("mock save failure")
    app._quit()
    app.transcriber._reap_worker()
    assert app.transcriber._worker is worker
    assert app.transcriber.is_busy()
    assert not app.transcriber.is_cleanup_complete()
    worker.wait.assert_called_once_with(0)
    worker.deleteLater.assert_not_called()
    quit_app.assert_not_called()
    # Both independent timer callbacks must remain gated on the native probe.
    pending, scheduled[:] = scheduled[:], []
    for callback in pending:
        callback()
    quit_app.assert_not_called()
    worker.deleteLater.assert_not_called()
    worker.wait.return_value = True
    pending, scheduled[:] = scheduled[:], []
    for callback in pending:
        callback()
    app._finish_quit_when_injection_closed()
    assert app.transcriber.is_cleanup_complete()
    worker.deleteLater.assert_called_once()
    assert outcomes == []
    quit_app.assert_called_once()
