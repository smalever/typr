"""Transcription history persistence."""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from typr.utils.logger import logger


HISTORY_DIR = Path.home() / ".local" / "share" / "typr"
HISTORY_FILE = HISTORY_DIR / "history.json"


@dataclass
class HistoryEntry:
    """A single transcription history entry."""

    id: str
    timestamp: str  # ISO 8601
    text: str
    model: str = ""
    language: Optional[str] = None
    duration_ms: Optional[int] = None

    @classmethod
    def create(
        cls,
        text: str,
        model: str = "",
        language: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> "HistoryEntry":
        return cls(
            id=uuid.uuid4().hex,
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            text=text,
            model=model,
            language=language,
            duration_ms=duration_ms,
        )

    def datetime(self) -> datetime:
        try:
            return datetime.fromisoformat(self.timestamp)
        except ValueError:
            return datetime.now()


class HistoryManager(QObject):
    """JSON-backed history store. Newest entries first."""

    history_changed = pyqtSignal()

    def __init__(self, max_entries: int = 500, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._max_entries = max_entries
        self._entries: list[HistoryEntry] = []
        self._load()

    def set_max_entries(self, value: int) -> None:
        self._max_entries = max(1, value)
        if len(self._entries) > self._max_entries:
            self._trim_and_save()

    def entries(self) -> list[HistoryEntry]:
        return list(self._entries)

    def add(self, entry: HistoryEntry) -> None:
        self._entries.insert(0, entry)
        self._trim_and_save()
        self.history_changed.emit()

    def delete(self, entry_id: str) -> bool:
        for i, entry in enumerate(self._entries):
            if entry.id == entry_id:
                self._entries.pop(i)
                self._save()
                self.history_changed.emit()
                return True
        return False

    def clear(self) -> None:
        self._entries = []
        self._save()
        self.history_changed.emit()

    def _load(self) -> None:
        if not HISTORY_FILE.exists():
            return
        try:
            with open(HISTORY_FILE) as f:
                data = json.load(f)
            entries = data.get("entries", []) if isinstance(data, dict) else data
            # Drop unknown fields (e.g., audio_path/audio_bytes from earlier versions)
            known = {f for f in HistoryEntry.__dataclass_fields__}
            self._entries = [
                HistoryEntry(**{k: v for k, v in e.items() if k in known})
                for e in entries
            ]
            logger.info(f"Loaded {len(self._entries)} history entries")
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"Failed to load history: {e}")
            self._entries = []

    def _trim_and_save(self) -> None:
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[: self._max_entries]
        self._save()

    def _save(self) -> None:
        try:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            data = {"entries": [asdict(e) for e in self._entries]}
            tmp = HISTORY_FILE.with_suffix(".json.tmp")
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            tmp.replace(HISTORY_FILE)
        except OSError as e:
            logger.error(f"Failed to save history: {e}")
