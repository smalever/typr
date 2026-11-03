"""Worker-owned WH_KEYBOARD_LL and native session reset notifications.

No device API is loaded until initialize. Native callbacks only update local
state / enqueue Qt events and always forward keyboard messages.
"""

import ctypes as C
import threading
from ctypes import wintypes as W

from PyQt6.QtCore import QObject, pyqtSignal

from typr.platforms.shortcut import parse_shortcut

LRESULT = C.c_ssize_t
WPARAM = C.c_size_t
LPARAM = C.c_ssize_t
HHOOK = C.c_void_p
ULONG_PTR = C.c_size_t
# WINFUNCTYPE is intentionally Windows-only; this module is lazily selected.
CALLBACK = getattr(C, "WINFUNCTYPE", C.CFUNCTYPE)
HOOKPROC = CALLBACK(LRESULT, C.c_int, WPARAM, LPARAM)
WNDPROC = CALLBACK(LRESULT, W.HWND, W.UINT, WPARAM, LPARAM)
WM_UPDATE = 0x8001
WM_RESET = 0x8002
WM_QUIT = 0x0012
WM_WTSSESSION_CHANGE = 0x02B1
DOWN = (0x100, 0x104)
UP = (0x101, 0x105)
GROUPS = {0xA0: "shift", 0xA1: "shift", 0xA2: "ctrl", 0xA3: "ctrl",
          0xA4: "alt", 0xA5: "alt", 0x5B: "meta", 0x5C: "meta"}
MODIFIERS = ("ctrl", "alt", "shift", "meta")


