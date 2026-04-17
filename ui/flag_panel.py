from typing import Dict, List, Set

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
                              QLabel, QPushButton, QHBoxLayout, QCheckBox,
                              QScrollArea, QButtonGroup, QRadioButton)

from core.annotation_validator import Violation

_TYPE_COLORS = {
    "HALLUCINATION": QColor(220, 80,  80),
    "GRAMMAR":       QColor(220, 140, 30),
    "VISUAL":        QColor(180, 80,  180),
    "OTHER":         QColor(120, 120, 120),
    "MODIFIED":      QColor( 50, 180,  80),
    "AI_GENERATED":  QColor( 80, 200, 180),
    # auto-detected
    "OVER_LIMIT":    QColor(220, 50,  50),
    "OVER_WARN":     QColor(210, 130, 30),
    "DUPLICATE":     QColor( 50, 100, 200),
    "SIMILAR":       QColor(180, 160, 30),
    "MIXED_LANG":    QColor(140,  50, 180),
}

_MANUAL_LABELS = {
    "HALLUCINATION": "幻觉",
    "GRAMMAR":       "语法",
    "VISUAL":        "视觉",
    "OTHER":         "其他",
    "MODIFIED":      "已修改",
    "AI_GENERATED":  "AI改写",
}

_AUTO_LABELS = {
    "OVER_LIMIT":  "超限",
    "OVER_WARN":   "超警告",
    "DUPLICATE":   "重复",
    "SIMILAR":     "相似",
    "MIXED_LANG":  "混杂",
}


