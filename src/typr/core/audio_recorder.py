"""Nonblocking Qt facade; one worker owns the entire PortAudio lifecycle."""

import io
import struct
import wave
from dataclasses import replace
from threading import Event, Lock, Thread

import pyaudio
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot

from typr.config import AudioConfig
from typr.utils.logger import logger

# PortAudio initialization/termination is process-global, not recorder-local.
# Only workers acquire this lock; retain it through the final terminate attempt.
_PORTAUDIO_LIFECYCLE_LOCK = Lock()


class AudioRecorder(QObject):
    """Main-thread API. Bool request results mean acceptance, not device success.

    Recording and enumeration are mutually exclusive. Cancellation invalidates
    even already queued results. Cleanup is terminal and never waits for device
    calls; callers must keep Qt alive until ``is_cleanup_complete()``.
    """

    audio_ready = pyqtSignal(bytes)
    audio_chunk = pyqtSignal(bytes)
    recording_error = pyqtSignal(str)
    level_changed = pyqtSignal(float)
    devices_ready = pyqtSignal(list)
    devices_error = pyqtSignal(str)
    _delivery = pyqtSignal(int, str, object)

    FORMAT = pyaudio.paInt16
    CHUNK_SIZE = 1024

    def __init__(self, config: AudioConfig | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.config = config or AudioConfig()
        self._thread: Thread | None = None
        self._stop = Event()
        self._serial = 0
        self._shutdown = False
        self._mode: str | None = None
        self._delivery.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def is_operation_complete(self) -> bool:
        """True only after the worker has actually exited (no UI join)."""
        return self._thread is None or not self._thread.is_alive()

    def is_cleanup_complete(self) -> bool:
        return self._shutdown and self.is_operation_complete()

    def _request(self, mode: str) -> bool:
        if self._shutdown or not self.is_operation_complete():
            return False
        self._serial += 1
        serial = self._serial
        self._stop = Event()
        self._mode = mode
        config = replace(self.config)
        self._thread = Thread(
            target=self._run, args=(serial, mode, config, self._stop), daemon=True
        )
        try:
            self._thread.start()
        except RuntimeError as exc:
            self._thread = None
            logger.error(f"Audio worker start failed: {exc}")
            self._delivery.emit(serial, "devices_error" if mode == "devices"
                                else "recording_error", str(exc))
        return True

    def start_recording(self) -> bool:
        return self._request("recording")

    def request_devices(self) -> bool:
        """Asynchronously enumerate input devices; no blocking get_devices API."""
        return self._request("devices")

    def stop_recording(self) -> None:
        """Request a WAV result after stream teardown; safe during opening."""
        if self._mode == "recording":
            self._stop.set()

    def cancel_recording(self) -> None:
        """Discard the active operation and any queued results, without waiting."""
        self._serial += 1
        self._stop.set()

    def cleanup(self) -> None:
        self._shutdown = True
        self.cancel_recording()

    def is_recording(self) -> bool:
        return (self._mode == "recording" and not self._stop.is_set()
                and not self.is_operation_complete())

    @pyqtSlot(int, str, object)
    def _deliver(self, serial: int, kind: str, payload: object) -> None:
        if self._shutdown or serial != self._serial:
            return
        if kind not in ("audio_chunk", "level_changed") and not self.is_operation_complete():
            # Emitting a queued result is not evidence that worker finally exited.
            QTimer.singleShot(1, lambda: self._deliver(serial, kind, payload))
            return
        getattr(self, kind).emit(payload)

    def _run(self, serial: int, mode: str, config: AudioConfig, stop: Event) -> None:
        with _PORTAUDIO_LIFECYCLE_LOCK:
            if stop.is_set():
                # A released PTT waiting behind Settings must not open hardware.
                # Cancel/shutdown also takes this path; serial filters its result.
                self._delivery.emit(serial, "devices_ready" if mode == "devices"
                                    else "audio_ready", [] if mode == "devices" else b"")
                return
            self._run_owned(serial, mode, config, stop)

    def _run_owned(self, serial: int, mode: str, config: AudioConfig, stop: Event) -> None:
        """Run with exclusive process-wide ownership of the PortAudio lifecycle."""
        audio = stream = None
        frames = []
        payload = None
        error = None
        try:
            audio = pyaudio.PyAudio()
            if mode == "devices":
                payload = self._devices(audio)
            else:
                device = None
                if config.input_device:
                    for info in self._devices(audio):
                        if info["name"] == config.input_device:
                            device = info["index"]
                            break
                    if device is None:
                        logger.warning("Configured input device not found, using default")
                if not stop.is_set():
                    stream = audio.open(
                        format=self.FORMAT, channels=config.channels,
                        rate=config.sample_rate, input=True,
                        frames_per_buffer=self.CHUNK_SIZE, input_device_index=device,
                    )
                while not stop.is_set() and stream is not None:
                    data = stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                    frames.append(data)
                    self._delivery.emit(serial, "audio_chunk", data)
                    self._delivery.emit(serial, "level_changed", self._calculate_level(data))
                payload = self._frames_to_wav(frames, config, audio)
        except Exception as exc:  # Worker runtime boundary, including device removal/privacy.
            error = f"Audio {mode} failed: {exc}"
            logger.error(error)
        finally:
            # Each teardown is attempted independently even if a previous step fails.
            for resource, method in ((stream, "stop_stream"), (stream, "close"),
                                     (audio, "terminate")):
                if resource is not None:
                    try:
                        getattr(resource, method)()
                    except Exception as exc:
                        message = f"Audio {method} failed: {exc}"
                        logger.error(message)
                        error = error or message
        kind = "devices" if mode == "devices" else "audio"
        self._delivery.emit(serial, ("devices_error" if mode == "devices"
                                    else "recording_error") if error else f"{kind}_ready",
                            error if error else payload)

    @staticmethod
    def _devices(audio) -> list[dict]:
        devices = []
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            channels = info["maxInputChannels"]
            if isinstance(channels, int | float) and channels > 0:
                devices.append({"index": index, "name": info["name"], "channels": channels})
        return devices

    @staticmethod
    def _calculate_level(data: bytes) -> float:
        if not data:
            return 0.0
        samples = struct.unpack(f"<{len(data) // 2}h", data)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return min(1.0, rms / 32767.0 * 3)

    def _frames_to_wav(self, frames: list[bytes], config: AudioConfig, audio) -> bytes:
        if not frames:
            return b""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(config.channels)
            wav.setsampwidth(audio.get_sample_size(self.FORMAT))
            wav.setframerate(config.sample_rate)
            wav.writeframes(b"".join(frames))
        return buffer.getvalue()
