"""Execute a source-loader double, never import real sounddevice or native code."""

import importlib.util
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from types import ModuleType

import pytest

from typr.core import _sounddevice_backend as backend


@pytest.fixture
def source_boundary(monkeypatch):
    calls, registry = [], []
    state = {"credits": 0, "fail": None, "native": 0x130600, "version": "0.5.6"}

    class Loader:
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            assert threading.current_thread() is not threading.main_thread()
            calls.append("import")
            if "import_entered" in state:
                state["import_entered"].set()
                assert state["import_gate"].wait(3)
            assert sys.modules["sounddevice"] is module
            if state["fail"] == "before_handler":
                raise ImportError("early")

            def initialize():
                assert threading.current_thread() is not threading.main_thread()
                calls.append("init")
                if state["fail"] == "native_init":
                    raise OSError("native init")
                state["credits"] += 1
                if state["fail"] == "stderr":
                    raise OSError("stderr restore")

            def finalize():
                assert threading.current_thread() is not threading.main_thread()
                calls.append("finalize")
                if "final_entered" in state:
                    state["final_entered"].set()
                    assert state["final_gate"].wait(3)
                while state["credits"]:
                    calls.append("terminate")
                    if state["fail"] == "terminate":
                        raise OSError("terminate")
                    state["credits"] -= 1

            module._initialize = initialize
            module._exit_handler = finalize
            module.__version__ = state["version"]
            module.get_portaudio_version = lambda: (state["native"], "not parsed")
            module.query_devices = lambda: []
            registry.append(finalize)  # Exact upstream order: register BEFORE init.
            initialize()

    def unregister(handler):
        assert threading.current_thread() is not threading.main_thread()
        calls.append("unregister")
        registry[:] = [item for item in registry if item is not handler]

    monkeypatch.delitem(sys.modules, "sounddevice", raising=False)
    monkeypatch.setattr(backend, "version", lambda name: "0.5.6")
    monkeypatch.setattr(backend.importlib.util, "find_spec", lambda name:
                        importlib.util.spec_from_loader(name, Loader()))
    monkeypatch.setattr(backend.atexit, "unregister", unregister)
    owner = backend.SoundDeviceOwner()
    yield owner, calls, registry, state
    monkeypatch.delitem(sys.modules, "sounddevice", raising=False)


def operation(owner):
    with owner.session():
        return "ok"


def worker(owner):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(operation, owner).result()


def test_first_and_later_balanced_no_native_atexit(source_boundary):
    owner, calls, registry, state = source_boundary
    assert worker(owner) == worker(owner) == "ok"
    assert calls == ["import", "init", "unregister", "finalize", "terminate",
                     "init", "finalize", "terminate"]
    assert not registry and state["credits"] == 0


@pytest.mark.parametrize("phase,terminations", [
    ("before_handler", 0), ("native_init", 0), ("stderr", 1),
])
def test_failed_import_retains_handler_and_rolls_back(source_boundary, phase, terminations):
    owner, calls, registry, state = source_boundary
    state["fail"] = phase
    with pytest.raises((OSError, ImportError)):
        worker(owner)
    assert "sounddevice" not in sys.modules
    assert not registry and state["credits"] == 0
    assert calls.count("terminate") == terminations
    state["fail"] = None
    assert worker(owner) == "ok"


def test_later_hidden_success_is_balanced(source_boundary):
    owner, _, registry, state = source_boundary
    worker(owner)
    state["fail"] = "stderr"
    with pytest.raises(OSError, match="stderr"):
        worker(owner)
    assert state["credits"] == 0 and not registry


def test_finalizer_failure_poisons_all_future_sessions(source_boundary):
    owner, calls, registry, state = source_boundary
    state["fail"] = "terminate"
    with pytest.raises(OSError, match="terminate"):
        worker(owner)
    previous = list(calls)
    with pytest.raises(RuntimeError, match="restart"):
        worker(owner)
    assert calls == previous and not registry


@pytest.mark.parametrize("number", [0x130500, 0x140000])
def test_native_version_failure_still_finalizes(source_boundary, number):
    owner, _, registry, state = source_boundary
    state["native"] = number
    with pytest.raises(RuntimeError, match="PortAudio"):
        worker(owner)
    assert state["credits"] == 0 and not registry


