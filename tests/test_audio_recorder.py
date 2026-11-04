"""Deterministic PortAudio doubles; no audio hardware or QApplication."""

import importlib.util
import io
import sys
import threading
import wave
from pathlib import Path
from queue import Queue
from types import ModuleType
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

from typr.config import AudioConfig


def spin_until(predicate):
    """Bound a failed test, not the production operation or a device call."""
    loop = QEventLoop()
    poll, timeout = QTimer(), QTimer()
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


class FakeAudio:
    def __init__(self):
        self.calls = []
        self.gates = {}
        self.entered = {
            name: threading.Event() for name in
            ("construct", "devices", "open", "read", "stop_stream", "close", "terminate")
        }
        self.errors = {}
        self.read_release = threading.Event()
        self.options = None

    def call(self, name):
        self.calls.append((name, threading.get_ident()))
        self.entered[name].set()
        if name in self.gates:
            assert self.gates[name].wait(3), f"test did not release {name}"
        if name in self.errors:
            raise self.errors[name]

    def construct(self):
        self.call("construct")
        return self

    def get_device_count(self):
        self.call("devices")
        return 2

    def get_device_info_by_index(self, index):
        return {"name": "Microphone" if index else "Output", "maxInputChannels": index}

    def open(self, **kwargs):
        self.options = kwargs
        self.call("open")
        return self

    def read(self, *args, **kwargs):
        self.call("read")
        assert self.read_release.wait(3)
        return b"\x01\x00" * 1024

    def stop_stream(self):
        self.call("stop_stream")

    def close(self):
        self.call("close")

    def terminate(self):
        self.call("terminate")

    def get_sample_size(self, format):
        assert threading.get_ident() != threading.main_thread().ident
        return 2


