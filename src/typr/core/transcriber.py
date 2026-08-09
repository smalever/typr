"""OpenAI Whisper API transcription."""

import httpx
from PyQt6.QtCore import QObject, QThread, pyqtSignal

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

    finished = pyqtSignal(str)
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

    def run(self) -> None:
        """Execute the API request."""
        try:
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
                self.finished.emit(text)

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

    def transcribe(self, audio_data: bytes) -> None:
        """Start transcription in background thread.

        Args:
            audio_data: WAV-formatted audio data.
        """
        if not audio_data:
            self.transcription_error.emit("No audio data to transcribe")
            return

        logger.info(f"Starting transcription, {len(audio_data)} bytes")
        self.transcription_started.emit()

        self._worker = TranscriberWorker(
            api_key=self.api_key,
            api_base_url=self.api_base_url,
            audio_data=audio_data,
            model=self.model,
            language=self.language,
            prompt=self.prompt,
        )
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, text: str) -> None:
        """Handle successful transcription."""
        self.transcription_complete.emit(text)
        self._cleanup_worker()

    def _on_error(self, error: str) -> None:
        """Handle transcription error."""
        self.transcription_error.emit(error)
        self._cleanup_worker()

    def _cleanup_worker(self) -> None:
        """Clean up worker thread."""
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

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
        return self._worker is not None and self._worker.isRunning()
