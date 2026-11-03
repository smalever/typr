"""Transcription history persistence."""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from typr.platforms.paths import atomic_write, history_dir
from typr.utils.logger import logger

HISTORY_DIR = history_dir()
HISTORY_FILE = HISTORY_DIR / "history.json"


@dataclass
class HistoryEntry:
    """A single transcription history entry."""

    id: str
    timestamp: str  # ISO 8601
    text: str
    model: str = ""
    language: str | None = None
    duration_ms: int | None = None

    @classmethod
    def create(
        cls,
        text: str,
        model: str = "",
        language: str | None = None,
        duration_ms: int | None = None,
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

    def __init__(self, max_entries: int = 500, parent: QObject | None = None):
        super().__init__(parent)
        self._max_entries = max_entries
        self._entries: list[HistoryEntry] = []
        self._load_failed = False
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
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("entries") if isinstance(data, dict) else data
            if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
                raise ValueError("History entries must be a list of objects")
            # Drop unknown fields (e.g., audio_path/audio_bytes from earlier versions)
            known = {f for f in HistoryEntry.__dataclass_fields__}
            self._entries = [
                HistoryEntry(**{k: v for k, v in e.items() if k in known}) for e in entries
            ]
            logger.info(f"Loaded {len(self._entries)} history entries")
        except FileNotFoundError:
            if HISTORY_FILE.is_symlink():
                self._load_failed = True
                logger.error("Dangling history link; refusing subsequent writes")
        except (OSError, TypeError, ValueError, RecursionError) as e:
            logger.error("Failed to load history (%s); preserving file", type(e).__name__)
            self._entries = []
            self._load_failed = True

    def _trim_and_save(self) -> None:
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[: self._max_entries]
        self._save()

    def _save(self) -> None:
        if self._load_failed:
            logger.error("History load previously failed; refusing to overwrite existing file")
            return
        try:
            data = {"entries": [asdict(e) for e in self._entries]}
            atomic_write(
                HISTORY_FILE, json.dumps(data, indent=2, ensure_ascii=True).encode("utf-8")
            )
        except OSError as e:
            logger.error(f"Failed to save history: {e}")
