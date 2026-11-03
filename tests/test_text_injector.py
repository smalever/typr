import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer, pyqtSignal

from typr.core.text_injector import TextInjector
from typr.platforms.linux_injector import LinuxInjector, LinuxSession


@pytest.fixture
def core():
    return QCoreApplication.instance() or QCoreApplication([])


class Backend(QObject):
    result = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.request = Mock()
        self.cleanup = Mock()
        self.is_cleanup_complete = Mock(return_value=True)


def test_tokens_busy_failure_late_shutdown(core, monkeypatch):
    backend = Backend()
    monkeypatch.setattr("typr.core.text_injector.injection_backend", lambda: lambda: backend)
    injector = TextInjector()
    complete, failures = [], []
    injector.injection_completed.connect(complete.append)
    injector.injection_failed.connect(lambda *args: failures.append(args))
    first, second = object(), object()
    assert injector.request_injection("one", first)
    injector.set_restore_delay(9000)
    assert not injector.request_injection("two", second)
    backend.request.assert_not_called()
    core.processEvents()
    assert failures == [(second, "Text injector is busy")]
    serial = backend.request.call_args.args[0]
    assert backend.request.call_args.args[-1] == 3000
    backend.result.emit(serial, "")
    core.processEvents()
    assert complete == [first]
    assert injector.request_injection("two", second)
    core.processEvents()
    backend.result.emit(serial, "late")
    core.processEvents()
    assert injector._active is not None
    backend.result.emit(backend.request.call_args.args[0], "failure")
    core.processEvents()
    assert failures[-1] == (second, "failure")
    assert injector.request_injection("never starts", object())
    injector.cleanup()
    core.processEvents()
    assert backend.request.call_count == 2
    backend.result.emit(2, "late shutdown")
    core.processEvents()
    assert len(failures) == 2
    assert not injector.request_injection("closed", object())
    assert injector.is_cleanup_complete()
    injector.cleanup()
    backend.cleanup.assert_called_once()


@pytest.mark.parametrize("external", [False, True])
def test_linux_restore_tracks_helper_and_preserves_external(external):
    session = LinuxSession(threading.Event())
    session.backend = "wl-copy"
    session.backup = "original"
    session.pasted = "pasted"
    session.process = Mock()
    session.read = Mock(return_value="new user text" if external else "pasted")
    session.release_helper = Mock()
    restored = Mock()
    session.spawn = Mock(return_value=restored)
    session.restore()
    session.release_helper.assert_called_once()
    if external:
        session.spawn.assert_not_called()
    else:
        session.spawn.assert_called_once_with("original")
        assert session.process is restored


def test_linux_cancel_before_send_and_cleanup():
    stop = threading.Event()
    session = LinuxSession(stop)
    session.ui = Mock()
    session.codes = SimpleNamespace(KEY_LEFTSHIFT=42, KEY_INSERT=110, EV_KEY=1)
    session.detect_backend = Mock(return_value="wl-copy")
    session.read = Mock(return_value="old")
    session.spawn = Mock(side_effect=lambda text: (stop.set(), Mock())[1])
    session.paste("text", 0, 100)
    session.ui.write.assert_not_called()
    session.close()
    session.ui.close.assert_called_once()


def test_linux_worker_nonblocking_shutdown_and_error_observable(core, monkeypatch):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    worker_threads = []

    class Session:
        deadline = None

        def __init__(self, stop):
            worker_threads.append(threading.get_ident())

        def paste(self, *args):
            entered.set()
            assert release.wait(2)
            raise RuntimeError("mock helper failure")

        def release_helper(self):
            pass

        def close(self):
            closed.set()

    monkeypatch.setattr("typr.platforms.linux_injector.LinuxSession", Session)
    backend = LinuxInjector()
    results = []
    backend.result.connect(lambda *args: results.append(args))
    backend.request(1, "text", 0, 0)
    assert entered.wait(2)
    core.processEvents()  # Worker remains blocked, Qt remains responsive.
    # Explicit shutdown is nonjoining even when a helper step is still active.
    backend.cleanup()
    release.set()
    assert closed.wait(2)
    assert worker_threads != [threading.get_ident()]
    core.processEvents()
    assert not results


def test_linux_helper_backend_selection(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "fake")
    monkeypatch.setenv("DISPLAY", "fake")
    monkeypatch.setattr("typr.platforms.linux_injector.shutil.which", lambda name: name)
    assert LinuxSession.detect_backend() == "wl-copy"
    monkeypatch.delenv("WAYLAND_DISPLAY")
    assert LinuxSession.detect_backend() == "xclip"
    monkeypatch.setattr("typr.platforms.linux_injector.shutil.which", lambda name: name == "xsel")
    assert LinuxSession.detect_backend() == "xsel"


def test_linux_worker_failure_delivered_on_qt_thread(core, monkeypatch):
    closed = threading.Event()

    class Session:
        deadline = None

        def __init__(self, stop):
            pass

        def paste(self, *args):
            raise OSError("mock uinput denied")

        def release_helper(self):
            pass

        def close(self):
            closed.set()

    monkeypatch.setattr("typr.platforms.linux_injector.LinuxSession", Session)
    backend = LinuxInjector()
    loop = QEventLoop()
    results = []

    def receive(serial, error):
        results.append((serial, error, threading.get_ident()))
        loop.quit()

    backend.result.connect(receive)
    backend.request(17, "text", 0, 0)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(2000)
    loop.exec()
    timeout.stop()
    backend.cleanup()
    assert closed.wait(2)
    assert results == [(17, "mock uinput denied", threading.get_ident())]


