import threading

import httpx
import pytest
from PyQt6 import sip
from PyQt6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QObject,
    QThread,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)

from typr.core.transcriber import WhisperTranscriber, _api_error_message, _request_timeout


def _response(payload: object) -> httpx.Response:
    request = httpx.Request("POST", "http://127.0.0.1/v1/audio/transcriptions")
    return httpx.Response(400, request=request, json=payload)


def test_api_error_message_accepts_openai_shape() -> None:
    response = _response({"error": {"message": "bad audio"}})

    assert _api_error_message(response, "fallback") == "bad audio"


def test_api_error_message_accepts_gigastt_shape() -> None:
    response = _response({"error": "pool exhausted", "code": "busy"})

    assert _api_error_message(response, "fallback") == "pool exhausted (busy)"


def test_api_error_message_tolerates_other_shapes() -> None:
    assert _api_error_message(_response({"error": ["bad"]}), "fallback") == "fallback"
    assert _api_error_message(_response("bad"), "fallback") == "fallback"


def test_local_gigastt_uses_longer_read_timeout() -> None:
    gigastt = _request_timeout("http://127.0.0.1:9876/v1", "gigaam-v3-rnnt")
    parakeet = _request_timeout("http://127.0.0.1:5092/v1", "parakeet-tdt-0.6b-v3")

    assert gigastt.connect == 10.0
    assert gigastt.read == 120.0
    assert parakeet.read == 30.0


def _until(core, predicate):
    loop, poll, timeout = QEventLoop(), QTimer(), QTimer()
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    poll.start(1)
    timeout.start(2000)
    if not predicate():
        loop.exec()
    poll.stop()
    timeout.stop()
    assert predicate()


@pytest.fixture
def gated_http(monkeypatch):
    core = QCoreApplication.instance() or QCoreApplication([])
    entered, release, posted = threading.Event(), threading.Event(), threading.Event()
    calls = []
    state = {"fail": False}

    class Client:
        def __init__(self, **kwargs):
            assert threading.get_ident() != threading.main_thread().ident
            calls.append(kwargs)

        def __enter__(self):
            return self

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            posted.set()
            if state["fail"]:
                raise httpx.ReadTimeout("fake timeout")
            return httpx.Response(200, request=httpx.Request("POST", url), json={"text": "text"})

        def __exit__(self, *args):
            assert threading.get_ident() != threading.main_thread().ident
            entered.set()
            assert release.wait(5)

    monkeypatch.setattr("typr.core.transcriber.httpx.Client", Client)
    transcriber = WhisperTranscriber("fake", "https://fake.invalid/v1/", "fake-model")
    yield core, transcriber, entered, release, posted, calls, state
    transcriber.cleanup()
    release.set()
    _until(core, transcriber.is_cleanup_complete)


@pytest.mark.parametrize("fail", [False, True])
def test_busy_retains_thread_until_http_context_exit(gated_http, fail):
    core, transcriber, entered, release, _, calls, state = gated_http
    state["fail"] = fail
    completed, errors, responsive, destroyed = [], [], [], []
    transcriber.transcription_complete.connect(completed.append)
    transcriber.transcription_error.connect(errors.append)
    transcriber.transcribe(b"wav")
    worker = transcriber._worker
    worker.destroyed.connect(lambda: destroyed.append(True))
    try:
        assert entered.wait(2)
        native_handle = worker._native_thread
        QTimer.singleShot(0, lambda: responsive.append(True))
        core.processEvents()
        assert responsive == [True]
        assert transcriber._worker is worker
        assert worker.isRunning()
        assert transcriber.is_busy()
        assert completed == errors == destroyed == []
        transcriber.transcribe(b"overlap")
        assert transcriber._worker is worker
        assert len(calls) == 2
    finally:
        release.set()
    _until(core, lambda: not transcriber.is_busy())
    assert completed == ([] if fail else ["text"])
    assert errors == (["Request timed out"] if fail else [])
    assert sip.isdeleted(worker) or worker.wait(0)
    if native_handle is not None:
        assert native_handle._handle is None  # Closed only after OS-thread exit, not Qt wait.
    transcriber.transcribe(b"again")
    assert transcriber._worker is not worker
    _until(core, lambda: not transcriber.is_busy())
    assert len(calls) == 4


