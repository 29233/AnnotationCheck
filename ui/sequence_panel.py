from typing import Dict, Any

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                              QListWidgetItem, QLabel, QPushButton, QLineEdit)

_STATUS_COLORS = {
    "done":        QColor(40,  160,  60),
    "in_progress": QColor(200, 150,   0),
    "pending":     QColor(120, 120, 120),
}


class SequencePanel(QWidget):
    """左侧边栏：可滚动的所有序列列表，带状态徽章"""

    sequence_selected = pyqtSignal(str)   # sequence name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(160)
        self.setMaximumWidth(240)

        self._sequences: list = []
        self._progress: Dict[str, Any] = {}
        self._violations: Dict[str, int] = {}  # seq_name -> violation count

        # ── 筛选栏 ───────────────────────────────────
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("筛选…")

        # ── 列表 ─────────────────────────────────────────
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)

        # ── assemble ─────────────────────────────────────
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(2, 2, 2, 2)
        vbox.setSpacing(4)
        vbox.addWidget(QLabel("<b>序列列表</b>"))
        vbox.addWidget(self._filter)
        vbox.addWidget(self._list)

        self._filter.textChanged.connect(self._apply_filter)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.itemActivated.connect(self._on_double_click)

    # ── public API ───────────────────────────────────────
    def set_sequences(self, names: list, progress: Dict[str, Any],
                      violations: Dict[str, int] = None):
        self._sequences = names
        self._progress  = progress
        self._violations = violations or {}
        self._apply_filter(self._filter.text())

    def refresh_item(self, seq_name: str, progress_entry: Dict[str, Any],
                     violation_count: int = 0):
        self._progress[seq_name]   = progress_entry
        self._violations[seq_name] = violation_count
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == seq_name:
                self._style_item(item, seq_name)
                break

    def highlight_current(self, seq_name: str):
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == seq_name:
                self._list.setCurrentItem(item)
                self._list.scrollToItem(item)
                break

    # ── internal ─────────────────────────────────────────
    def _apply_filter(self, text: str):
        self._list.clear()
        q = text.lower()
        for name in self._sequences:
            if q and q not in name.lower():
                continue
            item = QListWidgetItem()
            item.setData(Qt.UserRole, name)
            self._style_item(item, name)
            self._list.addItem(item)

    def _style_item(self, item: QListWidgetItem, name: str):
        prog   = self._progress.get(name, {})
        status = prog.get("status", "pending")
        vcount = self._violations.get(name, 0)
        badge  = f" ⚠{vcount}" if vcount else ""
        item.setText(f"{name}{badge}")
        color = _STATUS_COLORS.get(status, _STATUS_COLORS["pending"])
        item.setForeground(color)

    def _on_double_click(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        if name:
            self.sequence_selected.emit(name)