def test_module_version_failure_still_finalizes(source_boundary):
    owner, _, registry, state = source_boundary
    state["version"] = "0.5.7"
    with pytest.raises(RuntimeError, match="module version"):
        worker(owner)
    assert state["credits"] == 0 and not registry


@pytest.mark.parametrize("number", [0x130600, 0x130700, 0x13FFFF])
def test_native_version_accepted_boundaries(source_boundary, number):
    owner, _, _, state = source_boundary
    state["native"] = number
    assert worker(owner) == "ok"


def test_later_native_init_failure_does_not_terminate_uninitialized_backend(source_boundary):
    owner, calls, registry, state = source_boundary
    worker(owner)
    state["fail"] = "native_init"
    before = calls.count("terminate")
    with pytest.raises(OSError, match="native init"):
        worker(owner)
    assert calls.count("terminate") == before
    assert state["credits"] == 0 and not registry
    state["fail"] = None
    assert worker(owner) == "ok"


def test_unmanaged_import_and_distribution_version_rejected(source_boundary, monkeypatch):
    owner, calls, _, _ = source_boundary
    monkeypatch.setitem(sys.modules, "sounddevice", ModuleType("sounddevice"))
    with pytest.raises(RuntimeError, match="Unmanaged"):
        worker(owner)
    monkeypatch.delitem(sys.modules, "sounddevice")
    monkeypatch.setattr(backend, "version", lambda name: "0.5.7")
    with pytest.raises(RuntimeError, match="requires sounddevice"):
        worker(owner)
    assert calls == []


def test_main_thread_rejected_before_import(source_boundary):
    owner, calls, _, _ = source_boundary
    with pytest.raises(RuntimeError, match="worker"):
        operation(owner)
    assert not calls


def test_failed_import_rollback_preserves_foreign_replacement(source_boundary, monkeypatch):
    owner, _, registry, state = source_boundary
    replacement = ModuleType("foreign")
    state["fail"] = "native_init"
    original = backend.atexit.unregister

    def unregister(handler):
        original(handler)
        sys.modules["sounddevice"] = replacement

    monkeypatch.setattr(backend.atexit, "unregister", unregister)
    with pytest.raises(OSError):
        worker(owner)
    assert sys.modules["sounddevice"] is replacement and not registry


def test_facade_import_does_not_find_or_load_sounddevice(source_boundary):
    _, calls, _, _ = source_boundary
    from typr.core.audio_recorder import AudioRecorder

    assert AudioRecorder.FORMAT == "int16"
    assert calls == [] and "sounddevice" not in sys.modules


def test_real_owner_first_import_and_finalizer_hold_cross_instance_lock(
        source_boundary, monkeypatch):
    from PyQt6.QtCore import QCoreApplication, QTimer

    from typr.core import audio_recorder as audio

    owner, calls, registry, state = source_boundary
    core = QCoreApplication.instance() or QCoreApplication([])
    for key in ("import_entered", "import_gate", "final_entered", "final_gate"):
        state[key] = threading.Event()
    attempts = Queue()
    lock = threading.Lock()

    class ObservedLock:
        def __enter__(self):
            assert threading.current_thread() is not threading.main_thread()
            attempts.put(True)
            lock.acquire()

        def __exit__(self, *args):
            lock.release()

    monkeypatch.setattr(audio, "OWNER", owner)
    monkeypatch.setattr(audio, "_PORTAUDIO_LIFECYCLE_LOCK", ObservedLock())
    first, waiting = audio.AudioRecorder(), audio.AudioRecorder()
    try:
        assert first.request_devices()
        attempts.get(timeout=2)
        assert state["import_entered"].wait(2)
        assert waiting.request_devices()
        attempts.get(timeout=2)
        waiting.cleanup()
        assert calls == ["import"]
        state["import_gate"].set()
        assert state["final_entered"].wait(2)
        assert not first.is_operation_complete()
        assert not waiting.is_cleanup_complete()
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        core.processEvents()
        assert ticks == [True]
    finally:
        first.cleanup()
        waiting.cleanup()
        state["import_gate"].set()
        state["final_gate"].set()
        first._thread.join(2)
        waiting._thread.join(2)
    assert first.is_cleanup_complete() and waiting.is_cleanup_complete()
    assert calls.count("import") == calls.count("init") == calls.count("terminate") == 1
    assert not registry
