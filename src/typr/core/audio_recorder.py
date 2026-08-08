"""Audio recording using PyAudio with PipeWire backend."""

import io
import wave
from threading import Event, Thread

import pyaudio
from PyQt6.QtCore import QObject, pyqtSignal

from typr.config import AudioConfig
from typr.utils.logger import logger


class AudioRecorder(QObject):
    """Records audio from microphone using PyAudio."""

    # Signals
    audio_ready = pyqtSignal(bytes)  # Complete WAV data
    audio_chunk = pyqtSignal(bytes)  # For live streaming mode
    recording_error = pyqtSignal(str)  # Error message
    level_changed = pyqtSignal(float)  # Audio level 0.0-1.0

    # Audio format constants
    FORMAT = pyaudio.paInt16
    CHUNK_SIZE = 1024

    def __init__(self, config: AudioConfig | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.config = config or AudioConfig()
        self._audio: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._frames: list[bytes] = []
        self._recording = Event()
        self._thread: Thread | None = None

    def _ensure_audio(self) -> pyaudio.PyAudio:
        """Ensure PyAudio is initialized."""
        if self._audio is None:
            self._audio = pyaudio.PyAudio()
        return self._audio

    def start_recording(self) -> bool:
        """Start recording audio in a background thread.

        Returns:
            True if recording started successfully, False otherwise.
        """
        if self._recording.is_set():
            logger.warning("Recording already in progress")
            return False

        self._frames = []
        self._recording.set()

        try:
            audio = self._ensure_audio()
            device_index = self._get_device_index()

            self._stream = audio.open(
                format=self.FORMAT,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                frames_per_buffer=self.CHUNK_SIZE,
                input_device_index=device_index,
            )

            self._thread = Thread(target=self._record_loop, daemon=True)
            self._thread.start()
            logger.info("Recording started")
            return True

        except Exception as e:
            error_msg = f"Failed to start recording: {e}"
            logger.error(error_msg)
            self._recording.clear()
            self.recording_error.emit(error_msg)
            return False

    def _record_loop(self) -> None:
        """Background thread that collects audio chunks."""
        while self._recording.is_set() and self._stream:
            try:
                data = self._stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                self._frames.append(data)
                self.audio_chunk.emit(data)

                # Calculate audio level
                level = self._calculate_level(data)
                self.level_changed.emit(level)

            except Exception as e:
                if self._recording.is_set():  # Only report if not stopping
                    error_msg = f"Recording error: {e}"
                    logger.error(error_msg)
                    self.recording_error.emit(error_msg)
                break

    def _calculate_level(self, data: bytes) -> float:
        """Calculate normalized audio level from raw PCM data."""
        if not data:
            return 0.0

        # Convert bytes to 16-bit samples
        import struct

        samples = struct.unpack(f"<{len(data) // 2}h", data)
        if not samples:
            return 0.0

        # Calculate RMS
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        # Normalize to 0.0-1.0 range (16-bit max is 32767)
        return min(1.0, rms / 32767.0 * 3)  # *3 for better visual range

    def stop_recording(self) -> bytes:
        """Stop recording and return WAV data.

        Returns:
            WAV-formatted audio data as bytes.
        """
        self._recording.clear()

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.warning(f"Error closing stream: {e}")
            self._stream = None

        # Convert to WAV format
        wav_data = self._frames_to_wav()
        logger.info(f"Recording stopped, {len(wav_data)} bytes captured")
        self.audio_ready.emit(wav_data)
        return wav_data

    def cancel_recording(self) -> None:
        """Cancel recording without processing."""
        self._recording.clear()

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.warning(f"Error closing stream: {e}")
            self._stream = None

        self._frames = []
        logger.info("Recording cancelled")

    def _frames_to_wav(self) -> bytes:
        """Convert recorded frames to WAV format."""
        if not self._frames:
            return b""

        audio = self._ensure_audio()
        wav_buffer = io.BytesIO()

        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(b"".join(self._frames))

        return wav_buffer.getvalue()

    def _get_device_index(self) -> int | None:
        """Get device index from config or None for default."""
        if not self.config.input_device:
            return None

        audio = self._ensure_audio()
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info["name"] == self.config.input_device:
                return i

        logger.warning(f"Device '{self.config.input_device}' not found, using default")
        return None

    def get_devices(self) -> list[dict]:
        """List available input devices.

        Returns:
            List of device info dictionaries with 'index', 'name', 'channels' keys.
        """
        audio = self._ensure_audio()
        devices = []

        for i in range(audio.get_device_count()):
            try:
                info = audio.get_device_info_by_index(i)
                max_input_channels = info["maxInputChannels"]
                if not isinstance(max_input_channels, int | float):
                    continue
                if max_input_channels > 0:
                    devices.append(
                        {
                            "index": i,
                            "name": info["name"],
                            "channels": info["maxInputChannels"],
                        }
                    )
            except Exception as e:
                logger.debug(f"Error getting device {i} info: {e}")

        return devices

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording.is_set()

    def cleanup(self) -> None:
        """Clean up PyAudio resources."""
        if self._recording.is_set():
            self.cancel_recording()

        if self._audio:
            try:
                self._audio.terminate()
            except Exception as e:
                logger.warning(f"Error terminating PyAudio: {e}")
            self._audio = None

    def __del__(self):
        self.cleanup()
