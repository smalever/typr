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
