"""No real hooks, windows, or session registrations are created here."""

import ctypes as C
import queue
import threading

import pytest
from PyQt6.QtCore import QCoreApplication

from typr.config import HotkeyConfig
from typr.core.hotkey_manager import HotkeyManager
from typr.platforms.shortcut import parse_shortcut
from typr.platforms.windows_hotkeys import (
    HOOKPROC,
    KBDLLHOOKSTRUCT,
    LPARAM,
    LRESULT,
    ULONG_PTR,
    WM_QUIT,
    WM_WTSSESSION_CHANGE,
    WPARAM,
    PressState,
    WindowsHotkeys,
)


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_pointer_sized_abi():
    assert C.sizeof(LPARAM) == C.sizeof(WPARAM) == C.sizeof(LRESULT) == C.sizeof(C.c_void_p)
    assert C.sizeof(ULONG_PTR) == C.sizeof(C.c_void_p)
    assert C.sizeof(KBDLLHOOKSTRUCT) == 24
    assert HOOKPROC._restype_ is LRESULT


@pytest.mark.parametrize("text", ["", "Ctrl", "Ctrl+Z, Alt+X", "Bogus", "Ctrl+?", "Num+Z",
                                  "Ctrl+Z, ", "Ctrl+Z,", ", Ctrl+Z", "Ctrl+Z, ,",
                                  "Ctrl+Z, , Alt+X", "Ctrl+,, "])
def test_strict_parser(text):
    with pytest.raises(ValueError):
        parse_shortcut(text)


def test_parser_codes():
    shortcut = parse_shortcut("Ctrl+Alt+Z")
    assert shortcut.windows_vk == 90
    assert shortcut.linux_code == 44
    assert shortcut.modifiers == {"ctrl", "alt"}


def test_physical_modifiers_system_messages_repeat_and_release():
    events = []
    state = PressState(90, {"ctrl", "alt"}, events.append)
    for key in (0xA2, 0xA3, 0xA4, 0xA0, 90, 90):
        state.handle(0x104, key, 0)
    assert events == ["start"]
    state.handle(0x105, 0xA2, 0)
    assert events == ["start"]  # right Ctrl remains down
    state.handle(0x105, 0xA3, 0)
    assert events == ["start", "stop"]
    state.handle(0x104, 0xA2, 0)
    state.handle(0x104, 90, 0)
    assert events == ["start", "stop"]  # target never released
    state.handle(0x105, 90, 0)
    state.handle(0x104, 90, 0)
    state.handle(0x105, 90, 0)
    assert events == ["start", "stop", "start", "stop"]


def test_altgr_and_all_injected_ignored():
    events = []
    state = PressState(90, {"ctrl", "alt"}, events.append)
    state.handle(0x100, 0xA2, 0x10)  # synthesized injected Ctrl for AltGr
    state.handle(0x104, 0xA5, 0)
    state.handle(0x100, 90, 0)
    assert events == []
    state.handle(0x101, 90, 0)
    state.handle(0x100, 0xA2, 0)  # a real Ctrl with right Alt is allowed
    state.handle(0x100, 90, 0)
    state.handle(0x101, 90, 0x12)  # injected/lower integrity up cannot stop physical PTT
    assert events == ["start"]
    state.reset()
    assert events == ["start", "stop"] and not state.pressed


