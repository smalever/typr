"""Windows clipboard publication and Ctrl+V, exclusively on main Qt thread."""

import ctypes as C
import time

from PyQt6.QtCore import QCoreApplication, QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication

from typr.utils.logger import logger

WORD = C.c_uint16
DWORD = C.c_uint32
LONG = C.c_int32
ULONG_PTR = C.c_size_t


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class INPUTUNION(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ("payload",)
    _fields_ = [("type", DWORD), ("payload", INPUTUNION)]


VK_CONTROL = 0x11
VK_V = 0x56
KEYUP = 0x0002
MODIFIERS = (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C)
PASTE_KEYS = (*MODIFIERS, VK_V)


def key(vk, up=False):
    return INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=KEYUP if up else 0))


class Win32Input:
    def __init__(self, user32=None):
        self.user32 = user32 if user32 is not None else C.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [C.c_uint32, C.POINTER(INPUT), C.c_int]
        self.user32.SendInput.restype = C.c_uint32
        self.user32.GetAsyncKeyState.argtypes = [C.c_int]
        self.user32.GetAsyncKeyState.restype = C.c_int16

    def paste_keys_down(self):
        return any(self.user32.GetAsyncKeyState(vk) & 0x8000 for vk in PASTE_KEYS)

    def send(self, events):
        array = (INPUT * len(events))(*events)
        return self.user32.SendInput(len(array), array, C.sizeof(INPUT))


class WindowsInjector(QObject):
    result = pyqtSignal(int, str)

    def __init__(self, api=None, clipboard=None, clock=time.monotonic, timeout_ms=2000):
        super().__init__()
        self._api = api if api is not None else Win32Input()
        self._clipboard = clipboard
        self._clock = clock
        self._timeout = timeout_ms / 1000
        self._active = None
        self._closed = False
        self._timer = QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._tick)

    def _assert_thread(self):
        app = QCoreApplication.instance()
        if app is None or QThread.currentThread() != app.thread():
            raise RuntimeError("Clipboard injection requires the main Qt thread")

    def is_available(self):
        return not self._closed

    def request(self, serial, text, typing_delay, restore_delay):
        self._assert_thread()
        if self._closed:
            return
        self._active = (serial, text, self._clock() + self._timeout)
        self._timer.start()

    def _finish(self, error=""):
        serial = self._active[0]
        self._active = None
        self._timer.stop()
        if error:
            logger.error(f"Windows injection failed: {error}")
        self.result.emit(serial, error)

    def _tick(self):
        self._assert_thread()
        if self._closed or self._active is None:
            return
        _, text, deadline = self._active
        try:
            if self._clock() >= deadline:
                self._finish("Timed out waiting for paste keys to be released; clipboard unchanged")
                return
            if self._api.paste_keys_down():
                return
            if not text:
                self._finish()
                return
            clipboard = self._clipboard
            if clipboard is None:
                clipboard = QGuiApplication.clipboard()
            if clipboard is None:
                raise RuntimeError("Qt clipboard unavailable")
            clipboard.setText(text)
            if self._closed or self._active is None:
                return
            events = [key(VK_CONTROL), key(VK_V), key(VK_V, True), key(VK_CONTROL, True)]
            sent = self._api.send(events)
            if sent != len(events):
                held = []
                for event in events[:max(0, min(sent, len(events)))]:
                    vk = event.ki.wVk
                    if event.ki.dwFlags & KEYUP:
                        if vk in held:
                            held.remove(vk)
                    else:
                        held.append(vk)
                cleanup = [key(vk, True) for vk in reversed(held)]
                detail = ""
                if cleanup:
                    try:
                        if self._api.send(cleanup) != len(cleanup):
                            detail = "; synthetic key cleanup failed"
                    except Exception as exc:
                        detail = f"; synthetic key cleanup failed: {exc}"
                self._finish(f"SendInput sent {sent}/4 events (UIPI/UAC not bypassed){detail}")
                return
            self._finish()
        except Exception as exc:  # Qt runtime boundary; never restore clipboard.
            if self._active is not None:
                self._finish(str(exc))

    def cleanup(self):
        self._assert_thread()
        self._closed = True
        self._active = None
        self._timer.stop()

    def is_cleanup_complete(self):
        return self._closed
