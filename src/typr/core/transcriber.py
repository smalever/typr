"""OpenAI Whisper API transcription."""

from typing import Optional

import httpx
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from typr.utils.logger import logger


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
        language: Optional[str],
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
            with httpx.Client(timeout=60.0) as client:
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
            try:
                error_detail = e.response.json()
                if "error" in error_detail:
                    error_msg = f"API error: {error_detail['error'].get('message', str(e))}"
            except Exception:
                pass
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
        api_base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.api_key = api_key
        self.api_base_url = api_base_url
        self.model = model
        self.language: Optional[str] = None
        self.prompt: str = ""
        self._worker: Optional[TranscriberWorker] = None

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
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
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
