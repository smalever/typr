"""Main application controller for Typr."""

from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from typr.config import AppConfig
from typr.core.audio_recorder import AudioRecorder
from typr.core.history import HistoryEntry, HistoryManager
from typr.core.hotkey_manager import HotkeyManager
from typr.core.text_injector import TextInjector
from typr.core.transcriber import WhisperTranscriber
from typr.ui.tray_icon import TrayIcon, TrayState
from typr.utils.logger import logger
from typr.utils.i18n import tr


class AppState(Enum):
    """Application states."""

    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    TYPING = auto()
    ERROR = auto()


class TyprApp(QObject):
    """Main application controller.

    Coordinates all components and manages application state.
    """

    state_changed = pyqtSignal(AppState)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # Load configuration
        self.config = AppConfig.load()
        logger.info("Configuration loaded")

        # Initialize state
        self._state = AppState.IDLE

        # Initialize components
        self._init_components()

        # Connect signals
        self._connect_signals()

    def _init_components(self) -> None:
        """Initialize all application components."""
        # Core components
        self.audio_recorder = AudioRecorder(self.config.audio)
        self.transcriber = WhisperTranscriber(
            api_key=self.config.api_key,
            api_base_url=self.config.api_base_url,
            model=self.config.transcription.model,
        )
        self.transcriber.language = self.config.transcription.language
        self.transcriber.prompt = self.config.transcription.prompt

        self.text_injector = TextInjector(
            typing_delay=self.config.ui.typing_delay,
            restore_delay=self.config.ui.notification_duration,
        )
        self.hotkey_manager = HotkeyManager(self.config.hotkeys)

        # History
        self.history = HistoryManager(self.config.history.max_entries)

        # UI components
        self.tray_icon = TrayIcon(self.config.hotkeys.push_to_talk)
        self.tray_icon.set_mode(self.config.transcription.mode)

        # Dialogs (lazy loaded)
        self._settings_dialog: Optional["SettingsDialog"] = None
        self._history_dialog: Optional["HistoryDialog"] = None

    def _connect_signals(self) -> None:
        """Connect all component signals."""
        # Hotkey -> Recording
        self.hotkey_manager.recording_started.connect(self._on_recording_start)
        self.hotkey_manager.recording_stopped.connect(self._on_recording_stop)
        self.hotkey_manager.hotkey_error.connect(self._on_hotkey_error)

        # Audio -> Transcription
        self.audio_recorder.audio_ready.connect(self._on_audio_ready)
        self.audio_recorder.recording_error.connect(self._on_error)

        # Transcription -> Text injection
        self.transcriber.transcription_complete.connect(self._on_transcription_complete)
        self.transcriber.transcription_error.connect(self._on_error)

        # UI
        self.tray_icon.settings_requested.connect(self._show_settings)
        self.tray_icon.history_requested.connect(self._show_history)
        self.tray_icon.quit_requested.connect(self._quit)
        self.tray_icon.record_toggled.connect(self._on_record_toggled)

    @pyqtSlot(bool)
    def _on_record_toggled(self, start: bool) -> None:
        """Handle manual record toggle from tray icon."""
        if start:
            self._on_recording_start()
        else:
            self._on_recording_stop()

    def start(self) -> None:
        """Start the application."""
        logger.info("Starting Typr")

        # Check for text injection support
        if not self.text_injector.is_available():
            self.tray_icon.show_notification(
                tr("app.notify.error_title", "Typr Error"),
                tr("app.notify.text_injection_unavailable", "Text injection unavailable. Check /dev/uinput access and clipboard tools."),
                self.tray_icon.MessageIcon.Warning,
            )

        # Initialize hotkeys
        if not self.hotkey_manager.initialize():
            self.tray_icon.show_notification(
                tr("app.notify.error_title", "Typr Error"),
                tr("app.notify.hotkey_register_failed", "Could not register hotkey. Check Settings for manual configuration."),
                self.tray_icon.MessageIcon.Warning,
            )

        # Show tray icon
        self.tray_icon.show()
        self.tray_icon.show_notification(
            tr("app.notify.started.title", "Typr Started"),
            tr("app.notify.started.msg", "Hold {hotkey} to record").format(hotkey=self.config.hotkeys.push_to_talk),
            self.tray_icon.MessageIcon.Information,
            2000,
        )

    @pyqtSlot()
    def _on_recording_start(self) -> None:
        """Handle recording start from hotkey."""
        if self._state != AppState.IDLE:
            logger.debug(f"Cannot start recording in state {self._state}")
            return

        self._set_state(AppState.RECORDING)
        if not self.audio_recorder.start_recording():
            self._set_state(AppState.ERROR, tr("app.notify.recording_start_failed", "Failed to start recording"))

    @pyqtSlot()
    def _on_recording_stop(self) -> None:
        """Handle recording stop from hotkey."""
        if self._state != AppState.RECORDING:
            logger.debug(f"Cannot stop recording in state {self._state}")
            return

        self._set_state(AppState.TRANSCRIBING)
        self.audio_recorder.stop_recording()

    @pyqtSlot(bytes)
    def _on_audio_ready(self, audio_data: bytes) -> None:
        """Handle completed audio recording."""
        if not audio_data:
            self._set_state(AppState.IDLE, tr("app.notify.no_audio", "No audio recorded"))
            return

        logger.info(f"Audio ready: {len(audio_data)} bytes")
        self.transcriber.transcribe(audio_data)

    @pyqtSlot(str)
    def _on_transcription_complete(self, text: str) -> None:
        """Handle completed transcription."""
        if not text or not text.strip():
            logger.info("Empty transcription result")
            self._set_state(AppState.IDLE)
            return

        logger.info(f"Transcription: {text[:50]}...")
        self._record_history(text)
        self._set_state(AppState.TYPING)

        # Type the text
        if self.text_injector.type_text(text):
            if self.config.ui.show_notifications:
                self.tray_icon.show_notification(
                    tr("app.notify.transcription_complete", "Transcription Complete"),
                    text[:100] + ("..." if len(text) > 100 else ""),
                    self.tray_icon.MessageIcon.Information,
                    self.config.ui.notification_duration,
                )
        else:
            self._set_state(AppState.ERROR, tr("app.notify.type_failed", "Failed to type text"))
            return

        self._set_state(AppState.IDLE)

    def _record_history(self, text: str) -> None:
        """Persist a completed transcription to history if enabled."""
        if not self.config.history.enabled:
            return

        self.history.add(
            HistoryEntry.create(
                text=text,
                model=self.config.transcription.model,
                language=self.config.transcription.language,
            )
        )

    @pyqtSlot(str)
    def _on_error(self, message: str) -> None:
        """Handle errors from components."""
        self._set_state(AppState.ERROR, message)

    @pyqtSlot(str)
    def _on_hotkey_error(self, message: str) -> None:
        """Handle hotkey registration errors."""
        logger.error(f"Hotkey error: {message}")
        # Don't change state, just notify
        self.tray_icon.show_notification(
            "Hotkey Error",
            message,
            self.tray_icon.MessageIcon.Warning,
        )

    def _set_state(self, state: AppState, message: Optional[str] = None) -> None:
        """Set application state.

        Args:
            state: New state.
            message: Optional status message.
        """
        old_state = self._state
        self._state = state

        logger.debug(f"State: {old_state.name} -> {state.name}")

        # Map to tray states
        tray_state = {
            AppState.IDLE: TrayState.IDLE,
            AppState.RECORDING: TrayState.RECORDING,
            AppState.TRANSCRIBING: TrayState.PROCESSING,
            AppState.TYPING: TrayState.PROCESSING,
            AppState.ERROR: TrayState.ERROR,
        }.get(state, TrayState.IDLE)

        self.tray_icon.set_state(tray_state, message)
        self.state_changed.emit(state)

        # Auto-recover from error state
        if state == AppState.ERROR:
            if message:
                self.tray_icon.show_error(message)
            QTimer.singleShot(3000, self._recover_from_error)

    @pyqtSlot()
    def _recover_from_error(self) -> None:
        """Recover from error state."""
        if self._state == AppState.ERROR:
            self._set_state(AppState.IDLE)

    @pyqtSlot()
    def _show_settings(self) -> None:
        """Show settings dialog."""
        from typr.ui.settings_dialog import SettingsDialog

        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.config)
            self._settings_dialog.settings_saved.connect(self._on_settings_saved)

        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    @pyqtSlot()
    def _show_history(self) -> None:
        """Show transcription history dialog."""
        from typr.ui.history_dialog import HistoryDialog

        if self._history_dialog is None:
            self._history_dialog = HistoryDialog(self.history)

        self._history_dialog.show()
        self._history_dialog.raise_()
        self._history_dialog.activateWindow()

    @pyqtSlot()
    def _on_settings_saved(self) -> None:
        """Handle settings saved."""
        logger.info("Settings saved, reloading")

        # Update components with new settings
        self.transcriber.update_settings(
            api_key=self.config.api_key,
            api_base_url=self.config.api_base_url,
            model=self.config.transcription.model,
            language=self.config.transcription.language,
            prompt=self.config.transcription.prompt,
        )
        self.text_injector.set_typing_delay(self.config.ui.typing_delay)
        self.text_injector.set_restore_delay(self.config.ui.notification_duration)
        self.tray_icon.set_hotkey(self.config.hotkeys.push_to_talk)
        self.tray_icon.set_mode(self.config.transcription.mode)
        self.history.set_max_entries(self.config.history.max_entries)

        # Re-register hotkey if changed
        self.hotkey_manager.update_shortcut(self.config.hotkeys.push_to_talk)

    @pyqtSlot()
    def _quit(self) -> None:
        """Quit the application."""
        logger.info("Quitting Typr")

        # Cancel any ongoing recording
        if self._state == AppState.RECORDING:
            self.audio_recorder.cancel_recording()

        # Save config
        self.config.save()

        # Cleanup
        self.audio_recorder.cleanup()
        self.hotkey_manager.cleanup()
        self.text_injector.cleanup()

        # Quit application
        QApplication.quit()

    def get_state(self) -> AppState:
        """Get current application state."""
        return self._state
