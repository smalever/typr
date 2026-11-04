"""OpenAI Whisper API transcription."""

import sys

import httpx
from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot

from typr.utils.logger import logger


def _is_local_gigastt(api_base_url: str, model: str) -> bool:
    """Return whether settings target the installer-managed GigaSTT server."""
    return model == "gigaam-v3-rnnt" or api_base_url.rstrip("/") == (
        "http://127.0.0.1:9876/v1"
    )


def _request_timeout(api_base_url: str, model: str) -> httpx.Timeout:
    """Use a longer inference window for the local CPU GigaSTT backend."""
    read_timeout = 120.0 if _is_local_gigastt(api_base_url, model) else 30.0
    return httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=10.0)


def _api_error_message(response: httpx.Response, fallback: str) -> str:
    """Extract OpenAI or GigaSTT error text without assuming its JSON shape."""
    try:
        detail = response.json()
    except ValueError:
        return fallback

    if not isinstance(detail, dict):
        return fallback
    error = detail.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    if isinstance(error, str) and error:
        code = detail.get("code")
        return f"{error} ({code})" if isinstance(code, str) and code else error
    return fallback


class TranscriberWorker(QThread):
    """Worker thread for async API calls."""

    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        api_base_url: str,
        audio_data: bytes,
        model: str,
        language: str | None,
        prompt: str,
    ):
        super().__init__()
        self.api_key = api_key
        self.api_base_url = api_base_url.rstrip("/")
        self.audio_data = audio_data
        self.model = model
        self.language = language
        self.prompt = prompt
        self._native_thread = None
        self._native_error: str | None = None
        self._native_diagnostic: str | None = None

    def run(self) -> None:
        """Execute the API request."""
        try:
            if sys.platform == "win32":
                from typr.platforms.windows_thread import ThreadHandle

                try:
                    self._native_thread = ThreadHandle()
                except OSError as exc:
                    self._native_error = str(exc)
                    raise
            with httpx.Client(timeout=_request_timeout(self.api_base_url, self.model)) as client:
                files = {"file": ("audio.wav", self.audio_data, "audio/wav")}
                data = {"model": self.model}

                if self.language:
                    data["language"] = self.language
                if self.prompt:
                    data["prompt"] = self.prompt

                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                response = client.post(
                    f"{self.api_base_url}/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                result = response.json()
                text = result.get("text", "")
                logger.info(f"Transcription complete: {len(text)} chars")
                self.result.emit(text)

        except httpx.HTTPStatusError as e:
            error_msg = f"API error: {e.response.status_code}"
            detail = _api_error_message(e.response, str(e))
            if detail != str(e):
                error_msg = f"API error: {detail}"
            logger.error(error_msg)
            self.error.emit(error_msg)

        except httpx.TimeoutException:
            error_msg = "Request timed out"
            logger.error(error_msg)
            self.error.emit(error_msg)

        except Exception as e:
            error_msg = f"Transcription failed: {e}"
            logger.error(error_msg)
            self.error.emit(error_msg)

    def is_native_exit_complete(self) -> bool:
        """Nonblocking native proof; retain ownership on unverified exit."""
        if not self.wait(0):
            return False
        if sys.platform != "win32":
            return True
        try:
            if self._native_error is not None:
                raise OSError(self._native_error)
            if self._native_thread is None:
                raise OSError("Native thread handle missing")
            if not self._native_thread.is_exited():
                return False
        except OSError as exc:
            diagnostic = str(exc)
            if diagnostic != self._native_diagnostic:
                logger.error(f"Shutdown blocked: native thread exit unverified: {diagnostic}")
                self._native_diagnostic = diagnostic
            return False
        try:
            self._native_thread.close()
        except OSError as exc:
            # Exit is proven; a leaked handle must not be misreported as a live thread.
            logger.error(f"Native thread exited but handle cleanup failed: {exc}")
        return True

class WhisperTranscriber(QObject):
    """Transcribes audio using OpenAI Whisper API."""

    # Signals
    transcription_complete = pyqtSignal(str)
    transcription_error = pyqtSignal(str)
    transcription_started = pyqtSignal()

    def __init__(
        self,
        api_key: str,
        api_base_url: str = "http://127.0.0.1:5092/v1",
        model: str = "parakeet-tdt-0.6b-v3",
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.api_key = api_key
        self.api_base_url = api_base_url
        self.model = model
        self.language: str | None = None
        self.prompt: str = ""
        self._worker: TranscriberWorker | None = None
        self._closing = False
        self._outcome: tuple[bool, str] | None = None

    def transcribe(self, audio_data: bytes) -> None:
        """Start transcription in background thread.

        Args:
            audio_data: WAV-formatted audio data.
        """
        if self._closing or self._worker is not None:
            return
        if not audio_data:
            self.transcription_error.emit("No audio data to transcribe")
            return

        logger.info(f"Starting transcription, {len(audio_data)} bytes")
        self._worker = TranscriberWorker(
            api_key=self.api_key,
            api_base_url=self.api_base_url,
            audio_data=audio_data,
            model=self.model,
            language=self.language,
            prompt=self.prompt,
        )
        self._outcome = None
        self._worker.result.connect(self._on_result, Qt.ConnectionType.QueuedConnection)
        self._worker.error.connect(self._on_error, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(self._on_worker_exited, Qt.ConnectionType.QueuedConnection)
        self._worker.start()
        self.transcription_started.emit()

    @pyqtSlot(str)
    def _on_result(self, text: str) -> None:
        """Stage the result; the HTTP context and thread may still be alive."""
        if not self._closing and self.sender() is self._worker:
            self._outcome = (True, text)

    @pyqtSlot(str)
    def _on_error(self, error: str) -> None:
        if not self._closing and self.sender() is self._worker:
            self._outcome = (False, error)

    @pyqtSlot()
    def _on_worker_exited(self) -> None:
        if self.sender() is self._worker:
            self._reap_worker()

    def _reap_worker(self) -> None:
        """Release ownership only after actual exit, before reentrant callbacks."""
        worker = self._worker
        if worker is None:
            return
        if not worker.is_native_exit_complete():
            QTimer.singleShot(10, self._reap_worker)
            return
        outcome = self._outcome
        self._outcome = None
        self._worker = None
        worker.deleteLater()
        if not self._closing and outcome is not None:
            success, message = outcome
            if success:
                self.transcription_complete.emit(message)
            else:
                self.transcription_error.emit(message)

    def cleanup(self) -> None:
        """Terminal, nonblocking cancellation of delivery, not of synchronous HTTP."""
        self._closing = True
        self._outcome = None

    def is_cleanup_complete(self) -> bool:
        """Qt must keep running until the worker's native exit has been relayed."""
        return self._closing and self._worker is None

    def update_settings(
        self,
        api_key: str | None = None,
        api_base_url: str | None = None,
        model: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
    ) -> None:
        """Update transcriber settings."""
        if api_key is not None:
            self.api_key = api_key
        if api_base_url is not None:
            self.api_base_url = api_base_url
        if model is not None:
            self.model = model
        if language is not None:
            self.language = language
        if prompt is not None:
            self.prompt = prompt

    def is_busy(self) -> bool:
        """Check if transcription is in progress."""
        return self._worker is not None
