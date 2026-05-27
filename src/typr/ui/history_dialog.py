"""History viewer dialog."""

from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from typr.core.history import HistoryEntry, HistoryManager
from typr.utils.i18n import tr


class HistoryRowWidget(QWidget):
    """A single row in the history list with inline Copy and Delete buttons."""

    copy_requested = pyqtSignal(str)  # entry id
    delete_requested = pyqtSignal(str)

    def __init__(self, entry: HistoryEntry, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._entry_id = entry.id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self._timestamp_label = QLabel(self._format_timestamp(entry))
        ts_font = self._timestamp_label.font()
        ts_font.setPointSizeF(max(7.0, ts_font.pointSizeF() * 0.85))
        self._timestamp_label.setFont(ts_font)

        self._snippet_label = QLabel(self._format_snippet(entry))
        self._snippet_label.setWordWrap(False)
        self._snippet_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        text_col.addWidget(self._timestamp_label)
        text_col.addWidget(self._snippet_label)
        layout.addLayout(text_col, 1)

        self._copy_btn = QPushButton(tr("history.row.copy", "Copy"))
        self._copy_btn.setFixedWidth(72)
        self._copy_btn.setToolTip(tr("history.row.copy_tooltip", "Copy this transcription to the clipboard"))
        self._copy_btn.clicked.connect(self._on_copy_clicked)
        layout.addWidget(self._copy_btn)

        self._delete_btn = QPushButton(tr("history.row.delete", "Delete"))
        self._delete_btn.setFixedWidth(72)
        self._delete_btn.setToolTip(tr("history.row.delete_tooltip", "Delete this transcription from history"))
        self._delete_btn.clicked.connect(lambda: self.delete_requested.emit(self._entry_id))
        layout.addWidget(self._delete_btn)

        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        """Update label colors so they remain legible against the selection highlight."""
        palette = self.palette()
        if selected:
            primary = palette.color(QPalette.ColorRole.HighlightedText)
            muted = primary
        else:
            primary = palette.color(QPalette.ColorRole.Text)
            muted = palette.color(QPalette.ColorRole.PlaceholderText)
            # PlaceholderText can be unset on some styles; fall back to a dimmed Text.
            if not muted.isValid() or muted.alpha() == 0:
                muted = palette.color(QPalette.ColorRole.Text)
                muted.setAlpha(150)

        for label, color in ((self._snippet_label, primary), (self._timestamp_label, muted)):
            pal = label.palette()
            pal.setColor(QPalette.ColorRole.WindowText, color)
            pal.setColor(QPalette.ColorRole.Text, color)
            label.setPalette(pal)

    @staticmethod
    def _format_timestamp(entry: HistoryEntry) -> str:
        try:
            return datetime.fromisoformat(entry.timestamp).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return entry.timestamp

    @staticmethod
    def _format_snippet(entry: HistoryEntry) -> str:
        snippet = entry.text.strip().replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        return snippet or tr("history.row.empty", "(empty)")

    def _on_copy_clicked(self) -> None:
        self.copy_requested.emit(self._entry_id)
        self._copy_btn.setText(tr("history.row.copied", "Copied!"))
        self._copy_btn.setEnabled(False)
        QTimer.singleShot(900, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self._copy_btn.setText(tr("history.row.copy", "Copy"))
        self._copy_btn.setEnabled(True)

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), 52)


