"""Settings dialog for Typr."""

from collections.abc import Callable
from typing import Any

import httpx
from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from typr.config import AppConfig
from typr.utils.i18n import tr
from typr.utils.logger import logger


class _ApiRequestSignals(QObject):
    """Deliver background HTTP results back to the Qt thread."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)


class _ApiRequest(QRunnable):
    """Run one settings HTTP operation outside the main Qt thread."""

    def __init__(self, request: Callable[[], Any]):
        super().__init__()
        self._request = request
        self.signals = _ApiRequestSignals()

    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self._request())
        except Exception as error:
            self.signals.failed.emit(error)


def _authorization_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _request_models(base_url: str, api_key: str) -> list[str]:
    """Fetch model identifiers from an OpenAI-compatible endpoint."""
    headers = _authorization_headers(api_key)
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{base_url}/models", headers=headers)
        if response.status_code == 404:
            response = client.get(f"{base_url}/audio/models", headers=headers)
        if response.status_code == 404:
            schema_response = client.get(
                f"{base_url.rsplit('/v1', 1)[0]}/openapi.json",
                headers=headers,
            )
            schema_response.raise_for_status()
            schema = schema_response.json()
            model_enum = (
                schema.get("paths", {})
                .get("/v1/audio/transcriptions", {})
                .get("post", {})
                .get("requestBody", {})
                .get("content", {})
                .get("multipart/form-data", {})
                .get("schema", {})
                .get("properties", {})
                .get("model", {})
                .get("enum", [])
            )
            data: object = [{"id": model_id} for model_id in model_enum if model_id]
        else:
            response.raise_for_status()
            data = response.json()

    models: list[str] = []
    if isinstance(data, dict):
        raw_models = data.get("data", [])
    elif isinstance(data, list):
        raw_models = data
    else:
        raw_models = []

    if isinstance(raw_models, list):
        for model in raw_models:
            if isinstance(model, str):
                models.append(model)
            elif isinstance(model, dict):
                model_id = model.get("id") or model.get("name")
                if isinstance(model_id, str) and model_id:
                    models.append(model_id)
    return sorted(set(models))


def _probe_api(base_url: str, api_key: str) -> bool:
    """Return whether the transcription endpoint was used as the fallback probe."""
    headers = _authorization_headers(api_key)
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{base_url}/models", headers=headers)
        if response.status_code != 404:
            response.raise_for_status()
            return False

        probe = client.options(f"{base_url}/audio/transcriptions", headers=headers)
        if probe.status_code == 404 or probe.status_code in (401, 403):
            probe.raise_for_status()
        if probe.status_code >= 500:
            probe.raise_for_status()
        return True


class SettingsDialog(QDialog):
    """Settings dialog with tabs for configuration."""

    settings_saved = pyqtSignal()

    # Common models for the default local endpoint and OpenAI-compatible APIs
    DEFAULT_MODELS = [
        ("parakeet-tdt-0.6b-v3-onnx/", "Parakeet TDT 0.6B v3 ONNX"),
        ("whisper-1", "Whisper 1 (Standard)"),
        ("gpt-4o-transcribe", "GPT-4o Transcribe (Better accuracy)"),
        ("gpt-4o-mini-transcribe", "GPT-4o Mini Transcribe (Faster)"),
    ]

    # Common languages
    LANGUAGES = [
        (None, "Auto-detect"),
        ("en", "English"),
        ("es", "Spanish"),
        ("fr", "French"),
        ("de", "German"),
        ("it", "Italian"),
        ("pt", "Portuguese"),
        ("ru", "Russian"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("zh", "Chinese"),
        ("ar", "Arabic"),
        ("hi", "Hindi"),
    ]

    def __init__(self, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        thread_pool = QThreadPool.globalInstance()
        if thread_pool is None:
            raise RuntimeError("Qt global thread pool is unavailable")
        self._thread_pool = thread_pool
        self._active_requests: set[_ApiRequest] = set()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle(tr("settings.title", "Typr Settings"))
        self.setMinimumSize(500, 450)

        layout = QVBoxLayout(self)

        # Tab widget
        tabs = QTabWidget()
        tabs.addTab(self._create_general_tab(), tr("settings.tabs.general", "General"))
        tabs.addTab(self._create_api_tab(), tr("settings.tabs.api", "API"))
        tabs.addTab(self._create_hotkeys_tab(), tr("settings.tabs.hotkeys", "Hotkeys"))
        tabs.addTab(self._create_audio_tab(), tr("settings.tabs.audio", "Audio"))
        tabs.addTab(self._create_history_tab(), tr("settings.tabs.history", "History"))
        tabs.addTab(self._create_about_tab(), tr("settings.tabs.about", "About"))
        layout.addWidget(tabs)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        if apply_btn:
            apply_btn.clicked.connect(self._apply)
        layout.addWidget(buttons)

    def _create_general_tab(self) -> QWidget:
        """Create the General settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Transcription settings
        trans_group = QGroupBox(tr("settings.general.transcription", "Transcription"))
        trans_layout = QFormLayout(trans_group)

        # Model selection with fetch button
        model_layout = QHBoxLayout()
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)  # Allow custom model names
        for model_id, model_name in self.DEFAULT_MODELS:
            self._model_combo.addItem(model_name, model_id)
        model_layout.addWidget(self._model_combo, 1)

        self._fetch_models_btn = QPushButton(tr("settings.general.fetch", "Fetch"))
        self._fetch_models_btn.setToolTip(
            tr("settings.general.fetch_tooltip", "Fetch available models from API endpoint")
        )
        self._fetch_models_btn.clicked.connect(self._fetch_models)
        model_layout.addWidget(self._fetch_models_btn)
        trans_layout.addRow(tr("settings.general.model", "Model:"), model_layout)

        # Language selection
        self._language_combo = QComboBox()
        for lang_code, lang_name in self.LANGUAGES:
            self._language_combo.addItem(lang_name, lang_code)
        trans_layout.addRow(tr("settings.general.language", "Language:"), self._language_combo)

        # Context prompt
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setMaximumHeight(80)
        self._prompt_edit.setPlaceholderText(
            tr(
                "settings.general.context_placeholder",
                "Optional context to improve accuracy (e.g., technical terms, names)",
            )
        )
        trans_layout.addRow(tr("settings.general.context", "Context:"), self._prompt_edit)

        layout.addWidget(trans_group)

        # UI settings
        ui_group = QGroupBox(tr("settings.general.ui", "User Interface"))
        ui_layout = QFormLayout(ui_group)

        # Notifications
        self._notifications_check = QCheckBox(
            tr("settings.general.show_notifications", "Show notifications")
        )
        ui_layout.addRow(self._notifications_check)

        # Notification duration
        self._notif_duration_spin = QSpinBox()
        self._notif_duration_spin.setRange(1000, 10000)
        self._notif_duration_spin.setSingleStep(500)
        self._notif_duration_spin.setSuffix(" ms")
        ui_layout.addRow(
            tr("settings.general.notification_duration", "Notification duration:"),
            self._notif_duration_spin,
        )

        layout.addWidget(ui_group)
        layout.addStretch()

        return widget

    def _create_api_tab(self) -> QWidget:
        """Create the API settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # API settings
        api_group = QGroupBox(tr("settings.api.group", "OpenAI API"))
        api_layout = QFormLayout(api_group)

        # API key
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText(tr("settings.api.key_placeholder", "sk-..."))
        api_layout.addRow(tr("settings.api.key", "API Key:"), self._api_key_edit)

        # Show/hide API key button
        key_layout = QHBoxLayout()
        self._show_key_btn = QPushButton(tr("settings.api.key_show", "Show"))
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.toggled.connect(self._toggle_api_key_visibility)
        key_layout.addWidget(self._api_key_edit)
        key_layout.addWidget(self._show_key_btn)
        api_layout.addRow(tr("settings.api.key", "API Key:"), key_layout)

        # API base URL
        self._api_base_edit = QLineEdit()
        self._api_base_edit.setPlaceholderText(
            tr("settings.api.base_url_placeholder", "http://127.0.0.1:5092/v1")
        )
        api_layout.addRow(tr("settings.api.base_url", "Base URL:"), self._api_base_edit)

        # Test connection button
        self._test_connection_btn = QPushButton(
            tr("settings.api.test_connection", "Test Connection")
        )
        self._test_connection_btn.clicked.connect(self._test_connection)
        api_layout.addRow("", self._test_connection_btn)

        self._api_test_status = QLabel("")
        self._api_test_status.setWordWrap(True)
        api_layout.addRow("", self._api_test_status)

        layout.addWidget(api_group)

        # Info
        info_label = QLabel(
            tr(
                "settings.api.info",
                "Get your API key from "
                "<a href='https://platform.openai.com/api-keys'>OpenAI Platform</a>",
            )
        )
        info_label.setOpenExternalLinks(True)
        layout.addWidget(info_label)

        layout.addStretch()

        return widget

    def _create_hotkeys_tab(self) -> QWidget:
        """Create the Hotkeys settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Hotkey settings
        hotkey_group = QGroupBox(tr("settings.hotkeys.group", "Keyboard Shortcuts"))
        hotkey_layout = QFormLayout(hotkey_group)

        # Push-to-talk hotkey
        self._ptt_hotkey_edit = QKeySequenceEdit()
        hotkey_layout.addRow(tr("settings.hotkeys.ptt", "Push-to-Talk:"), self._ptt_hotkey_edit)

        # Cancel hotkey
        self._cancel_hotkey_edit = QKeySequenceEdit()
        hotkey_layout.addRow(
            tr("settings.hotkeys.cancel", "Cancel Recording:"), self._cancel_hotkey_edit
        )

        layout.addWidget(hotkey_group)

        # Info
        info_label = QLabel(
            tr(
                "settings.hotkeys.info",
                "Note: Hotkeys are registered directly with your input devices via evdev.",
            )
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()

        return widget

    def _create_audio_tab(self) -> QWidget:
        """Create the Audio settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Audio settings
        audio_group = QGroupBox(tr("settings.audio.group", "Audio Input"))
        audio_layout = QFormLayout(audio_group)

        # Input device
        self._device_combo = QComboBox()
        self._device_combo.addItem(tr("settings.audio.device_default", "Default"), None)
        audio_layout.addRow(tr("settings.audio.device", "Input Device:"), self._device_combo)

        # Refresh devices button
        refresh_btn = QPushButton(tr("settings.audio.refresh", "Refresh Devices"))
        refresh_btn.clicked.connect(self._refresh_devices)
        audio_layout.addRow("", refresh_btn)

        # Sample rate (read-only info)
        sample_info = QLabel(tr("settings.audio.sample_rate_val", "16000 Hz (optimal for Whisper)"))
        audio_layout.addRow(tr("settings.audio.sample_rate", "Sample Rate:"), sample_info)

        layout.addWidget(audio_group)

        # Test recording
        test_group = QGroupBox(tr("settings.audio.test_group", "Test Recording"))
        test_layout = QVBoxLayout(test_group)

        test_btn = QPushButton(tr("settings.audio.test_btn", "Test Microphone"))
        test_btn.clicked.connect(self._test_microphone)
        test_layout.addWidget(test_btn)

        self._test_status = QLabel("")
        test_layout.addWidget(self._test_status)

        layout.addWidget(test_group)
        layout.addStretch()

        # Populate devices
        self._refresh_devices()

        return widget

    def _create_history_tab(self) -> QWidget:
        """Create the History settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        history_group = QGroupBox(tr("settings.history.group", "Transcription History"))
        history_layout = QFormLayout(history_group)

        self._history_enabled_check = QCheckBox(
            tr("settings.history.enabled", "Save transcription history")
        )
        history_layout.addRow(self._history_enabled_check)

        self._history_max_spin = QSpinBox()
        self._history_max_spin.setRange(10, 10000)
        self._history_max_spin.setSingleStep(50)
        self._history_max_spin.setSuffix(f" {tr('settings.history.entries_suffix', 'entries')}")
        history_layout.addRow(tr("settings.history.max", "Max entries:"), self._history_max_spin)

        layout.addWidget(history_group)

        info_label = QLabel(
            tr(
                "settings.history.info",
                "History is stored locally at "
                "<code>~/.local/share/typr/history.json</code>. Open the History window "
                "from the tray icon to browse and copy past transcriptions.",
            )
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()
        return widget

    def _create_about_tab(self) -> QWidget:
        """Create the About tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # App info
        title = QLabel("<h2>Typr</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel(tr("settings.about.version", "Version 0.1.0"))
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        desc = QLabel(
            tr(
                "settings.about.desc",
                "Speech-to-text for Linux using OpenAI and Parakeet-compatible APIs",
            )
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addStretch()

        # Links
        links = QLabel(
            '<a href="https://github.com/smalever/typr">GitHub</a> | '
            '<a href="https://platform.openai.com/docs/guides/speech-to-text">Whisper API Docs</a>'
        )
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(links)

        return widget

    def _load_settings(self) -> None:
        """Load current settings into UI."""
        # API
        self._api_key_edit.setText(self.config.api_key)
        self._api_base_edit.setText(self.config.api_base_url)

        # Transcription - handle both preset and custom models
        model_index = self._model_combo.findData(self.config.transcription.model)
        if model_index >= 0:
            self._model_combo.setCurrentIndex(model_index)
        else:
            # Custom model - set as editable text
            self._model_combo.setCurrentText(self.config.transcription.model)

        lang_index = self._language_combo.findData(self.config.transcription.language)
        if lang_index >= 0:
            self._language_combo.setCurrentIndex(lang_index)

        self._prompt_edit.setPlainText(self.config.transcription.prompt)

        # UI
        self._notifications_check.setChecked(self.config.ui.show_notifications)
        self._notif_duration_spin.setValue(self.config.ui.notification_duration)

        # Hotkeys
        self._ptt_hotkey_edit.setKeySequence(
            QKeySequence.fromString(self.config.hotkeys.push_to_talk)
        )
        self._cancel_hotkey_edit.setKeySequence(
            QKeySequence.fromString(self.config.hotkeys.cancel_recording)
        )

        # Audio device
        device_index = self._device_combo.findData(self.config.audio.input_device)
        if device_index >= 0:
            self._device_combo.setCurrentIndex(device_index)

        # History
        self._history_enabled_check.setChecked(self.config.history.enabled)
        self._history_max_spin.setValue(self.config.history.max_entries)

    def _save_settings(self) -> None:
        """Save settings from UI to config."""
        # API
        self.config.api_key = self._api_key_edit.text()
        self.config.api_base_url = self._api_base_edit.text() or "http://127.0.0.1:5092/v1"

        # Transcription - handle both preset (data) and custom (text) models
        model_data = self._model_combo.currentData()
        self.config.transcription.model = (
            model_data if model_data else self._model_combo.currentText()
        )
        self.config.transcription.language = self._language_combo.currentData()
        self.config.transcription.prompt = self._prompt_edit.toPlainText()

        # UI
        self.config.ui.show_notifications = self._notifications_check.isChecked()
        self.config.ui.notification_duration = self._notif_duration_spin.value()

        # Hotkeys
        ptt_seq = self._ptt_hotkey_edit.keySequence()
        if not ptt_seq.isEmpty():
            self.config.hotkeys.push_to_talk = ptt_seq.toString()

        cancel_seq = self._cancel_hotkey_edit.keySequence()
        if not cancel_seq.isEmpty():
            self.config.hotkeys.cancel_recording = cancel_seq.toString()

        # Audio
        self.config.audio.input_device = self._device_combo.currentData()

        # History
        self.config.history.enabled = self._history_enabled_check.isChecked()
        self.config.history.max_entries = self._history_max_spin.value()

        # Save to file
        self.config.save()
        logger.info("Settings saved")

    def _apply(self) -> None:
        """Apply settings without closing."""
        self._save_settings()
        self.settings_saved.emit()

    def _save_and_close(self) -> None:
        """Save settings and close dialog."""
        self._save_settings()
        self.settings_saved.emit()
        self.accept()

    def _toggle_api_key_visibility(self, show: bool) -> None:
        """Toggle API key visibility."""
        if show:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_key_btn.setText(tr("settings.api.key_hide", "Hide"))
        else:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._show_key_btn.setText(tr("settings.api.key_show", "Show"))

    def _fetch_models(self) -> None:
        """Fetch available models from the API endpoint."""
        base_url = (
            self._api_base_edit.text()
            or self.config.api_base_url
            or "http://127.0.0.1:5092/v1"
        ).rstrip("/")
        api_key = self._api_key_edit.text()

        self._fetch_models_btn.setEnabled(False)
        self._fetch_models_btn.setText("...")
        self._start_api_request(
            lambda: _request_models(base_url, api_key),
            self._on_models_fetched,
            self._on_models_fetch_failed,
        )

    def _on_models_fetched(self, result: object) -> None:
        models = result if isinstance(result, list) else []
        if not models:
            QMessageBox.warning(
                self,
                tr("settings.fetch.no_models.title", "No Models"),
                tr("settings.fetch.no_models.msg", "No models found at this endpoint"),
            )
            return

        current_model = self._model_combo.currentText()
        self._model_combo.clear()
        for model_id in models:
            if isinstance(model_id, str):
                self._model_combo.addItem(model_id, model_id)

        index = self._model_combo.findText(current_model)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)

        QMessageBox.information(
            self,
            tr("settings.fetch.success.title", "Models Loaded"),
            tr("settings.fetch.success.msg", "Found {count} model(s)").format(count=len(models)),
        )

    def _on_models_fetch_failed(self, error: Exception) -> None:
        if isinstance(error, httpx.HTTPStatusError):
            if error.response.status_code == 404:
                message = tr(
                    "settings.fetch.err_404",
                    "Model list endpoint not found. Check Base URL in API settings.",
                )
            else:
                message = tr(
                    "settings.fetch.err_api",
                    "API error: {status}\n{text}",
                ).format(
                    status=error.response.status_code,
                    text=error.response.text[:200],
                )
        else:
            message = tr(
                "settings.fetch.err_generic",
                "Failed to fetch models: {error}",
            ).format(error=error)
        QMessageBox.warning(self, tr("settings.fetch.err.title", "Error"), message)

    def _finish_models_request(self) -> None:
        self._fetch_models_btn.setEnabled(True)
        self._fetch_models_btn.setText(tr("settings.general.fetch", "Fetch"))

    def _test_connection(self) -> None:
        """Test API connection."""
        api_key = self._api_key_edit.text()
        base_url = (self._api_base_edit.text() or "http://127.0.0.1:5092/v1").rstrip("/")
        self._api_test_status.setStyleSheet("")
        self._api_test_status.setText(tr("settings.api.test.checking", "Checking connection..."))
        self._test_connection_btn.setEnabled(False)
        self._start_api_request(
            lambda: _probe_api(base_url, api_key),
            self._on_api_test_succeeded,
            self._on_api_test_failed,
        )

    def _on_api_test_succeeded(self, result: object) -> None:
        if result is True:
            message = tr(
                "settings.api.test.valid_transcribe",
                "Settings are valid: transcription endpoint is available.",
            )
        else:
            message = tr("settings.api.test.valid", "Settings are valid.")
        self._set_api_test_status(True, message)

    def _on_api_test_failed(self, error: Exception) -> None:
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            details = error.response.text[:200].strip()
            if status == 401:
                msg = tr("settings.api.test.err_401", "Error 401: API key is missing or invalid.")
            elif status == 403:
                msg = tr(
                    "settings.api.test.err_403",
                    "Error 403: access denied (check API key and permissions).",
                )
            elif status == 404:
                msg = tr(
                    "settings.api.test.err_404",
                    "Error 404: endpoint not found (check Base URL).",
                )
            elif status == 429:
                msg = tr("settings.api.test.err_429", "Error 429: rate limit exceeded.")
            elif 500 <= status <= 599:
                msg = tr("settings.api.test.err_5xx", "Server error (5xx): issue on API side.")
            else:
                msg = tr("settings.api.test.err_generic", "API error {status}.").format(
                    status=status
                )
            if details:
                msg = f"{msg}\n{details}"
        elif isinstance(error, httpx.TimeoutException):
            msg = tr(
                "settings.api.test.timeout",
                "Timeout: server did not respond in time.",
            )
        elif isinstance(error, httpx.NetworkError):
            msg = tr(
                "settings.api.test.network_err",
                "Network error: {error}",
            ).format(error=error)
        else:
            msg = tr(
                "settings.api.test.conn_err",
                "Connection error: {error}",
            ).format(error=error)
        self._set_api_test_status(False, msg)

    def _finish_api_test(self) -> None:
        self._test_connection_btn.setEnabled(True)

    def _start_api_request(
        self,
        request: Callable[[], Any],
        on_success: Callable[[object], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        worker = _ApiRequest(request)
        self._active_requests.add(worker)
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(on_error)
        if on_success == self._on_models_fetched:
            worker.signals.succeeded.connect(lambda _: self._finish_models_request())
            worker.signals.failed.connect(lambda _: self._finish_models_request())
        else:
            worker.signals.succeeded.connect(lambda _: self._finish_api_test())
            worker.signals.failed.connect(lambda _: self._finish_api_test())
        worker.signals.succeeded.connect(lambda _: self._active_requests.discard(worker))
        worker.signals.failed.connect(lambda _: self._active_requests.discard(worker))
        self._thread_pool.start(worker)

    def _set_api_test_status(self, success: bool, message: str) -> None:
        """Show API test status under the test button."""
        color = "#66bb6a" if success else "#ff6b6b"
        self._api_test_status.setStyleSheet(f"color: {color};")
        self._api_test_status.setText(message)

    def _refresh_devices(self) -> None:
        """Refresh audio device list."""
        current_device = self._device_combo.currentData()
        self._device_combo.clear()
        self._device_combo.addItem("Default", None)

        try:
            from typr.core.audio_recorder import AudioRecorder

            recorder = AudioRecorder()
            devices = recorder.get_devices()
            recorder.cleanup()

            for device in devices:
                self._device_combo.addItem(device["name"], device["name"])

            # Restore selection
            if current_device:
                index = self._device_combo.findData(current_device)
                if index >= 0:
                    self._device_combo.setCurrentIndex(index)

        except Exception as e:
            logger.error(f"Failed to get devices: {e}")

    def _test_microphone(self) -> None:
        """Test microphone recording."""
        self._test_status.setText(
            tr("settings.audio.test_status_recording", "Recording for 2 seconds...")
        )

        try:
            from PyQt6.QtCore import QTimer

            from typr.core.audio_recorder import AudioRecorder

            recorder = AudioRecorder()
            recorder.start_recording()

            def stop_recording():
                audio_data = recorder.stop_recording()
                recorder.cleanup()

                if audio_data and len(audio_data) > 1000:
                    self._test_status.setText(
                        tr(
                            "settings.audio.test_status_success", "Success! Recorded {bytes} bytes"
                        ).format(bytes=len(audio_data))
                    )
                else:
                    self._test_status.setText(
                        tr("settings.audio.test_status_fail", "Recording too short or empty")
                    )

            QTimer.singleShot(2000, stop_recording)

        except Exception as e:
            self._test_status.setText(
                tr("settings.audio.test_status_error", "Error: {error}").format(error=e)
            )
