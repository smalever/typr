"""Configuration management for Typr."""

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Optional


def _coerce(dc_cls, value: Any):
    """Build a dataclass from a dict, ignoring unknown keys; pass through if already correct type."""
    if isinstance(value, dc_cls):
        return value
    if not isinstance(value, dict):
        return dc_cls()
    known = {f.name for f in fields(dc_cls)}
    return dc_cls(**{k: v for k, v in value.items() if k in known})


@dataclass
class AudioConfig:
    """Audio recording configuration."""

    input_device: Optional[str] = None  # None = default device
    sample_rate: int = 16000
    channels: int = 1


@dataclass
class TranscriptionConfig:
    """Transcription settings."""

    model: str = "whisper-1"  # whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe
    language: Optional[str] = None  # None = auto-detect
    mode: str = "push_to_talk"  # push_to_talk, live
    prompt: str = ""  # Context prompt for better accuracy


@dataclass
class HotkeyConfig:
    """Hotkey settings."""

    push_to_talk: str = "Meta+Shift+Space"
    cancel_recording: str = "Escape"


@dataclass
class UIConfig:
    """UI settings."""

    show_notifications: bool = True
    notification_duration: int = 3000  # ms
    typing_delay: int = 0  # ms between characters


@dataclass
class HistoryConfig:
    """Transcription history settings."""

    enabled: bool = True
    max_entries: int = 500


@dataclass
class AppConfig:
    """Main application configuration."""

    api_key: str = ""
    api_base_url: str = "https://api.openai.com/v1"
    audio: AudioConfig = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)

    # Config file location
    CONFIG_DIR: Path = field(default_factory=lambda: Path.home() / ".config" / "typr")
    CONFIG_FILE: Path = field(
        default_factory=lambda: Path.home() / ".config" / "typr" / "config.json"
    )

    # Set to True if loading partially failed; prevents save() from
    # clobbering a config we couldn't fully parse.
    _load_failed: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self):
        """Convert dict fields to dataclass instances, ignoring unknown keys."""
        self.audio = _coerce(AudioConfig, self.audio)
        self.transcription = _coerce(TranscriptionConfig, self.transcription)
        self.hotkeys = _coerce(HotkeyConfig, self.hotkeys)
        self.ui = _coerce(UIConfig, self.ui)
        self.history = _coerce(HistoryConfig, self.history)

    @classmethod
    def load(cls) -> "AppConfig":
        """Load config from file or return defaults.

        Tolerant of unknown / missing fields so that field renames or removals
        in newer versions don't wipe out the user's saved settings. If parsing
        fails entirely, a flag is set to prevent the next save from overwriting
        the existing file.
        """
        config_file = Path.home() / ".config" / "typr" / "config.json"
        if not config_file.exists():
            return cls()

        try:
            with open(config_file) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error loading config (preserving existing file): {e}")
            instance = cls()
            instance._load_failed = True
            return instance

        # Drop non-serializable fields and any keys we don't recognize.
        if not isinstance(data, dict):
            print("Config file is not an object, preserving existing file")
            instance = cls()
            instance._load_failed = True
            return instance

        data.pop("CONFIG_DIR", None)
        data.pop("CONFIG_FILE", None)
        known_top = {f.name for f in fields(cls) if not f.name.startswith("_")} - {
            "CONFIG_DIR",
            "CONFIG_FILE",
        }
        filtered = {k: v for k, v in data.items() if k in known_top}
        return cls(**filtered)

    def save(self) -> None:
        """Save config to file with a backup of the previous version."""
        if self._load_failed:
            print("Config load previously failed; refusing to overwrite existing file")
            return

        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # Convert to dict, excluding non-serializable fields
        data = self._to_dict()
        data.pop("CONFIG_DIR", None)
        data.pop("CONFIG_FILE", None)

        # Back up the previous good config before overwriting.
        if self.CONFIG_FILE.exists():
            backup = self.CONFIG_FILE.with_suffix(".json.bak")
            try:
                backup.write_bytes(self.CONFIG_FILE.read_bytes())
                os.chmod(backup, 0o600)
            except OSError as e:
                print(f"Could not write config backup: {e}")

        # Write atomically via temp file + rename.
        tmp = self.CONFIG_FILE.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o600)
        tmp.replace(self.CONFIG_FILE)

    def _to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            "api_key": self.api_key,
            "api_base_url": self.api_base_url,
            "audio": asdict(self.audio),
            "transcription": asdict(self.transcription),
            "hotkeys": asdict(self.hotkeys),
            "ui": asdict(self.ui),
            "history": asdict(self.history),
        }