class HistoryDialog(QDialog):
    """Browse, search, copy, and delete past transcriptions."""

    def __init__(self, history: HistoryManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._history = history
        self._all_entries: list[HistoryEntry] = []

        self._setup_ui()
        self._reload()

        self._history.history_changed.connect(self._reload)

    def _setup_ui(self) -> None:
        self.setWindowTitle(tr("history.title", "Typr History"))
        self.resize(820, 540)

        layout = QVBoxLayout(self)

        # Search bar
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(tr("history.search", "Search:")))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(tr("history.search_placeholder", "Filter by text..."))
        self._search_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self._search_edit)
        layout.addLayout(search_row)

        # Splitter: list on left, preview on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setUniformItemSizes(True)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._list)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._meta_label = QLabel("")
        self._meta_label.setStyleSheet("color: gray;")
        right_layout.addWidget(self._meta_label)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(tr("history.preview_placeholder", "Select an entry to view the full transcription"))
        right_layout.addWidget(self._preview)

        preview_btn_row = QHBoxLayout()
        self._copy_preview_btn = QPushButton(tr("history.copy_preview", "Copy full text"))
        self._copy_preview_btn.clicked.connect(self._copy_selected)
        preview_btn_row.addWidget(self._copy_preview_btn)
        preview_btn_row.addStretch()
        right_layout.addLayout(preview_btn_row)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        # Footer buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._clear_btn = QPushButton(tr("history.clear_all", "Clear All..."))
        self._clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self._clear_btn)

        close_btn = QPushButton(tr("history.close", "Close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._update_buttons()

    @pyqtSlot()
    def _reload(self) -> None:
        self._all_entries = self._history.entries()
        self._apply_filter()

    @pyqtSlot()
    def _apply_filter(self) -> None:
        query = self._search_edit.text().strip().lower()
        previously_selected = self._current_entry_id()

        self._list.clear()
        for entry in self._all_entries:
            if query and query not in entry.text.lower():
                continue
            item = QListWidgetItem(self._list)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setToolTip(entry.text[:300])

            row = HistoryRowWidget(entry)
            row.copy_requested.connect(self._copy_entry_id)
            row.delete_requested.connect(self._delete_entry_id)
            item.setSizeHint(row.sizeHint())

            self._list.addItem(item)
            self._list.setItemWidget(item, row)

        # Restore selection if possible, else select first
        if previously_selected:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.ItemDataRole.UserRole) == previously_selected:
                    self._list.setCurrentRow(i)
                    break
        if self._list.currentRow() < 0 and self._list.count() > 0:
            self._list.setCurrentRow(0)

        self._update_buttons()
        if self._list.count() == 0:
            self._preview.clear()
            self._meta_label.setText(
                tr("history.no_matches", "No entries match.") if query else tr("history.no_history", "No history yet.")
            )

    def _current_entry_id(self) -> Optional[str]:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _current_entry(self) -> Optional[HistoryEntry]:
        return self._lookup_entry(self._current_entry_id())

    def _lookup_entry(self, entry_id: Optional[str]) -> Optional[HistoryEntry]:
        if not entry_id:
            return None
        for entry in self._all_entries:
            if entry.id == entry_id:
                return entry
        return None

    def _on_selection_changed(
        self,
        current: Optional[QListWidgetItem] = None,
        previous: Optional[QListWidgetItem] = None,
    ) -> None:
        if previous is not None:
            old_widget = self._list.itemWidget(previous)
            if isinstance(old_widget, HistoryRowWidget):
                old_widget.set_selected(False)
        if current is not None:
            new_widget = self._list.itemWidget(current)
            if isinstance(new_widget, HistoryRowWidget):
                new_widget.set_selected(True)

        entry = self._current_entry()
        if entry is None:
            self._preview.clear()
            self._meta_label.setText("")
        else:
            self._preview.setPlainText(entry.text)
            self._meta_label.setText(self._format_meta(entry))
        self._update_buttons()

    @staticmethod
    def _format_meta(entry: HistoryEntry) -> str:
        try:
            ts = datetime.fromisoformat(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            ts = entry.timestamp
        parts = [ts]
        if entry.model:
            parts.append(entry.model)
        if entry.language:
            parts.append(entry.language)
        if entry.duration_ms:
            parts.append(f"{entry.duration_ms / 1000:.1f}s")
        return "  •  ".join(parts)

    def _update_buttons(self) -> None:
        self._copy_preview_btn.setEnabled(self._current_entry() is not None)
        self._clear_btn.setEnabled(len(self._all_entries) > 0)

    @pyqtSlot(str)
    def _copy_entry_id(self, entry_id: str) -> None:
        entry = self._lookup_entry(entry_id)
        if entry is not None:
            QGuiApplication.clipboard().setText(entry.text)

    @pyqtSlot()
    def _copy_selected(self) -> None:
        entry = self._current_entry()
        if entry is not None:
            QGuiApplication.clipboard().setText(entry.text)

    @pyqtSlot(str)
    def _delete_entry_id(self, entry_id: str) -> None:
        entry = self._lookup_entry(entry_id)
        if entry is None:
            return
        confirm = QMessageBox.question(
            self,
            tr("history.delete_confirm.title", "Delete entry"),
            tr("history.delete_confirm.msg", "Delete this transcription from history?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._history.delete(entry_id)

    @pyqtSlot()
    def _clear_all(self) -> None:
        confirm = QMessageBox.question(
            self,
            tr("history.clear_confirm.title", "Clear history"),
            tr("history.clear_confirm.msg", "Permanently delete all transcription history?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._history.clear()