class KBDLLHOOKSTRUCT(C.Structure):
    _fields_ = [("vkCode", W.DWORD), ("scanCode", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class WNDCLASS(C.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", C.c_int),
                ("cbWndExtra", C.c_int), ("hInstance", W.HINSTANCE),
                ("hIcon", W.HICON), ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


class Win32:
    """Explicit ABI declarations, including pointer-sized callback and handles."""

    def __init__(self):
        user = C.WinDLL("user32", use_last_error=True)
        kernel = C.WinDLL("kernel32", use_last_error=True)
        wts = C.WinDLL("wtsapi32", use_last_error=True)
        signatures = {
            "SetWindowsHookExW": (user, HHOOK, [C.c_int, HOOKPROC, W.HINSTANCE, W.DWORD]),
            "CallNextHookEx": (user, LRESULT, [HHOOK, C.c_int, WPARAM, LPARAM]),
            "UnhookWindowsHookEx": (user, W.BOOL, [HHOOK]),
            "PeekMessageW": (user, W.BOOL, [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]),
            "GetMessageW": (user, C.c_int, [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]),
            "DispatchMessageW": (user, LRESULT, [C.POINTER(W.MSG)]),
            "PostThreadMessageW": (user, W.BOOL, [W.DWORD, W.UINT, WPARAM, LPARAM]),
            "DefWindowProcW": (user, LRESULT, [W.HWND, W.UINT, WPARAM, LPARAM]),
            "RegisterClassW": (user, W.ATOM, [C.POINTER(WNDCLASS)]),
            "UnregisterClassW": (user, W.BOOL, [W.LPCWSTR, W.HINSTANCE]),
            "CreateWindowExW": (user, W.HWND, [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]),
            "DestroyWindow": (user, W.BOOL, [W.HWND]),
            "GetCurrentThreadId": (kernel, W.DWORD, []),
            "GetModuleHandleW": (kernel, W.HMODULE, [W.LPCWSTR]),
            "WTSRegisterSessionNotification": (wts, W.BOOL, [W.HWND, W.DWORD]),
            "WTSUnRegisterSessionNotification": (wts, W.BOOL, [W.HWND]),
        }
        for name, (library, result, arguments) in signatures.items():
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)

    @staticmethod
    def error(operation):
        return OSError(C.get_last_error(), operation)


class PressState:
    """Physical state owned exclusively by the native worker thread."""

    def __init__(self, target, modifiers, publish):
        self.target, self.modifiers, self.publish = target, modifiers, publish
        self.pressed = set()
        self.active = False

    def reset(self):
        self.pressed.clear()
        if self.active:
            self.active = False
            self.publish("stop")

    def handle(self, message, key, flags):
        if flags & 0x10 or message not in DOWN + UP:  # ALL injected, including AltGr synthesis
            return
        if message in DOWN:
            if key in self.pressed:
                return
            self.pressed.add(key)
            held = {GROUPS[k] for k in self.pressed if k in GROUPS}
            if key == self.target and self.modifiers <= held:
                self.active = True
                self.publish("start")
        else:
            self.pressed.discard(key)
            held = {GROUPS[k] for k in self.pressed if k in GROUPS}
            if self.active and (key == self.target or not self.modifiers <= held):
                self.active = False
                self.publish("stop")


class WindowsHotkeys(QObject):
    event = pyqtSignal(int, int, str, str)
    STARTUP_TIMEOUT = 0.1

    def __init__(self, config, api_factory=Win32):
        super().__init__()
        self.shortcut = parse_shortcut(config.push_to_talk)
        self.generation = 0
        self.registration = 0
        self._api_factory = api_factory
        self._thread = None
        self._tid = 0
        self._api = None
        self._registered = False
        self._cancel = threading.Event()
        self._ready = threading.Event()
        self._startup_error = ""
        self._callbacks = None

    def initialize(self):
        if self._thread and self._thread.is_alive():
            if self.is_registered():
                return True
            self.event.emit(self.registration, self.generation, "error",
                            "Hotkey worker is still starting/stopping")
            return False
        self._cancel.clear()
        self._ready.clear()
        self._startup_error = ""
        self.registration += 1
        self._thread = threading.Thread(target=self._run, name="typr-hotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(self.STARTUP_TIMEOUT):
            self.cleanup()
            self.event.emit(self.registration, self.generation, "error",
                            "Hotkey worker startup timed out")
            return False
        if self._startup_error:
            self.event.emit(self.registration, self.generation, "error", self._startup_error)
            return False
        return self.is_registered()

    def is_registered(self):
        return self._registered and not self._cancel.is_set()

    def update(self, shortcut, generation):
        if self._thread and self._thread.is_alive():
            if not self.is_registered():
                self.event.emit(self.registration, self.generation, "error",
                                "Hotkey worker is stopping")
                return False
            mask = sum(1 << i for i, group in enumerate(MODIFIERS) if group in shortcut.modifiers)
            if not self._api.PostThreadMessageW(
                    self._tid, WM_UPDATE, shortcut.windows_vk, (generation << 4) | mask):
                self.event.emit(self.registration, self.generation, "error",
                                "Cannot queue hotkey update")
                return False
        self.shortcut, self.generation = shortcut, generation
        return True

    def reset(self):
        if self._tid and not self._api.PostThreadMessageW(self._tid, WM_RESET, 0, 0):
            self.event.emit(self.registration, self.generation, "error",
                            "Cannot queue hotkey reset")
            self.cleanup()

    def cleanup(self):
        self._cancel.set()
        if self._tid and self._thread and self._thread.is_alive():
            if not self._api.PostThreadMessageW(self._tid, WM_QUIT, 0, 0):
                self.event.emit(self.registration, self.generation, "error",
                                "Cannot queue hotkey shutdown")

    def _run(self):
        api = None
        hook = window = atom = None
        session_registered = False
        generation = self.generation
        registration = self.registration
        state = PressState(self.shortcut.windows_vk, self.shortcut.modifiers,
                           lambda kind: self.event.emit(registration, generation, kind, ""))
        message = W.MSG()
        name = f"TyprHotkeys-{id(self)}"
        instance = None

        @HOOKPROC
        def callback(code, wparam, lparam):
            try:
                if code >= 0 and not self._cancel.is_set():
                    data = C.cast(lparam, C.POINTER(KBDLLHOOKSTRUCT)).contents
                    state.handle(wparam, data.vkCode, data.flags)
            except Exception as exc:  # ctypes callback boundary; forwarding is mandatory
                state.reset()
                self.event.emit(registration, generation, "error",
                                f"Keyboard callback failed: {exc}")
            return api.CallNextHookEx(hook, code, wparam, lparam)

        @WNDPROC
        def window_proc(hwnd, msg, wp, lp):
            if msg == WM_WTSSESSION_CHANGE:
                state.reset()  # lock/unlock/logon/disconnect: no stale physical state
            return api.DefWindowProcW(hwnd, msg, wp, lp)

        # If unhook fails Windows removes the hook on installing-thread exit.
        # Retain callbacks on the backend even beyond _run's finally, not merely
        # as locals destroyed just before the native thread actually terminates.
        self._callbacks = (callback, window_proc)
        try:
            api = self._api = self._api_factory()
            api.PeekMessageW(C.byref(message), None, 0, 0, 0)  # create queue BEFORE publishing tid
            self._tid = api.GetCurrentThreadId()
            if self._cancel.is_set():
                return
            instance = api.GetModuleHandleW(None)
            wc = WNDCLASS(lpfnWndProc=window_proc, hInstance=instance, lpszClassName=name)
            atom = api.RegisterClassW(C.byref(wc))
            if not atom:
                raise api.error("RegisterClassW")
            window = api.CreateWindowExW(0, name, name, 0, 0, 0, 0, 0,
                                         None, None, instance, None)
            if not window:
                raise api.error("CreateWindowExW")
            if not api.WTSRegisterSessionNotification(window, 0):
                raise api.error("WTSRegisterSessionNotification")
            session_registered = True
            hook = api.SetWindowsHookExW(13, callback, instance, 0)
            if not hook:
                raise api.error("SetWindowsHookExW")
            self._registered = True
            self._ready.set()
            while not self._cancel.is_set():
                result = api.GetMessageW(C.byref(message), None, 0, 0)
                if result == -1:
                    raise api.error("GetMessageW")
                if result == 0:
                    break
                if message.message == WM_UPDATE:
                    state.reset()
                    generation = message.lParam >> 4
                    state.target = message.wParam
                    state.modifiers = frozenset(group for i, group in enumerate(MODIFIERS)
                                               if message.lParam & (1 << i))
                elif message.message == WM_RESET:
                    state.reset()
                else:
                    api.DispatchMessageW(C.byref(message))
        except Exception as exc:  # native worker boundary; never leak through ctypes/Qt
            self._startup_error = f"Windows hotkey worker failed: {exc}"
            self.event.emit(registration, generation, "error", self._startup_error)
        finally:
            self._registered = False
            state.reset()
            # Keep both callback closures alive until unhook AND thread exit.
            if hook and not api.UnhookWindowsHookEx(hook):
                self.event.emit(registration, generation, "error", "UnhookWindowsHookEx failed")
            if window:
                if session_registered and not api.WTSUnRegisterSessionNotification(window):
                    self.event.emit(registration, generation, "error",
                                    "Session notification cleanup failed")
                if not api.DestroyWindow(window):
                    self.event.emit(registration, generation, "error", "DestroyWindow failed")
            if atom and not api.UnregisterClassW(name, instance):
                self.event.emit(registration, generation, "error", "UnregisterClassW failed")
            self._tid = 0
            self._ready.set()
