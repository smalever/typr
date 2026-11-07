"""Offline build smoke check; never start Qt, audio devices or a network client."""

import importlib
import importlib.abc
import importlib.metadata
import importlib.util
import os
import socket
import sys
import tempfile
from pathlib import Path


def deny_network(*args, **kwargs):
    raise RuntimeError("Network access forbidden during offline import validation")


socket.socket.connect = deny_network
socket.create_connection = deny_network
class DenyAudio(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "sounddevice":
            raise RuntimeError("Native audio initialization forbidden during build")
        return None


audio = importlib.util.find_spec("sounddevice")
if audio is None or not Path(audio.origin).is_file():
    raise RuntimeError("sounddevice package missing")
if importlib.metadata.version("sounddevice") != "0.5.6":
    raise RuntimeError("Unexpected sounddevice version")
if not list(Path(audio.origin).parent.glob("_sounddevice_data/portaudio-binaries/*.dll")):
    raise RuntimeError("Bundled PortAudio DLL missing")
sys.meta_path.insert(0, DenyAudio())
with tempfile.TemporaryDirectory(prefix="typr-offline-import-") as profile:
    for variable in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA"):
        os.environ[variable] = profile
    for module in (
        "typr", "typr.app", "typr.__main__", "PyQt6.QtCore", "PyQt6.QtWidgets",
        "httpx", "websockets", "cffi",
    ):
        importlib.import_module(module)
    # Windows file logging must close before deleting the isolated profile.
    import logging

    logging.shutdown()
