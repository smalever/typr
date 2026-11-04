"""Sole sounddevice owner. Caller holds the recorder lifecycle lock in a worker.

The private finalizer is vetted against exactly 0.5.6. Never register native
cleanup at interpreter exit or modify sounddevice's initialization counter.
Source: https://python-sounddevice.readthedocs.io/en/0.5.6/_modules/sounddevice.html
No other code may import/reload/use sounddevice concurrently with this owner.
"""

import atexit
import importlib.util
import sys
from contextlib import contextmanager
from importlib.metadata import version
from threading import current_thread, main_thread

from typr.utils.logger import logger


class SoundDeviceOwner:
    def __init__(self):
        self._module = None
        self._broken = False

    @contextmanager
    def session(self):
        if current_thread() is main_thread():
            raise RuntimeError("sounddevice lifecycle requires an audio worker")
        if self._broken:
            raise RuntimeError("Audio backend cleanup failed; restart Typr")
        module = self._module
        first = module is None
        if first:
            if "sounddevice" in sys.modules:
                raise RuntimeError(
                    "Unmanaged sounddevice import: exclusive audio ownership required")
            if version("sounddevice") != "0.5.6":
                raise RuntimeError("Typr requires sounddevice 0.5.6")
            spec = importlib.util.find_spec("sounddevice")
            if spec is None or spec.loader is None:
                raise ImportError("sounddevice loader not found")
            module = importlib.util.module_from_spec(spec)
        loaded = not first
        try:
            if first:
                sys.modules["sounddevice"] = module
                try:
                    spec.loader.exec_module(module)
                    loaded = True
                    self._module = module
                finally:
                    # Registration precedes import-time initialization. Keep the
                    # module reference even when exec_module raises.
                    handler = getattr(module, "_exit_handler", None)
                    if handler is not None:
                        atexit.unregister(handler)
            else:
                module._initialize()
            if module.__version__ != "0.5.6":
                raise RuntimeError("Unsupported sounddevice module version")
            number, _ = module.get_portaudio_version()
            if not (0x130600 <= number < 0x140000):
                raise RuntimeError("Typr requires PortAudio >=19.6.0,<20")
            yield module
        finally:
            try:
                handler = getattr(module, "_exit_handler", None)
                if handler is not None:
                    # Also covers successful Pa_Initialize hidden by a Python
                    # stderr-restoration exception; zero credits is a no-op.
                    handler()
            except BaseException:
                self._broken = True
                logger.exception("Audio backend finalization failed; backend disabled")
                raise
            finally:
                if first and not loaded and sys.modules.get("sounddevice") is module:
                    del sys.modules["sounddevice"]


OWNER = SoundDeviceOwner()
