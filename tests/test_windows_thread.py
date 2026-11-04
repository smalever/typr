"""No desktop: Win32 handle doubles and a contained native FLS finalizer."""

import ctypes as C
import sys
import threading
from ctypes import wintypes as W
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

from typr.core.transcriber import TranscriberWorker, WhisperTranscriber
from typr.platforms.windows_thread import ThreadHandle


@pytest.fixture
def kernel(monkeypatch):
    monkeypatch.setattr(C, "get_last_error", lambda: 5, raising=False)
    return SimpleNamespace(GetCurrentThreadId=Mock(return_value=123),
                           OpenThread=Mock(return_value=456),
                           WaitForSingleObject=Mock(return_value=258),
                           CloseHandle=Mock(return_value=True))


def test_handle_ownership_and_zero_timeout(kernel):
    handle = ThreadHandle(kernel)
    kernel.OpenThread.assert_called_once_with(0x00100000, False, 123)
    assert kernel.OpenThread.restype is W.HANDLE
    assert kernel.WaitForSingleObject.argtypes == [W.HANDLE, W.DWORD]
    assert not handle.is_exited()
    with pytest.raises(RuntimeError, match="before native exit"):
        handle.close()
    kernel.CloseHandle.assert_not_called()
    kernel.WaitForSingleObject.return_value = 0
    assert handle.is_exited()
    handle.close()
    handle.close()
    kernel.CloseHandle.assert_called_once_with(456)
    assert all(call.args == (456, 0) for call in kernel.WaitForSingleObject.call_args_list)


@pytest.mark.parametrize("operation", ["open", "probe", "close"])
def test_handle_errors_are_explicit(kernel, operation):
    if operation == "open":
        kernel.OpenThread.return_value = None
        with pytest.raises(OSError, match="OpenThread"):
            ThreadHandle(kernel)
        return
    handle = ThreadHandle(kernel)
    kernel.WaitForSingleObject.return_value = 0xFFFFFFFF if operation == "probe" else 0
    kernel.CloseHandle.return_value = False
    message = "WaitForSingleObject" if operation == "probe" else "CloseHandle"
    with pytest.raises(OSError, match=message):
        handle.is_exited() if operation == "probe" else handle.close()
    assert handle._handle == 456


@pytest.mark.skipif(sys.platform != "win32", reason="Windows FLS acceptance")
@pytest.mark.parametrize("closing", [False, True])
def test_held_fls_finalizer_blocks_facade_reap(monkeypatch, closing):
    core = QCoreApplication.instance() or QCoreApplication([])
    kernel = C.WinDLL("kernel32", use_last_error=True)
    callback_type = C.WINFUNCTYPE(None, C.c_void_p)
    kernel.FlsAlloc.argtypes, kernel.FlsAlloc.restype = [callback_type], W.DWORD
    kernel.FlsSetValue.argtypes, kernel.FlsSetValue.restype = [W.DWORD, C.c_void_p], W.BOOL
    kernel.FlsFree.argtypes, kernel.FlsFree.restype = [W.DWORD], W.BOOL
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    callbacks = []
    exit_statuses = []

    class CheckedHandle(ThreadHandle):
        def close(self):
            exit_statuses.append(kernel.WaitForSingleObject(self._handle, 0))
            super().close()

    @callback_type
    def finalizer(value):
        entered.set()
        callbacks.append(release.wait(5))
        returned.set()

    index = kernel.FlsAlloc(finalizer)
    assert index != 0xFFFFFFFF

    class Worker(TranscriberWorker):
        def run(self):
            self._native_thread = CheckedHandle()
            assert kernel.FlsSetValue(index, C.c_void_p(1))
            self.result.emit("done")

    monkeypatch.setattr("typr.core.transcriber.TranscriberWorker", Worker)
    transcriber = WhisperTranscriber("fake")
    outcomes = []
    transcriber.transcription_complete.connect(outcomes.append)
    transcriber.transcribe(b"contained, no HTTP")
    worker = transcriber._worker
    handle = None
    try:
        assert entered.wait(2)
        handle = worker._native_thread
        # Reproduce Qt6.12 Windows discrepancy against an independent OS wait.
        assert worker.wait(0)
        assert not worker.isRunning()
        assert not handle.is_exited()
        assert kernel.WaitForSingleObject(handle._handle, 0) == 258
        core.processEvents()
        if closing:
            transcriber.cleanup()
        responsive = []
        QTimer.singleShot(0, lambda: responsive.append(True))
        core.processEvents()
        assert responsive == [True]
        assert transcriber._worker is worker
        assert transcriber.is_busy()
        assert not transcriber.is_cleanup_complete()
        assert outcomes == []
        transcriber.transcribe(b"overlap")
        assert transcriber._worker is worker
    finally:
        release.set()
        loop, poll, timeout = QEventLoop(), QTimer(), QTimer()
        poll.timeout.connect(lambda: loop.quit() if not transcriber.is_busy() else None)
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        poll.start(1)
        timeout.start(2000)
        loop.exec()
        poll.stop()
        timeout.stop()
        transcriber.cleanup()
        assert returned.wait(2)
        assert kernel.FlsFree(index)
    assert callbacks == [True]
    assert exit_statuses == [0]
    assert not transcriber.is_busy()
    assert transcriber.is_cleanup_complete()
    assert handle._handle is None
    assert outcomes == ([] if closing else ["done"])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows worker failure policy")
@pytest.mark.parametrize("failure", ["open", "probe", "close"])
def test_worker_native_failure_policy(monkeypatch, caplog, failure):
    core = QCoreApplication.instance() or QCoreApplication([])
    worker = TranscriberWorker("fake", "https://fake.invalid", b"wav", "fake", None, "")
    monkeypatch.setattr(worker, "wait", lambda timeout: True)
    handle = Mock()
    if failure == "open":
        worker._native_error = "OpenThread failed"
    else:
        worker._native_thread = handle
        handle.is_exited.return_value = True
        if failure == "probe":
            handle.is_exited.side_effect = OSError("probe failed")
        else:
            handle.close.side_effect = OSError("close failed")
    assert worker.is_native_exit_complete() is (failure == "close")
    if failure != "close":
        assert not worker.is_native_exit_complete()
        assert caplog.text.count("Shutdown blocked") == 1
        handle.close.assert_not_called()
    else:
        assert "handle cleanup failed" in caplog.text
    assert core is not None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows OpenThread failure")
def test_open_failure_aborts_before_http_and_blocks_unverified_reap(monkeypatch, caplog):
    core = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setattr("typr.platforms.windows_thread.ThreadHandle",
                        Mock(side_effect=OSError("OpenThread denied")))
    client = Mock(side_effect=AssertionError("HTTP must not start"))
    monkeypatch.setattr("typr.core.transcriber.httpx.Client", client)
    worker = TranscriberWorker("fake", "https://fake.invalid", b"wav", "fake", None, "")
    errors = []
    worker.error.connect(errors.append)
    worker.run()  # Creation failure before any native/network work; deterministic boundary.
    monkeypatch.setattr(worker, "wait", lambda timeout: True)
    assert not worker.is_native_exit_complete()
    assert errors == ["Transcription failed: OpenThread denied"]
    client.assert_not_called()
    assert "Shutdown blocked: native thread exit unverified" in caplog.text
    assert core is not None
