"""Owned Win32 thread handle: Qt finished/wait can precede FLS teardown."""

import ctypes as C
from ctypes import wintypes as W


class ThreadHandle:
    """Acquire in the worker; probe/close only after Qt finished in its owner."""

    def __init__(self, kernel=None):
        self._kernel = kernel if kernel is not None else C.WinDLL(
            "kernel32", use_last_error=True)
        for name, args, result in (
            ("GetCurrentThreadId", [], W.DWORD),
            ("OpenThread", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD),
            ("CloseHandle", [W.HANDLE], W.BOOL),
        ):
            function = getattr(self._kernel, name)
            function.argtypes, function.restype = args, result
        self._handle = self._kernel.OpenThread(
            0x00100000, False, self._kernel.GetCurrentThreadId())  # SYNCHRONIZE only
        if not self._handle:
            raise OSError(C.get_last_error(), "OpenThread failed; native exit unverified")

    def is_exited(self) -> bool:
        if self._handle is None:
            raise RuntimeError("Thread handle already closed")
        status = self._kernel.WaitForSingleObject(self._handle, 0)
        if status == 0:  # WAIT_OBJECT_0: OS thread, including FLS callbacks, exited
            return True
        if status == 258:  # WAIT_TIMEOUT
            return False
        raise OSError(C.get_last_error(), f"WaitForSingleObject failed: {status:#x}")

    def close(self) -> None:
        if self._handle is None:
            return
        if not self.is_exited():
            raise RuntimeError("Cannot close thread handle before native exit")
        if not self._kernel.CloseHandle(self._handle):
            raise OSError(C.get_last_error(), "CloseHandle failed")
        self._handle = None
