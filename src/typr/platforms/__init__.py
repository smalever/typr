"""Platform boundaries; importing this package does not load device backends."""

import sys


def hotkey_backend():
    """Load only the current platform's input implementation."""
    if sys.platform == "win32":
        from .windows_hotkeys import WindowsHotkeys

        return WindowsHotkeys
    if sys.platform == "linux":
        from .linux_hotkeys import LinuxHotkeys

        return LinuxHotkeys
    raise RuntimeError(f"Global hotkeys are unsupported on {sys.platform}")


def injection_backend():
    """Import no evdev or Linux clipboard implementation on Windows."""
    if sys.platform == "win32":
        from .windows_injector import WindowsInjector

        return WindowsInjector
    if sys.platform == "linux":
        from .linux_injector import LinuxInjector

        return LinuxInjector
    raise RuntimeError(f"Text injection is unsupported on {sys.platform}")