class FlagPanel(QWidget):
    """
    问题帧列表面板，支持按类型筛选、批量改写。

    Signals
    -------
    frame_requested(int)          – 双击某条跳转到对应帧
    filter_changed(set)           – 筛选条件变化时发出（激活的类型名集合）
    bulk_rewrite_requested(list) – 用户请求批量改写（发出候选帧号列表）
    """

    frame_requested        = pyqtSignal(int)
    filter_changed        = pyqtSignal(set)
    bulk_rewrite_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(280)

        self._manual: Dict[int, Dict] = {}
        self._auto:   Dict[int, List[Violation]] = {}
        self._active_filters: Set[str] = set()
        self._pending_rewrite: List[int] = []  # 待改写帧（由主窗口注入）

        # ── 标题行 ─────────────────────────────────────────────
        title_row = QHBoxLayout()
        self._lbl_title = QLabel("<b>问题列表</b>")
        self._btn_export = QPushButton("导出")
        self._btn_export.setFixedWidth(55)
        title_row.addWidget(self._lbl_title)
        title_row.addStretch()
        title_row.addWidget(self._btn_export)

        # ── 筛选行（分三行）────────────────────────────────────
        # 第一行：手动标记类型 - 前半
        filter_row1 = QHBoxLayout()
        filter_row1.setContentsMargins(0, 2, 0, 1)
        lbl_filter = QLabel("筛选：")
        lbl_filter.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        self._cb_hall    = QCheckBox("幻觉")
        self._cb_grammar = QCheckBox("语法")
        self._cb_visual  = QCheckBox("视觉")
        self._cb_other   = QCheckBox("其他")
        for cb in (self._cb_hall, self._cb_grammar, self._cb_visual, self._cb_other):
            cb.setStyleSheet("font-size: 11px;")
            cb.stateChanged.connect(self._on_filter_changed)
        filter_row1.addWidget(lbl_filter)
        filter_row1.addWidget(self._cb_hall)
        filter_row1.addWidget(self._cb_grammar)
        filter_row1.addWidget(self._cb_visual)
        filter_row1.addWidget(self._cb_other)
        filter_row1.addStretch()

        # 第二行：手动标记类型 - 后半
        filter_row2 = QHBoxLayout()
        filter_row2.setContentsMargins(0, 1, 0, 1)
        self._cb_modified = QCheckBox("已修改")
        self._cb_ai       = QCheckBox("AI改写")
        self._cb_errors   = QCheckBox("错误")
        self._cb_warnings = QCheckBox("警告")
        for cb in (self._cb_modified, self._cb_ai, self._cb_errors, self._cb_warnings):
            cb.setStyleSheet("font-size: 11px;")
            cb.stateChanged.connect(self._on_filter_changed)
        filter_row2.addWidget(self._cb_modified)
        filter_row2.addWidget(self._cb_ai)
        filter_row2.addSpacing(8)
        filter_row2.addWidget(self._cb_errors)
        filter_row2.addWidget(self._cb_warnings)
        filter_row2.addStretch()
        self._btn_reset = QPushButton("重置")
        self._btn_reset.setFixedWidth(40)
        self._btn_reset.clicked.connect(self._reset_filters)
        filter_row2.addWidget(self._btn_reset)

        # 第三行：自动检测类型细分
        filter_row3 = QHBoxLayout()
        filter_row3.setContentsMargins(0, 0, 0, 2)
        self._cb_duplicate = QCheckBox("重复")
        self._cb_similar   = QCheckBox("相似")
        for cb in (self._cb_duplicate, self._cb_similar):
            cb.setStyleSheet("font-size: 11px;")
            cb.stateChanged.connect(self._on_filter_changed)
        filter_row3.addWidget(self._cb_duplicate)
        filter_row3.addWidget(self._cb_similar)
        filter_row3.addStretch()

        # ── 问题列表 ──────────────────────────────────────────
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_double_click)

        # ── 底部按钮行 ─────────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 2, 0, 0)
        self._btn_bulk = QPushButton("批量改写  Ctrl+R")
        self._btn_bulk.setFixedWidth(120)
        self._lbl_progress = QLabel("")
        self._lbl_progress.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        bottom_row.addWidget(self._btn_bulk)
        bottom_row.addWidget(self._lbl_progress)
        bottom_row.addStretch()

        # ── 组装 ────────────────────────────────────────────────
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(2, 2, 2, 2)
        vbox.setSpacing(4)
        vbox.addLayout(title_row)
        vbox.addLayout(filter_row1)
        vbox.addLayout(filter_row2)
        vbox.addLayout(filter_row3)
        vbox.addWidget(self._list, 1)
        vbox.addLayout(bottom_row)

        self._btn_export.clicked.connect(self._export)
        self._btn_bulk.clicked.connect(self._request_bulk_rewrite)

    # ── public API ──────────────────────────────────────────────
    def refresh(self, manual: Dict[int, Dict],
                auto_violations: Dict[int, List[Violation]]):
        self._manual = manual
        self._auto   = auto_violations
        self._rebuild()

    def set_pending_rewrite_indices(self, indices: List[int]):
        """由主窗口注入当前序列的批量改写候选帧号列表。"""
        self._pending_rewrite = sorted(set(indices))

    def update_rewrite_progress(self, done: int, total: int):
        """由主窗口调用，实时更新批量改写进度标签。"""
        if total > 0:
            self._lbl_progress.setText(f"进度：{done}/{total}")
            if done >= total:
                self._lbl_progress.setText(f"完成 {done}/{total}")
        else:
            self._lbl_progress.setText("")

    # ── internal ────────────────────────────────────────────────
    FILTER_CB_MAP = {
        "HALLUCINATION": "_cb_hall",
        "GRAMMAR":      "_cb_grammar",
        "VISUAL":       "_cb_visual",
        "OTHER":        "_cb_other",
        "MODIFIED":     "_cb_modified",
        "AI_GENERATED": "_cb_ai",
        "DUPLICATE":    "_cb_duplicate",
        "SIMILAR":      "_cb_similar",
        "error":        "_cb_errors",
        "warning":      "_cb_warnings",
    }

    def _on_filter_changed(self):
        """收集所有选中 CheckBox，构建 active_filters 并刷新列表。"""
        filters: Set[str] = set()
        for ftype, attr in self.FILTER_CB_MAP.items():
            cb = getattr(self, attr, None)
            if cb is not None and cb.isChecked():
                filters.add(ftype)
        self._active_filters = filters
        self.filter_changed.emit(filters)
        self._rebuild()

    def _reset_filters(self):
        for attr in self.FILTER_CB_MAP.values():
            cb = getattr(self, attr, None)
            if cb is not None:
                cb.setChecked(False)
        self._active_filters.clear()
        self.filter_changed.emit(set())
        self._rebuild()

    def _rebuild(self):
        self._list.clear()
        has_filter = bool(self._active_filters)

        all_items: List[tuple] = []   # (sort_key, display_text, color, idx)

        # ── 手动标记 ──────────────────────────────────────────
        for idx in sorted(self._manual.keys()):
            info  = self._manual[idx]
            ftype = info.get("type", "OTHER")
            note  = info.get("note", "")

            if has_filter:
                # 精确类型匹配
                if ftype not in self._active_filters:
                    continue

            label = _MANUAL_LABELS.get(ftype, ftype)
            text  = f"  第 {idx + 1} 帧  [{label}]"
            if note:
                text += f"  {note[:40]}"
            color = _TYPE_COLORS.get(ftype, QColor(120, 120, 120))
            # sort_key: (0 = manual, ftype, idx)
            all_items.append(( (0, ftype, idx), text, color, idx ))

        # ── 自动违规 ─────────────────────────────────────────
        for idx in sorted(self._auto.keys()):
            viols = self._auto[idx]
            if not viols:
                continue
            top_sev = max(viols, key=lambda v: v.severity == "error")
            vtype   = top_sev.vtype
            sev_key = top_sev.severity   # "error" or "warning"

            if has_filter:
                # 同时检查精确类型和严重级别
                type_ok  = vtype in self._active_filters
                sev_ok   = sev_key in self._active_filters
                if not (type_ok or sev_ok):
                    continue

            label = _AUTO_LABELS.get(vtype, vtype)
            text  = (f"  第 {idx + 1} 帧  [{label}]  "
                     f"{top_sev.detail[:30]}")
            color = _TYPE_COLORS.get(vtype, QColor(150, 150, 150))
            # sort_key: (1 = auto, severity, vtype, idx)
            all_items.append(( (1, sev_key, vtype, idx), text, color, idx ))

        # ── 渲染 ─────────────────────────────────────────────
        if not all_items:
            item = QListWidgetItem("  （无匹配项）")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(QColor(100, 100, 100))
            self._list.addItem(item)
        else:
            for sort_key, text, color, idx in all_items:
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, idx)
                item.setForeground(color)
                self._list.addItem(item)

        # 更新标题计数
        total_m = len([x for x in all_items if x[0][0] == 0])
        total_a = len([x for x in all_items if x[0][0] == 1])
        self._lbl_title.setText(
            f"<b>问题列表（{total_m}标记 / {total_a}检测）</b>")

    def _on_double_click(self, item: QListWidgetItem):
        idx = item.data(Qt.UserRole)
        if idx is not None:
            self.frame_requested.emit(int(idx))

    def _request_bulk_rewrite(self):
        if not self._pending_rewrite:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "无内容",
                                   "当前序列中没有可批量改写的帧（幻觉/重复/相似）。")
            return
        self.bulk_rewrite_requested.emit(list(self._pending_rewrite))

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
                str(idx): [{"type": v.vtype, "severity": v.severity,
                            "detail": v.detail}
                           for v in viols]
                for idx, viols in self._auto.items()
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "导出成功", f"报告已保存至：\n{path}")
