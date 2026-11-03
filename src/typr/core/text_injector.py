"""Asynchronous, platform-neutral text injection boundary."""

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot

from typr.platforms import injection_backend
from typr.utils.logger import logger


class TextInjector(QObject):
    """One active request; unique caller-owned tokens are compared by identity.

    Acceptance is not success. Rejections emit failure asynchronously. Cleanup
    is terminal and suppresses callbacks. Public methods run on main Qt thread.
    """

    injection_completed = pyqtSignal(object)
    injection_failed = pyqtSignal(object, str)

    def __init__(self, typing_delay=0, restore_delay=3000, parent=None):
        super().__init__(parent)
        self.typing_delay = typing_delay
        self.restore_delay = restore_delay
        self._backend = None
        self._closed = False
        self._serial = 0
        self._active = None

    def _get_backend(self):
        if self._backend is None:
            self._backend = injection_backend()()
            self._backend.result.connect(self._result, Qt.ConnectionType.QueuedConnection)
        return self._backend

    def is_available(self):
        if self._closed:
            return False
        try:
            return self._get_backend().is_available()
        except (OSError, RuntimeError, ImportError) as exc:
            logger.error(f"Text injection unavailable: {exc}")
            return False

    def request_injection(self, text: str, token: object) -> bool:
        if self._closed:
            return False
        if self._active is not None:
            QTimer.singleShot(0, lambda: self._reject(token, "Text injector is busy"))
            return False
        self._serial += 1
        serial = self._serial
        self._active = (serial, token)
        delays = (self.typing_delay, self.restore_delay)
        QTimer.singleShot(0, lambda: self._start(serial, text, delays))
        return True

    def _reject(self, token, reason):
        if not self._closed:
            self.injection_failed.emit(token, reason)

    def _start(self, serial, text, delays):
        if self._closed or self._active is None or self._active[0] != serial:
            return
        try:
            self._get_backend().request(serial, text, *delays)
        except Exception as exc:  # Qt runtime boundary
            logger.error(f"Text injection startup failed: {exc}")
            self._result(serial, str(exc))

    @pyqtSlot(int, str)
    def _result(self, serial, error):
        if self._closed or self._active is None or serial != self._active[0]:
            return
        _, token = self._active
        self._active = None
        if error:
            self.injection_failed.emit(token, error)
        else:
            self.injection_completed.emit(token)

    def set_typing_delay(self, delay):
        self.typing_delay = delay

    def set_restore_delay(self, delay):
        self.restore_delay = delay

    def cleanup(self):
        if self._closed:
            return
        self._closed = True
        self._active = None
        if self._backend is not None:
            self._backend.cleanup()

    def is_cleanup_complete(self) -> bool:
        """Terminal barrier: poll on Qt thread; never waits or joins a worker."""
        return self._closed and (
            self._backend is None or self._backend.is_cleanup_complete())