class FakeWin32:
    def __init__(self, fail=None, gate=None):
        self.fail, self.gate = fail, gate
        self.messages = queue.Queue()
        self.calls = []
        self.callback = self.window_proc = None
        self.worker = None

    def error(self, operation):
        return OSError(operation)

    def PeekMessageW(self, *args):
        self.worker = threading.get_ident()
        if self.gate:
            self.gate.wait(2)
        return 0

    def GetCurrentThreadId(self):
        return 1

    def GetModuleHandleW(self, *args):
        return 1

    def RegisterClassW(self, wc):
        self.window_proc = wc._obj.lpfnWndProc
        return 1

    def CreateWindowExW(self, *args):
        return 2

    def WTSRegisterSessionNotification(self, *args):
        return self.fail != "session"

    def SetWindowsHookExW(self, _, callback, *args):
        self.callback = callback
        return 0 if self.fail == "hook" else 3

    def CallNextHookEx(self, *args):
        self.calls.append("next")
        return 987

    def PostThreadMessageW(self, tid, msg, wp, lp):
        self.messages.put((msg, wp, lp))
        return True

    def GetMessageW(self, message, *args):
        if self.fail == "message":
            return -1
        msg, wp, lp = self.messages.get(timeout=2)
        if callable(msg):
            msg()
            return self.GetMessageW(message, *args)
        message._obj.message, message._obj.wParam, message._obj.lParam = msg, wp, lp
        return 0 if msg == WM_QUIT else 1

    def DispatchMessageW(self, *args):
        return 0

    def DefWindowProcW(self, *args):
        return 0

    def UnhookWindowsHookEx(self, *args):
        self.calls.append("unhook")
        return self.fail != "unhook"

    def WTSUnRegisterSessionNotification(self, *args):
        self.calls.append("unregister-session")
        return True

    def DestroyWindow(self, *args):
        self.calls.append("destroy")
        return True

    def UnregisterClassW(self, *args):
        self.calls.append("unregister-class")
        return True

    def run(self, function):
        done = threading.Event()

        def call():
            function()
            done.set()

        self.messages.put((call, 0, 0))
        assert done.wait(1)

    def key(self, message, vk, flags=0, code=0):
        data = KBDLLHOOKSTRUCT(vkCode=vk, flags=flags)
        assert self.callback(code, message, C.addressof(data)) == 987


def finish(backend):
    backend.cleanup()
    backend._thread.join(1)  # Tests may join; production Qt cleanup never joins.
    assert not backend._thread.is_alive()


def test_mock_worker_update_session_reset_cleanup_restart(app):
    api = FakeWin32()
    backend = WindowsHotkeys(HotkeyConfig(), lambda: api)
    events = []
    backend.event.connect(lambda registration, *event: events.append(event))
    assert backend.initialize()
    assert backend.initialize()

    def press():
        for key in (0xA2, 0xA4, 90):
            api.key(0x100, key)
        api.key(0x100, 88, code=-1)
        api.window_proc(2, WM_WTSSESSION_CHANGE, 7, 0)

    api.run(press)
    app.processEvents()
    assert [e[1] for e in events] == ["start", "stop"]
    assert backend.update(parse_shortcut("Shift+F2"), 1)
    api.run(lambda: (api.key(0x100, 0xA1), api.key(0x100, 0x71)))
    app.processEvents()
    assert events[-1] == (1, "start", "")
    finish(backend)
    app.processEvents()
    assert events[-1] == (1, "stop", "")
    assert api.calls.count("unhook") == 1
    backend.cleanup()
    assert backend.initialize()
    finish(backend)
    assert api.calls.count("unhook") == 2


@pytest.mark.parametrize("failure", ["hook", "session", "message", "unhook"])
def test_known_failures(app, failure):
    api = FakeWin32(failure)
    backend = WindowsHotkeys(HotkeyConfig(), lambda: api)
    events = []
    backend.event.connect(lambda registration, *event: events.append(event))
    result = backend.initialize()
    if failure in ("hook", "session"):
        assert not result
    finish(backend)
    app.processEvents()
    assert any(e[1] == "error" for e in events)
    assert "destroy" in api.calls


def test_timeout_before_queue_creation_is_cancelled_and_retryable(app):
    gate = threading.Event()
    api = FakeWin32(gate=gate)
    backend = WindowsHotkeys(HotkeyConfig(), lambda: api)
    backend.STARTUP_TIMEOUT = 0.001
    assert not backend.initialize()
    assert not backend.initialize()
    gate.set()
    finish(backend)
    assert api.callback is None
    backend.STARTUP_TIMEOUT = 0.1
    assert backend.initialize()
    finish(backend)