@pytest.mark.parametrize("fail", [False, True])
def test_terminal_cleanup_suppresses_queued_results_and_rejects_jobs(gated_http, fail):
    core, transcriber, entered, release, _, calls, state = gated_http
    state["fail"] = fail
    outcomes = []
    transcriber.transcription_complete.connect(outcomes.append)
    transcriber.transcription_error.connect(outcomes.append)
    assert not transcriber.is_cleanup_complete()
    transcriber.transcribe(b"wav")
    worker = transcriber._worker
    try:
        assert entered.wait(2)
        transcriber.cleanup()
        transcriber.cleanup()
        transcriber.transcribe(b"late")
        transcriber.transcribe(b"")
        core.processEvents()
        assert not transcriber.is_cleanup_complete()
        assert transcriber._worker is worker
        assert outcomes == []
    finally:
        release.set()
    _until(core, transcriber.is_cleanup_complete)
    transcriber.transcribe(b"terminal")
    core.processEvents()
    assert outcomes == []
    assert len(calls) == 2


def test_main_thread_relay_and_reentrant_completion_keep_new_job(gated_http):
    core, transcriber, entered, release, _, calls, _ = gated_http
    outcomes = []

    class Receiver(QObject):
        @pyqtSlot(str)
        def complete(self, text):
            assert QThread.currentThread() is core.thread()
            assert transcriber._worker is None
            outcomes.append(text)
            if len(outcomes) == 1:
                transcriber.transcribe(b"reentrant")
                assert transcriber._worker is not None

    receiver = Receiver()
    transcriber.transcription_complete.connect(receiver.complete)
    # The started callback must also observe busy ownership, never overwrite it.
    transcriber.transcription_started.connect(lambda: transcriber.transcribe(b"nested start"))
    transcriber.transcribe(b"wav")
    try:
        assert entered.wait(2)
        core.processEvents()
        assert outcomes == []
    finally:
        release.set()
    _until(core, lambda: len(outcomes) == 2 and not transcriber.is_busy())
    assert len(calls) == 4
    url, payload = calls[1]
    assert url == "https://fake.invalid/v1/audio/transcriptions"
    assert payload == {
        "headers": {"Authorization": "Bearer fake"},
        "files": {"file": ("audio.wav", b"wav", "audio/wav")},
        "data": {"model": "fake-model"},
    }


def test_stale_sender_cannot_replace_active_outcome(gated_http):
    core, transcriber, entered, release, _, _, _ = gated_http

    class StaleWorker(QObject):
        result = pyqtSignal(str)
        error = pyqtSignal(str)
        finished = pyqtSignal()

    stale = StaleWorker()
    stale.result.connect(transcriber._on_result)
    stale.error.connect(transcriber._on_error)
    stale.finished.connect(transcriber._on_worker_exited)
    outcomes = []
    transcriber.transcription_complete.connect(outcomes.append)
    transcriber.transcription_error.connect(outcomes.append)
    transcriber.transcribe(b"wav")
    worker = transcriber._worker
    try:
        assert entered.wait(2)
        core.processEvents()
        stale.result.emit("stale result")
        stale.error.emit("stale error")
        stale.finished.emit()
        assert transcriber._worker is worker
        assert outcomes == []
    finally:
        release.set()
    _until(core, lambda: not transcriber.is_busy())
    assert outcomes == ["text"]


@pytest.mark.parametrize("closing", [False, True])
def test_native_exit_probe_retains_finished_worker_and_retries(gated_http, monkeypatch, closing):
    core, transcriber, entered, release, _, calls, _ = gated_http
    transcriber.transcribe(b"wav")
    worker = transcriber._worker
    native_wait = worker.wait
    allow_exit = threading.Event()
    probes, outcomes, destroyed = [], [], []

    def wait(timeout):
        assert timeout == 0  # Never permit a blocking join from the facade.
        probes.append(timeout)
        return allow_exit.is_set() and native_wait(0)

    monkeypatch.setattr(worker, "wait", wait)
    worker.destroyed.connect(lambda: destroyed.append(True))
    transcriber.transcription_complete.connect(outcomes.append)
    try:
        assert entered.wait(2)
        release.set()
        _until(core, lambda: not worker.isRunning())
        core.processEvents()
        if closing:
            transcriber.cleanup()
        responsive = []
        QTimer.singleShot(0, lambda: responsive.append(True))
        # Exercise the retry timer, not just the finished signal handler.
        _until(core, lambda: len(probes) >= 2 and bool(responsive))
        assert transcriber._worker is worker
        assert transcriber.is_busy()
        assert not transcriber.is_cleanup_complete()
        assert outcomes == destroyed == []
        transcriber.transcribe(b"overlap")
        assert transcriber._worker is worker
        assert len(calls) == 2
    finally:
        release.set()
        allow_exit.set()
    _until(core, lambda: not transcriber.is_busy())
    assert transcriber.is_cleanup_complete() is closing
    assert outcomes == ([] if closing else ["text"])
    assert sip.isdeleted(worker) or worker.wait(0)
