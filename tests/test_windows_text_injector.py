import ctypes as C
import threading
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QThread

from typr.platforms.windows_injector import (
    INPUT,
    KEYUP,
    MODIFIERS,
    PASTE_KEYS,
    VK_CONTROL,
    VK_V,
    Win32Input,
    WindowsInjector,
)


@pytest.fixture
def core():
    return QCoreApplication.instance() or QCoreApplication([])


def test_abi_signatures_count_and_modifiers():
    if C.sizeof(C.c_void_p) == 8:
        assert C.sizeof(INPUT) == 40
        assert C.alignment(INPUT) == 8
        assert INPUT.payload.offset == 8
    user32 = Mock()
    user32.GetAsyncKeyState.return_value = 0
    user32.SendInput.return_value = 4
    api = Win32Input(user32)
    assert user32.SendInput.restype is C.c_uint32
    assert user32.SendInput.argtypes == [C.c_uint32, C.POINTER(INPUT), C.c_int]
    assert user32.GetAsyncKeyState.restype is C.c_int16
    assert not api.paste_keys_down()
    assert [call.args[0] for call in user32.GetAsyncKeyState.call_args_list] == list(PASTE_KEYS)
    assert api.send([INPUT()] * 4) == 4
    assert user32.SendInput.call_args.args[0::2] == (4, C.sizeof(INPUT))


@pytest.mark.parametrize("modifier", MODIFIERS)
def test_each_physical_or_generic_modifier(modifier):
    user32 = Mock()
    user32.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk == modifier else 0
    assert Win32Input(user32).paste_keys_down()


def test_wait_timeout_no_publication_or_forced_release(core):
    api, clipboard = Mock(), Mock()
    api.paste_keys_down.return_value = True
    clock = [0]
    backend = WindowsInjector(api, clipboard, clock=lambda: clock[0])
    results = []
    backend.result.connect(lambda *args: results.append(args))
    backend.request(1, "text", 0, 0)
    backend._tick()
    assert not results
    clock[0] = 2
    backend._tick()
    assert "Timed out" in results[0][1]
    clipboard.setText.assert_not_called()
    api.send.assert_not_called()
    backend.cleanup()


@pytest.mark.parametrize("sent,held", [(0, []), (1, [VK_CONTROL]),
                                         (2, [VK_V, VK_CONTROL]), (3, [VK_CONTROL]), (4, [])])
def test_send_count_partial_cleanup_and_clipboard_policy(core, sent, held):
    api, clipboard = Mock(), Mock()
    api.paste_keys_down.return_value = False
    api.send.side_effect = [sent, len(held)]
    clipboard.setText.side_effect = lambda text: (
        QThread.currentThread() == core.thread() or pytest.fail("wrong Qt thread"))
    backend = WindowsInjector(api, clipboard)
    results = []
    backend.result.connect(lambda *args: results.append(args))
    backend.request(7, "Unicode: тест", 0, 0)
    backend._tick()
    assert bool(results[0][1]) == (sent != 4)
    events = api.send.call_args_list[0].args[0]
    assert [(e.ki.wVk, e.ki.dwFlags) for e in events] == [
        (VK_CONTROL, 0), (VK_V, 0), (VK_V, KEYUP), (VK_CONTROL, KEYUP)]
    if held:
        assert [(e.ki.wVk, e.ki.dwFlags) for e in api.send.call_args.args[0]] == [
            (vk, KEYUP) for vk in held]
    else:
        assert api.send.call_count == 1
    backend.cleanup()
    assert clipboard.method_calls == [(("setText"), ("Unicode: тест",), {})]


def test_cleanup_failure_diagnosed_and_shutdown_no_send(core):
    api, clipboard = Mock(), Mock()
    api.paste_keys_down.return_value = False
    api.send.side_effect = [2, 0]
    backend = WindowsInjector(api, clipboard)
    errors = []
    backend.result.connect(lambda serial, error: errors.append(error))
    backend.request(1, "text", 0, 0)
    backend._tick()
    assert "cleanup failed" in errors[0]
    backend.request(2, "never publish", 0, 0)
    backend.cleanup()
    backend._tick()
    assert clipboard.setText.call_count == 1


def test_thread_guard_and_reentrant_shutdown(core):
    backend = WindowsInjector(Mock(), Mock())
    errors = []

    def foreign():
        try:
            backend.request(1, "text", 0, 0)
        except RuntimeError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=foreign)
    thread.start()
    thread.join(2)
    assert "main Qt thread" in errors[0]
    backend._api.paste_keys_down.return_value = False
    backend._clipboard.setText.side_effect = lambda text: backend.cleanup()
    backend.request(1, "text", 0, 0)
    backend._tick()
    backend._api.send.assert_not_called()


@pytest.mark.parametrize("release", [False, True])
def test_physical_v_wait_timeout_or_release_success(core, release):
    user32, clipboard = Mock(), Mock()
    held = [True]
    user32.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk == VK_V and held[0] else 0
    user32.SendInput.return_value = 4
    clock = [0]
    backend = WindowsInjector(Win32Input(user32), clipboard, clock=lambda: clock[0])
    results = []
    backend.result.connect(lambda *args: results.append(args))
    backend.request(1, "text", 0, 0)
    backend._tick()
    clipboard.setText.assert_not_called()
    user32.SendInput.assert_not_called()
    held[0] = not release
    clock[0] = 1 if release else 2
    backend._tick()
    assert bool(results[0][1]) != release
    if release:
        clipboard.setText.assert_called_once_with("text")
        user32.SendInput.assert_called_once()
    else:
        assert "modifier" not in results[0][1]
        clipboard.setText.assert_not_called()
        user32.SendInput.assert_not_called()
    backend.cleanup()
    assert backend.is_cleanup_complete()