@pytest.fixture
def audio_module():
    # Import-boundary only: production still requires the real PyAudio dependency.
    stub = ModuleType("pyaudio")
    stub.paInt16 = 8
    stub.PyAudio = lambda: None
    path = Path(__file__).parents[1] / "src/typr/core/audio_recorder.py"
    spec = importlib.util.spec_from_file_location("typr._audio_lifecycle_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"pyaudio": stub}):
        spec.loader.exec_module(module)
    return module


@pytest.fixture
def recorder(audio_module, monkeypatch):
    core = QCoreApplication.instance() or QCoreApplication([])
    fake = FakeAudio()
    monkeypatch.setattr(audio_module.pyaudio, "PyAudio", fake.construct)
    recorder = audio_module.AudioRecorder()
    yield recorder, fake, core
    recorder.cleanup()
    for gate in fake.gates.values():
        gate.set()
    fake.read_release.set()
    spin_until(recorder.is_cleanup_complete)


def responsive(core):
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    core.processEvents()
    assert ticks == [True]


@pytest.mark.parametrize("phase", ["construct", "open"])
@pytest.mark.parametrize("action", ["stop", "cancel", "cleanup"])
def test_delayed_open_quick_release_cancel_shutdown(recorder, action, phase):
    rec, fake, core = recorder
    fake.gates[phase] = threading.Event()
    ready, errors = [], []
    rec.audio_ready.connect(ready.append)
    rec.recording_error.connect(errors.append)
    assert rec.start_recording()
    assert fake.entered[phase].wait(2)
    {"stop": rec.stop_recording, "cancel": rec.cancel_recording,
     "cleanup": rec.cleanup}[action]()
    assert not rec.is_operation_complete()
    assert not rec.start_recording()
    responsive(core)
    fake.gates[phase].set()
    spin_until(rec.is_operation_complete)
    spin_until(lambda: bool(ready) if action == "stop" else rec.is_operation_complete())
    core.processEvents()
    assert ready == ([b""] if action == "stop" else [])
    assert errors == []
    assert not fake.entered["read"].is_set()
    if phase == "open":
        assert [name for name, _ in fake.calls][-3:] == ["stop_stream", "close", "terminate"]
    else:
        assert not fake.entered["open"].is_set()
        assert fake.calls[-1][0] == "terminate"
    assert all(tid != threading.get_ident() for _, tid in fake.calls)
    assert rec.is_cleanup_complete() == (action == "cleanup")


@pytest.mark.parametrize("phase", ["stop_stream", "close", "terminate"])
def test_delayed_teardown_wav_and_actual_completion(recorder, phase):
    rec, fake, core = recorder
    fake.gates[phase] = threading.Event()
    results = []
    rec.audio_ready.connect(lambda data: results.append((data, rec.is_operation_complete())))
    assert rec.start_recording()
    assert fake.entered["read"].wait(2)
    rec.stop_recording()
    fake.read_release.set()
    assert fake.entered[phase].wait(2)
    responsive(core)
    assert not rec.is_operation_complete()
    assert results == []
    assert not rec.request_devices()
    fake.gates[phase].set()
    spin_until(lambda: bool(results))
    data, completed = results[0]
    assert completed
    with wave.open(io.BytesIO(data), "rb") as wav:
        assert (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) == (1, 16000, 2)
        assert wav.readframes(1024) == b"\x01\x00" * 1024


@pytest.mark.parametrize("phase,message", [
    ("construct", "no device"), ("open", "privacy denied"), ("read", "device removed"),
    ("stop_stream", "stop failed"), ("close", "close failed"), ("terminate", "terminate failed"),
])
def test_errors_cleanup_and_retry(recorder, phase, message):
    rec, fake, core = recorder
    fake.errors[phase] = OSError(message)
    fake.read_release.set()
    # Gate teardown failures so the main thread can request stop deterministically.
    fake.gates["open"] = threading.Event()
    errors = []
    rec.recording_error.connect(lambda error: errors.append((error, rec.is_operation_complete())))
    assert rec.start_recording()
    if phase in ("stop_stream", "close", "terminate"):
        assert fake.entered["open"].wait(2)
        rec.stop_recording()
    fake.gates["open"].set()
    spin_until(lambda: bool(errors))
    assert message in errors[0][0]
    assert errors[0][1]
    if phase != "construct":
        assert fake.entered["terminate"].is_set()
    if phase in ("read", "stop_stream", "close", "terminate"):
        assert fake.entered["close"].is_set()
    fake.errors.clear()
    devices = []
    rec.devices_ready.connect(devices.append)
    assert rec.request_devices()
    spin_until(lambda: bool(devices))
    assert devices == [[{"index": 1, "name": "Microphone", "channels": 1}]]
    responsive(core)


@pytest.mark.parametrize("device,index", [(None, None), ("missing", None), ("Microphone", 1)])
def test_device_resolution_and_config_snapshot(recorder, device, index):
    rec, fake, _ = recorder
    rec.config = AudioConfig(input_device=device)
    fake.gates["construct"] = threading.Event()
    assert rec.start_recording()
    assert fake.entered["construct"].wait(2)
    rec.config.channels = 2
    rec.config.sample_rate = 48000
    fake.gates["construct"].set()
    assert fake.entered["read"].wait(2)
    rec.stop_recording()
    fake.read_release.set()
    spin_until(rec.is_operation_complete)
    assert fake.options["input_device_index"] == index
    assert (fake.options["channels"], fake.options["rate"]) == (1, 16000)


@pytest.mark.parametrize("invalidate", ["cancel", "shutdown", "restart"])
def test_already_queued_results_never_leak(recorder, invalidate):
    rec, fake, core = recorder
    ready, levels, chunks, errors = [], [], [], []
    rec.audio_ready.connect(ready.append)
    rec.level_changed.connect(levels.append)
    rec.audio_chunk.connect(chunks.append)
    rec.recording_error.connect(errors.append)
    assert rec.start_recording()
    assert fake.entered["read"].wait(2)
    rec.stop_recording()
    fake.read_release.set()
    assert fake.entered["terminate"].wait(2)
    # No Qt events consumed; wait for actual exit without delivering the queued signals.
    rec._thread.join(2)
    assert rec.is_operation_complete()
    if invalidate == "restart":
        assert rec.request_devices()
    elif invalidate == "cancel":
        rec.cancel_recording()
    else:
        rec.cleanup()
    core.processEvents()
    assert ready == levels == chunks == errors == []


def test_device_enumeration_delayed_error_and_shutdown(recorder):
    rec, fake, core = recorder
    fake.gates["devices"] = threading.Event()
    fake.errors["devices"] = OSError("enumeration unavailable")
    results, errors = [], []
    rec.devices_ready.connect(results.append)
    rec.devices_error.connect(errors.append)
    assert rec.request_devices()
    assert fake.entered["devices"].wait(2)
    assert not rec.start_recording()
    responsive(core)
    fake.gates["devices"].set()
    spin_until(lambda: bool(errors))
    assert "enumeration unavailable" in errors[0]
    fake.errors.clear()
    assert rec.request_devices()
    rec.cleanup()
    spin_until(rec.is_cleanup_complete)
    core.processEvents()
    assert results == []
    assert not rec.request_devices()


def test_old_queued_error_suppressed_by_retry_and_signals_on_qt_thread(recorder):
    rec, fake, core = recorder
    fake.errors["open"] = OSError("old privacy failure")
    errors, devices, threads = [], [], []
    rec.recording_error.connect(errors.append)
    rec.devices_ready.connect(lambda result: (devices.append(result),
                                             threads.append(threading.get_ident())))
    assert rec.start_recording()
    assert fake.entered["terminate"].wait(2)
    rec._thread.join(2)
    assert rec.is_operation_complete()
    fake.errors.clear()
    assert rec.request_devices()
    spin_until(lambda: bool(devices))
    core.processEvents()
    assert errors == []
    assert threads == [threading.get_ident()]


def test_independent_cleanup_attempts_after_multiple_teardown_errors(recorder):
    rec, fake, _ = recorder
    fake.gates["read"] = threading.Event()
    fake.errors.update(stop_stream=OSError("stop"), close=OSError("close"),
                       terminate=OSError("terminate"))
    errors = []
    rec.recording_error.connect(errors.append)
    assert rec.start_recording()
    assert fake.entered["read"].wait(2)
    rec.stop_recording()
    fake.read_release.set()
    fake.gates["read"].set()
    spin_until(lambda: bool(errors))
    assert rec.is_operation_complete()
    assert [name for name, _ in fake.calls][-3:] == ["stop_stream", "close", "terminate"]


@pytest.fixture
def shared_audio(audio_module, monkeypatch):
    """Observe worker lock attempts without timing-based absence assertions."""
    core = QCoreApplication.instance() or QCoreApplication([])
    attempts = Queue()
    real_lock = audio_module._PORTAUDIO_LIFECYCLE_LOCK

    class ObservedLock:
        def __enter__(self):
            assert threading.get_ident() != threading.main_thread().ident
            attempts.put(threading.get_ident())
            real_lock.acquire()

        def __exit__(self, *args):
            real_lock.release()

    monkeypatch.setattr(audio_module, "_PORTAUDIO_LIFECYCLE_LOCK", ObservedLock())
    fakes = [FakeAudio() for _ in range(3)]
    constructors = []
    records = [audio_module.AudioRecorder() for _ in fakes]

    def construct():
        fake = fakes[len(constructors)]
        constructors.append(fake)
        return fake.construct()

    monkeypatch.setattr(audio_module.pyaudio, "PyAudio", construct)
    yield records, fakes, constructors, attempts, core
    for rec in records:
        rec.cleanup()
    for fake in fakes:
        for gate in fake.gates.values():
            gate.set()
        fake.read_release.set()
    spin_until(lambda: all(rec.is_cleanup_complete() for rec in records))


@pytest.mark.parametrize("owner_mode,waiting_mode", [
    ("devices", "recording"), ("recording", "devices"), ("recording", "recording"),
])
@pytest.mark.parametrize("phase", ["construct", "terminate"])
def test_cross_instance_full_lifecycle_serialization(shared_audio, owner_mode, waiting_mode, phase):
    records, fakes, constructors, attempts, core = shared_audio
    owner, waiting, _ = records
    fakes[0].gates[phase] = threading.Event()
    fakes[0].gates["open"] = threading.Event()
    fakes[1].gates["open"] = threading.Event()
    def request(rec, mode):
        return rec.request_devices() if mode == "devices" else rec.start_recording()

    assert request(owner, owner_mode)
    attempts.get(timeout=2)
    if owner_mode == "recording" and phase == "terminate":
        assert fakes[0].entered["open"].wait(2)
        owner.stop_recording()
        fakes[0].gates["open"].set()
    assert fakes[0].entered[phase].wait(2)
    assert request(waiting, waiting_mode)
    attempts.get(timeout=2)  # Worker has reached lock acquisition, not merely been scheduled.
    assert len(constructors) == 1
    assert not waiting.is_operation_complete()
    responsive(core)
    if owner_mode == "recording" and phase == "construct":
        owner.stop_recording()
    fakes[0].gates[phase].set()
    assert fakes[1].entered["construct"].wait(2)
    assert fakes[0].entered["terminate"].is_set()
    if waiting_mode == "recording":
        assert fakes[1].entered["open"].wait(2)
        waiting.stop_recording()
        fakes[1].gates["open"].set()
    spin_until(lambda: owner.is_operation_complete() and waiting.is_operation_complete())
    assert len(constructors) == 2


@pytest.mark.parametrize("action", ["cancel", "shutdown", "stop"])
@pytest.mark.parametrize("mode", ["devices", "recording"])
def test_waiting_cancel_shutdown_or_release_skips_hardware_and_reopen(shared_audio, action, mode):
    records, fakes, constructors, attempts, core = shared_audio
    owner, old, reopened = records
    fakes[0].gates["terminate"] = threading.Event()
    assert owner.request_devices()
    attempts.get(timeout=2)
    assert fakes[0].entered["terminate"].wait(2)
    results, errors = [], []
    old.audio_ready.connect(results.append)
    old.devices_ready.connect(results.append)
    old.recording_error.connect(errors.append)
    old.devices_error.connect(errors.append)
    assert old.start_recording() if mode == "recording" else old.request_devices()
    attempts.get(timeout=2)
    # stop is recording-only; for device enumeration it behaves as dialog cancellation.
    {"cancel": old.cancel_recording, "shutdown": old.cleanup,
     "stop": old.stop_recording if mode == "recording" else old.cancel_recording}[action]()
    assert not old.is_operation_complete()
    assert not old.is_cleanup_complete()
    assert not old.start_recording()
    assert reopened.request_devices()  # Settings reopened before retired worker exits.
    attempts.get(timeout=2)
    responsive(core)
    assert len(constructors) == 1
    fakes[0].gates["terminate"].set()
    spin_until(lambda: all(rec.is_operation_complete() for rec in records))
    if action == "stop" and mode == "recording":
        spin_until(lambda: bool(results))
    core.processEvents()
    assert results == ([b""] if action == "stop" and mode == "recording" else [])
    assert errors == []
    assert len(constructors) == 2  # Old waiter never initialized PortAudio.
    assert old.is_cleanup_complete() == (action == "shutdown")


@pytest.mark.parametrize("phase", ["construct", "devices", "open", "read",
                                   "stop_stream", "close", "terminate"])
def test_cross_instance_exceptions_release_lifecycle_lock(shared_audio, phase):
    records, fakes, constructors, attempts, _ = shared_audio
    owner, waiting, _ = records
    fakes[0].gates[phase] = threading.Event()
    fakes[0].errors[phase] = OSError(f"mock {phase} failure")
    errors, devices = [], []
    owner.devices_error.connect(errors.append)
    owner.recording_error.connect(errors.append)
    waiting.devices_ready.connect(devices.append)
    if phase in ("construct", "devices", "terminate"):
        assert owner.request_devices()
    else:
        fakes[0].gates["read"] = threading.Event()
        fakes[0].read_release.set()
        assert owner.start_recording()
        if phase in ("stop_stream", "close"):
            assert fakes[0].entered["read"].wait(2)
            owner.stop_recording()
            fakes[0].gates["read"].set()
    attempts.get(timeout=2)
    assert fakes[0].entered[phase].wait(2)
    assert waiting.request_devices()
    attempts.get(timeout=2)
    assert len(constructors) == 1
    fakes[0].gates[phase].set()
    spin_until(lambda: bool(devices) and bool(errors))
    assert phase in errors[0]
    assert owner.is_operation_complete() and waiting.is_operation_complete()
    assert len(constructors) == 2