def test_reset_control_and_update_post_failure_preserve_shortcut(app):
    api = FakeWin32()
    backend = WindowsHotkeys(HotkeyConfig(), lambda: api)
    events = []
    backend.event.connect(lambda registration, *event: events.append(event))
    assert backend.initialize()
    api.run(lambda: [api.key(0x100, key) for key in (0xA2, 0xA4, 90)])
    backend.reset()
    api.run(lambda: None)
    app.processEvents()
    assert [e[1] for e in events] == ["start", "stop"]
    original = backend.shortcut
    post = api.PostThreadMessageW
    api.PostThreadMessageW = lambda *args: False
    assert not backend.update(parse_shortcut("Shift+X"), 1)
    assert backend.shortcut is original and backend.generation == 0
    api.PostThreadMessageW = post
    finish(backend)


def facade(monkeypatch, api_factory):
    backend = WindowsHotkeys(HotkeyConfig(), api_factory)
    monkeypatch.setattr("typr.core.hotkey_manager.hotkey_backend", lambda: lambda _: backend)
    manager = HotkeyManager()
    events, errors = [], []
    manager.recording_started.connect(lambda: events.append("start"))
    manager.recording_stopped.connect(lambda: events.append("stop"))
    manager.hotkey_error.connect(errors.append)
    assert manager.initialize()
    return manager, backend, events, errors


def test_fatal_before_update_consumed_and_cleanup_errors_survive_generation(app, monkeypatch):
    api = FakeWin32()
    manager, backend, events, errors = facade(monkeypatch, lambda: api)
    entered, release = threading.Event(), threading.Event()

    def blocked_message():
        for key in (0xA2, 0xA4, 90):
            api.key(0x100, key)
        entered.set()
        assert release.wait(1)
        api.fail = "message"

    api.UnhookWindowsHookEx = lambda *_: False
    api.WTSUnRegisterSessionNotification = lambda *_: False
    api.DestroyWindow = lambda *_: False
    api.UnregisterClassW = lambda *_: False
    api.messages.put((blocked_message, 0, 0))
    assert entered.wait(1)
    try:
        assert manager.update_shortcut("Shift+F2")  # queued, never consumed
    finally:
        release.set()
    backend._thread.join(1)
    assert not backend._thread.is_alive()
    manager.cleanup()  # another generation must not hide final native failures
    app.processEvents()
    assert events == []  # stale start/stop still rejected
    assert any("GetMessageW" in error for error in errors)
    for text in ("UnhookWindowsHookEx", "Session notification cleanup", "DestroyWindow",
                 "UnregisterClassW"):
        assert any(text in error for error in errors)
    assert not manager.is_registered()


def test_restart_discards_old_events_and_idempotent_initialize_preserves_ptt(app, monkeypatch):
    old, fresh = FakeWin32(), FakeWin32()
    apis = iter((old, fresh))
    manager, backend, events, errors = facade(monkeypatch, lambda: next(apis))
    old_registration = backend.registration

    def press_then_fail():
        for key in (0xA2, 0xA4, 90):
            old.key(0x100, key)
        old.fail = "message"

    old.run(press_then_fail)
    backend._thread.join(1)
    assert not backend._thread.is_alive()
    # All old start/stop/error signals remain queued in Qt at this point.
    assert manager.initialize()
    assert backend.registration != old_registration
    app.processEvents()
    assert events == [] and errors == []
    fresh.run(lambda: [fresh.key(0x100, key) for key in (0xA2, 0xA4, 90)])
    registration = backend.registration
    assert manager.initialize()  # no identity invalidation for a live registration
    assert backend.registration == registration
    app.processEvents()
    assert events == ["start"]
    assert manager.initialize()
    assert events == ["start"]
    fresh.run(lambda: fresh.key(0x101, 90))
    app.processEvents()
    assert events == ["start", "stop"] and not errors
    finish(backend)


def test_comma_target_is_not_misread_as_empty_chord():
    # OEM punctuation is deliberately unsupported, rather than interpreted as
    # a separator. Supported non-letter key names continue to parse unchanged.
    with pytest.raises(ValueError, match="Unsupported hotkey key: ,"):
        parse_shortcut("Ctrl+,")
    for text in ("Ctrl+Space", "Alt+Return", "Shift+Tab", "Ctrl+Del", "Alt+Ins"):
        assert parse_shortcut(text).text == text
