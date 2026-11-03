"""Stable QObject hotkey boundary; device backends are imported lazily."""

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot

from typr.config import HotkeyConfig
from typr.platforms import hotkey_backend
from typr.platforms.shortcut import parse_shortcut


class HotkeyManager(QObject):
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    hotkey_error = pyqtSignal(str)

    def __init__(self, config: HotkeyConfig | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.config = config or HotkeyConfig()
        self._backend = None
        self._generation = 0
        self._active = False

    def initialize(self) -> bool:
        if self._backend is not None:
            registration = getattr(self._backend, "registration", None)
            result = self._backend.initialize()
            if registration != getattr(self._backend, "registration", None):
                self._stop()
            return result
        try:
            shortcut = parse_shortcut(self.config.push_to_talk)
            backend_type = hotkey_backend()
            # Backend config is private: Settings mutates the shared config before
            # update_shortcut, which must not corrupt an existing registration.
            self._backend = backend_type(HotkeyConfig(push_to_talk=shortcut.text))
            if hasattr(self._backend, "event"):
                self._backend.generation = self._generation
                relay = (self._relay_worker if hasattr(self._backend, "registration")
                         else self._relay)
                self._backend.event.connect(relay, Qt.ConnectionType.QueuedConnection)
                if hasattr(self._backend, "hotkey_error"):
                    self._backend.hotkey_error.connect(self.hotkey_error)
            else:
                self._backend.recording_started.connect(self._start)
                self._backend.recording_stopped.connect(self._stop)
                self._backend.hotkey_error.connect(self.hotkey_error)
            return self._backend.initialize()
        except (ValueError, RuntimeError, OSError) as exc:
            self.hotkey_error.emit(str(exc))
            return False

    @pyqtSlot(int, str, str)
    def _relay(self, generation: int, kind: str, message: str) -> None:
        if generation != self._generation:
            return
        if kind == "start":
            self._start()
        elif kind == "stop":
            self._stop()
        elif kind == "error":
            self._stop()
            self.hotkey_error.emit(message)

    @pyqtSlot(int, int, str, str)
    def _relay_worker(self, registration: int, generation: int, kind: str, message: str) -> None:
        if registration != self._backend.registration:
            return
        # Fatal and final cleanup diagnostics belong to a worker, not a shortcut.
        # A queued WM_UPDATE may never be consumed before GetMessageW fails.
        if kind == "error":
            self._stop()
            self.hotkey_error.emit(message)
        else:
            self._relay(generation, kind, message)

    @pyqtSlot()
    def _start(self) -> None:
        if not self._active:
            self._active = True
            self.recording_started.emit()

    @pyqtSlot()
    def _stop(self) -> None:
        if self._active:
            self._active = False
            self.recording_stopped.emit()

    def update_shortcut(self, shortcut: str) -> bool:
        try:
            parsed = parse_shortcut(shortcut)
        except ValueError as exc:
            self.hotkey_error.emit(str(exc))
            return False
        generation = self._generation + 1
        if self._backend is not None:
            if hasattr(self._backend, "event"):
                if not self._backend.update(parsed, generation):
                    return False
            elif not self._backend.update_shortcut(parsed.text):
                return False
        self._generation = generation
        self._stop()
        self.config.push_to_talk = parsed.text
        return True

    def is_registered(self) -> bool:
        return self._backend is not None and self._backend.is_registered()

    def cleanup(self) -> None:
        self._generation += 1
        self._stop()
        if self._backend is not None:
            self._backend.cleanup()
            if hasattr(self._backend, "event"):
                self._backend.generation = self._generation