@pytest.mark.parametrize("backend,command", [
    ("wl-copy", ["wl-paste", "-n"]),
    ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
    ("xsel", ["xsel", "--clipboard", "--output"]),
])
def test_linux_helper_read_bounded(backend, command, monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="текст".encode()))
    monkeypatch.setattr("typr.platforms.linux_injector.subprocess.run", run)
    session = LinuxSession(threading.Event())
    session.backend = backend
    assert session.read() == "текст"
    assert run.call_args.args == (command,)
    assert run.call_args.kwargs["timeout"] == 0.5


def test_linux_spawn_bounded_write_and_failure_cleanup(monkeypatch):
    import subprocess

    session = LinuxSession(threading.Event())
    session.backend = "wl-copy"
    process = Mock()
    process.poll.return_value = None
    process.stdin.fileno.return_value = 12
    process.stdin.closed = False
    monkeypatch.setattr(
        "typr.platforms.linux_injector.subprocess.Popen", Mock(return_value=process))
    monkeypatch.setattr("typr.platforms.linux_injector.os.set_blocking", Mock())
    monkeypatch.setattr("typr.platforms.linux_injector.select.select", lambda *a: ([], [12], []))
    write = Mock(side_effect=lambda fd, data: len(data))
    monkeypatch.setattr("typr.platforms.linux_injector.os.write", write)
    assert session.spawn("text") is process
    process.stdin.close.assert_called_once()
    process.terminate.assert_not_called()
    write.side_effect = BrokenPipeError("mock pipe failure")
    process.wait.side_effect = [subprocess.TimeoutExpired("fake", 0.2), 0]
    with pytest.raises(BrokenPipeError):
        session.spawn("text")
    process.terminate.assert_called_once()
    process.kill.assert_called_once()


def test_linux_shift_insert_and_delay_snapshots(monkeypatch):
    stop = Mock()
    stop.is_set.return_value = False
    stop.wait.return_value = False
    session = LinuxSession(stop)
    session.ui = Mock()
    session.codes = SimpleNamespace(KEY_LEFTSHIFT=42, KEY_INSERT=110, EV_KEY=1)
    session.detect_backend = Mock(return_value="xclip")
    session.read = Mock(return_value="old")
    session.spawn = Mock(return_value=Mock())
    monkeypatch.setattr("typr.platforms.linux_injector.time.monotonic", lambda: 10)
    session.paste("text", 0, 3000)
    assert [call.args for call in session.ui.write.call_args_list] == [
        (1, 42, 1), (1, 110, 1), (1, 110, 0), (1, 42, 0)]
    assert [call.args for call in stop.wait.call_args_list] == [(0.12,), (0.001,)]
    assert session.deadline == 13
    session.close()


@pytest.mark.parametrize("backend,command", [
    ("wl-copy", ["wl-copy", "--type", "text/plain;charset=utf-8", "--foreground"]),
    ("xclip", ["xclip", "-selection", "clipboard", "-in", "-quiet"]),
    ("xsel", ["xsel", "--clipboard", "--input", "--nodetach"]),
])
def test_linux_foreground_commands_current_and_restored_cleanup(backend, command, monkeypatch):
    session = LinuxSession(threading.Event())
    session.backend = backend
    current, restored = Mock(), Mock()
    for process in (current, restored):
        process.poll.return_value = None
        process.stdin.fileno.return_value = 12
    popen = Mock(side_effect=[current, restored])
    monkeypatch.setattr("typr.platforms.linux_injector.subprocess.Popen", popen)
    monkeypatch.setattr("typr.platforms.linux_injector.os.set_blocking", Mock())
    monkeypatch.setattr("typr.platforms.linux_injector.select.select", lambda *a: ([], [12], []))
    monkeypatch.setattr("typr.platforms.linux_injector.os.write", lambda fd, data: len(data))
    session.process = session.spawn("pasted")
    session.pasted = "pasted"
    session.backup = "original"
    session.read = Mock(return_value="pasted")
    session.restore()
    assert session.process is restored
    current.terminate.assert_called_once()
    current.wait.assert_called_once_with(timeout=0.2)
    session.close()
    restored.terminate.assert_called_once()
    restored.wait.assert_called_once_with(timeout=0.2)
    assert [call.args[0] for call in popen.call_args_list] == [command, command]


def test_facade_cleanup_without_backend_is_immediate(core):
    injector = TextInjector()
    assert not injector.is_cleanup_complete()
    injector.cleanup()
    assert injector.is_cleanup_complete()


def test_linux_empty_xclip_restore_retains_managed_owner():
    session = LinuxSession(threading.Event())
    session.backend = "xclip"
    session.pasted = "pasted"
    session.read = Mock(return_value="pasted")
    session.process = Mock()
    session.process.poll.return_value = None
    previous = session.process
    restored = Mock()
    restored.poll.return_value = None
    session.spawn = Mock(return_value=restored)
    session.restore()
    previous.terminate.assert_called_once()
    session.spawn.assert_called_once_with("")
    assert session.process is restored
    session.close()
    restored.terminate.assert_called_once()


def test_linux_terminal_initialization_failure_observable(core, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def failed_session(stop):
        entered.set()
        assert release.wait(2)
        raise OSError("mock init failure")

    monkeypatch.setattr("typr.platforms.linux_injector.LinuxSession", failed_session)
    backend = LinuxInjector()
    results = []
    loop = QEventLoop()

    def receive(serial, error):
        results.append((serial, error))
        loop.quit()

    backend.result.connect(receive)
    backend.request(19, "text", 0, 0)
    assert entered.wait(2)
    release.set()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(2000)
    loop.exec()
    timer.stop()
    backend.cleanup()
    backend._thread.join(2)  # Test-only bounded observation, not production UI code.
    assert backend.is_cleanup_complete()
    assert results == [(19, "mock init failure")]
