from typing import Dict, List

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
                              QLabel, QPushButton, QHBoxLayout)

from core.annotation_validator import Violation

_TYPE_COLORS = {
    "HALLUCINATION": QColor(220, 80,  80),
    "GRAMMAR":       QColor(220, 140, 30),
    "VISUAL":        QColor(180, 80,  180),
    "OTHER":         QColor(120, 120, 120),
    # auto-detected
    "OVER_LIMIT":    QColor(220, 50,  50),
    "OVER_WARN":     QColor(210, 130, 30),
    "DUPLICATE":     QColor( 50, 100, 200),
    "SIMILAR":       QColor(180, 160, 30),
    "MIXED_LANG":    QColor(140,  50, 180),
}


class FlagPanel(QWidget):
    """面板：显示手动标记的问题帧 + 自动检测到的违规项"""

    frame_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(280)

        self._manual: Dict[int, Dict] = {}
        self._auto:   Dict[int, List[Violation]] = {}

        title_row = QHBoxLayout()
        self._lbl_title = QLabel("<b>问题列表</b>")
        self._btn_export = QPushButton("导出")
        self._btn_export.setFixedWidth(60)
        title_row.addWidget(self._lbl_title)
        title_row.addStretch()
        title_row.addWidget(self._btn_export)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_double_click)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(2, 2, 2, 2)
        vbox.setSpacing(4)
        vbox.addLayout(title_row)
        vbox.addWidget(self._list)

        self._btn_export.clicked.connect(self._export)

    # ── public API ───────────────────────────────────────
    def refresh(self, manual: Dict[int, Dict],
                auto_violations: Dict[int, List[Violation]]):
        self._manual = manual
        self._auto   = auto_violations
        self._rebuild()

    # ── internal ─────────────────────────────────────────
    def _rebuild(self):
        self._list.clear()

        # ── 手动标记 ────────────────────────────────
        if self._manual:
            sep = QListWidgetItem("── 手动标记 ──")
            sep.setFlags(Qt.NoItemFlags)
            sep.setForeground(QColor(150, 150, 150))
            self._list.addItem(sep)
            for idx in sorted(self._manual.keys()):
                info = self._manual[idx]
                ftype = info.get("type", "OTHER")
                note  = info.get("note", "")
                text  = f"  第 {idx + 1} 帧  [{ftype}]"
                if note:
                    text += f"  {note[:40]}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, idx)
                color = _TYPE_COLORS.get(ftype, QColor(120, 120, 120))
                item.setForeground(color)
                self._list.addItem(item)

        # ── 自动检测 ────────────────────────────────
        auto_errors = {idx: viols for idx, viols in self._auto.items()
                       if any(v.severity == "error" for v in viols)}
        auto_warns  = {idx: viols for idx, viols in self._auto.items()
                       if idx not in auto_errors and viols}

        if auto_errors or auto_warns:
            sep = QListWidgetItem("── 自动检测 ──")
            sep.setFlags(Qt.NoItemFlags)
            sep.setForeground(QColor(150, 150, 150))
            self._list.addItem(sep)
            for idx in sorted({**auto_errors, **auto_warns}.keys()):
                viols = self._auto[idx]
                top   = max(viols, key=lambda v: (v.severity == "error", v.severity))
                text  = f"  第 {idx + 1} 帧  [{top.vtype}]  {top.detail[:35]}"
                item  = QListWidgetItem(text)
                item.setData(Qt.UserRole, idx)
                color = _TYPE_COLORS.get(top.vtype, QColor(150, 150, 150))
                item.setForeground(color)
                self._list.addItem(item)

        # update title count
        total = len(self._manual) + len(auto_errors) + len(auto_warns)
        self._lbl_title.setText(f"<b>问题列表（{total}）</b>")

    def _on_double_click(self, item: QListWidgetItem):
        idx = item.data(Qt.UserRole)
        if idx is not None:
            self.frame_requested.emit(int(idx))

    def _export(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        import json, datetime
        path, _ = QFileDialog.getSaveFileName(
            self, "导出问题报告", "",
            "JSON 文件 (*.json);;文本文件 (*.txt)")
        if not path:
            return
        report = {
            "generated": datetime.datetime.now().isoformat(),
            "manual_flags": {str(k): v for k, v in self._manual.items()},
            "auto_violations": {
                str(idx): [{"type": v.vtype, "severity": v.severity, "detail": v.detail}
                            for v in viols]
                for idx, viols in self._auto.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "导出成功", f"报告已保存至：\n{path}")
