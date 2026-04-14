"""
Text annotation panel with English editing pane (top) and
Chinese translation pane (bottom), plus scrollable annotation list.
"""
import os
import re
import threading
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont, QBrush
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QTableWidget, QTableWidgetItem, QLabel,
                              QTextEdit, QPushButton, QHeaderView,
                              QAbstractItemView, QLineEdit)

# violation-type → base colour
_VIOL_COLORS: Dict[str, QColor] = {
    "OVER_LIMIT": QColor(200,  50,  50),
    "OVER_WARN":  QColor(210, 130,  30),
    "DUPLICATE":  QColor( 50, 100, 200),
    "SIMILAR":    QColor(180, 160,  30),
    "MIXED_LANG": QColor(140,  50, 180),
}
_CURRENT_BG = QColor(  0, 120, 200,  55)
_MISSING_BG = QColor(100, 100, 100,  80)


def _top_violation(viols: List) -> Optional:
    errors   = [v for v in viols if v.severity == "error"]
    warnings = [v for v in viols if v.severity == "warning"]
    if errors:   return errors[0]
    if warnings: return warnings[0]
    return None


def _detect_lang(text: str) -> str:
    """检测文本语言：含中文返回 'zh'，否则返回 'en'。"""
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    return "en"


class TextPanel(QWidget):
    """
    Right-side annotation panel.

    Layout (top → bottom):
      ┌─ header bar ────────────────────────────────────────────────────┐
      │  [frame badge]  [violation summary]                               │
      ├─ English preview pane (~25 % height) ────────────────────────────┤
      │  multi-line editor for current frame's English annotation;        │
      │  coloured left-border reflecting violation severity                │
      ├─ Chinese translation pane (~25 % height) ─────────────────────────┤
      │  read-only display of the Chinese translation;                    │
      │  "翻译中…" while loading, shows result when ready                │
      ├─ ctrl row ───────────────────────────────────────────────────────┤
      │  [word count] [翻译] [prev][next] [save] [cancel]                 │
      ├─ annotation list table ─────────────────────────────────────────┤
      │  # | Annotation | Words   (24 px rows, scrollable)              │
      ├─ search bar ────────────────────────────────────────────────────┤
      │  [search input]  [▲][▼] [match count]                           │
      └─────────────────────────────────────────────────────────────────┘

    Signals
    -------
    frame_requested(int)  – user clicked a table row to jump to a frame
    line_edited(int, str) – user saved an edited line
    """

    frame_requested = pyqtSignal(int)
    line_edited     = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines:       List[str] = []
        self._violations: Dict[int, List] = {}
        self._current_frame = -1
        self._frame_count   = 0
        self._updating    = False
        self._match_rows: List[int] = []
        self._match_cursor = -1

        # ConfigManager reference (set via set_config_manager)
        self._config = None
        # AnnotationManager reference (set via set_annotation_manager)
        self._ann_mgr = None

        # in-memory cache backed by ann_mgr.translations (frame_idx → text)
        self._trans_cache: Dict[int, str] = {}
        # frames currently being translated (avoid duplicate requests)
        self._trans_pending: set = set()

        self._build_ui()

    def set_config_manager(self, config):
        """由 MainWindow 调用，注入 ConfigManager 以读取阿里云凭证。"""
        self._config = config

    def set_annotation_manager(self, ann_mgr):
        """由 MainWindow 调用，注入 AnnotationManager 以持久化译文。"""
        self._ann_mgr = ann_mgr
        # populate in-memory cache from disk store
        if ann_mgr is not None:
            self._trans_cache = dict(ann_mgr.translations)

    # ═══════════════════════════════════════════════════ UI construction
    def _build_ui(self):
        # ── header bar ─────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(6, 4, 6, 2)

        self._lbl_frame = QLabel("— / —")
        self._lbl_frame.setStyleSheet("font-weight: bold; color: #c0c0c0;")
        self._lbl_summary = QLabel("")

        header_row.addWidget(self._lbl_frame)
        header_row.addWidget(QLabel("  │  "))
        header_row.addWidget(self._lbl_summary, 1)

        # ── English preview pane (top, editable) ───────────────────────
        self._preview = QTextEdit()
        self._preview.setAcceptRichText(False)
        self._preview.setLineWrapMode(QTextEdit.WidgetWidth)
        self._preview.setFont(QFont("Consolas", 10))
        self._preview.setStyleSheet(_EDIT_STYLE("#333"))

        # ── Chinese translation pane (bottom, read-only) ────────────────
        self._trans_pane = QTextEdit()
        self._trans_pane.setReadOnly(True)
        self._trans_pane.setAcceptRichText(False)
        self._trans_pane.setLineWrapMode(QTextEdit.WidgetWidth)
        self._trans_pane.setFont(QFont("Microsoft YaHei", 10))
        self._trans_pane.setStyleSheet(_READONLY_STYLE("#333"))

        # ── ctrl row ────────────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(4, 2, 4, 0)
        self._lbl_wc = QLabel("0 词")
        self._lbl_wc.setStyleSheet("color: #a0a0a0;")
        self._btn_save = QPushButton("保存  Ctrl+↵")
        self._btn_cancel = QPushButton("取消")
        self._btn_prev_frame = QPushButton("◀ 上一帧")
        self._btn_next_frame = QPushButton("下一帧 ▶")
        for btn in (self._btn_save, self._btn_cancel,
                     self._btn_prev_frame, self._btn_next_frame):
            btn.setFixedHeight(22)
        self._btn_save.setFixedWidth(90)
        self._btn_cancel.setFixedWidth(70)

        # ── translate button ─────────────────────────────────────────────
        self._btn_translate = QPushButton("翻译")
        self._btn_translate.setFixedHeight(22)
        self._btn_translate.setFixedWidth(50)
        self._btn_translate.setToolTip("重新翻译当前帧（文本修改后需手动翻译）")
        self._lbl_trans_status = QLabel("")
        self._lbl_trans_status.setStyleSheet("color: #a0a0a0;")

        ctrl_row.addWidget(self._lbl_wc)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self._btn_translate)
        ctrl_row.addWidget(self._lbl_trans_status)
        ctrl_row.addSpacing(8)
        ctrl_row.addWidget(self._btn_prev_frame)
        ctrl_row.addWidget(self._btn_next_frame)
        ctrl_row.addSpacing(8)
        ctrl_row.addWidget(self._btn_save)
        ctrl_row.addWidget(self._btn_cancel)

        # ── annotation list table ──────────────────────────────────────
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "标注内容", "词数"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 42)
        self.table.setColumnWidth(2, 46)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setDefaultSectionSize(24)

        # ── search bar ─────────────────────────────────────────────────
        search_row = QHBoxLayout()
        search_row.setContentsMargins(4, 2, 4, 2)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索… (Ctrl+F)")
        self._btn_prev_match = QPushButton("▲")
        self._btn_next_match = QPushButton("▼")
        self._lbl_match_info = QLabel("")
        for b in (self._btn_prev_match, self._btn_next_match):
            b.setFixedWidth(26)
        search_row.addWidget(self._search_input)
        search_row.addWidget(self._btn_prev_match)
        search_row.addWidget(self._btn_next_match)
        search_row.addWidget(self._lbl_match_info)

        # ── assemble ───────────────────────────────────────────────────
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(2)
        vbox.addLayout(header_row)
        vbox.addWidget(self._preview, 2)    # stretch factor 2 → ~25%
        vbox.addWidget(self._trans_pane, 2)  # stretch factor 2 → ~25%
        vbox.addLayout(ctrl_row)
        vbox.addWidget(self.table, 3)       # stretch factor 3 → ~37%
        vbox.addLayout(search_row)

        # ── connections ────────────────────────────────────────────────
        self._btn_save.clicked.connect(self._apply_edit)
        self._btn_cancel.clicked.connect(self._cancel_edit)
        self._btn_prev_frame.clicked.connect(self._goto_prev)
        self._btn_next_frame.clicked.connect(self._goto_next)
        self._btn_translate.clicked.connect(self._translate_current)
        self._preview.textChanged.connect(self._on_preview_changed)

        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.entered.connect(self._on_table_hover)

        self._search_input.textChanged.connect(self._on_search_changed)
        self._btn_prev_match.clicked.connect(lambda: self._jump_match(-1))
        self._btn_next_match.clicked.connect(lambda: self._jump_match(1))

    # ════════════════════════════════════════════════════════ public API
    def load(self, lines: List[str], violations: Dict[int, List],
             frame_count: int):
        self._lines       = lines
        self._violations = violations
        self._frame_count = frame_count
        # re-populate cache from disk store (ann_mgr.translations already loaded)
        if self._ann_mgr is not None:
            self._trans_cache = dict(self._ann_mgr.translations)
        else:
            self._trans_cache.clear()
        self._trans_pending.clear()
        self._rebuild_table()
        self._update_preview(0)
        self._refresh_summary()

    def update_violations(self, violations: Dict[int, List]):
        self._violations = violations
        self._refresh_colors()
        self._refresh_summary()
        self._update_preview(self._current_frame)

    def update_line(self, idx: int, text: str, violations: Dict[int, List]):
        if 0 <= idx < len(self._lines):
            self._lines[idx] = text
        self._violations.update(violations)
        for k in list(self._violations.keys()):
            if k in violations and not violations[k]:
                del self._violations[k]
        self._refresh_row(idx)
        self._refresh_summary()
        self._update_preview(idx)

    def reload_all(self, lines: List[str], violations: Dict[int, List]):
        self._lines       = lines
        self._violations = violations
        if self._ann_mgr is not None:
            self._trans_cache = dict(self._ann_mgr.translations)
        else:
            self._trans_cache.clear()
        self._rebuild_table()
        self._update_preview(self._current_frame)

    def set_current_frame(self, idx: int):
        if self._current_frame == idx:
            return
        prev = self._current_frame
        self._current_frame = idx
        if 0 <= prev < self.table.rowCount():
            self._refresh_row(prev)
        if 0 <= idx < self.table.rowCount():
            self._refresh_row(idx)
            self._updating = True
            self.table.selectRow(idx)
            self.table.scrollTo(self.table.model().index(idx, 0))
            self._updating = False
        self._update_preview(idx)
        self._schedule_translate(idx)

    def focus_search(self):
        self._search_input.setFocus()
        self._search_input.selectAll()

    # ═════════════════════════════════════════════════════ internal helpers
    def _rebuild_table(self):
        self._updating = True
        self.table.setRowCount(0)
        n = max(len(self._lines), self._frame_count)
        self.table.setRowCount(n)
        for i in range(n):
            self._fill_row(i)
        self._updating = False
        if 0 <= self._current_frame < n:
            self.table.selectRow(self._current_frame)
            self.table.scrollTo(self.table.model().index(self._current_frame, 0))

    def _fill_row(self, i: int):
        text  = self._lines[i] if i < len(self._lines) else ""
        words = len(text.split()) if text else 0
        viols = self._violations.get(i, [])

        item_num  = QTableWidgetItem(str(i + 1))
        item_text = QTableWidgetItem(text)
        item_wc   = QTableWidgetItem(f"{words}w")

        item_num.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item_text.setTextAlignment(Qt.AlignLeft  | Qt.AlignVCenter)
        item_wc.setTextAlignment(Qt.AlignCenter)
        for item in (item_num, item_wc):
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)

        if i >= len(self._lines):
            item_text.setText("[missing]")
            item_text.setForeground(QBrush(QColor(150, 150, 150)))
            bg = _MISSING_BG
        else:
            bg = self._row_bg(i, viols)

        for item in (item_num, item_text, item_wc):
            item.setBackground(QBrush(bg))
            if i == self._current_frame:
                font = QFont()
                font.setBold(True)
                item.setFont(font)

        self.table.setItem(i, 0, item_num)
        self.table.setItem(i, 1, item_text)
        self.table.setItem(i, 2, item_wc)

    def _refresh_row(self, i: int):
        if 0 <= i < self.table.rowCount():
            self._fill_row(i)

    def _refresh_colors(self):
        for i in range(self.table.rowCount()):
            if i < len(self._lines):
                viols = self._violations.get(i, [])
                bg = self._row_bg(i, viols)
                for col in range(3):
                    item = self.table.item(i, col)
                    if item:
                        item.setBackground(QBrush(bg))

    def _row_bg(self, i: int, viols: List) -> QColor:
        if i == self._current_frame:
            return _CURRENT_BG
        top = _top_violation(viols)
        if top and top.vtype in _VIOL_COLORS:
            base = _VIOL_COLORS[top.vtype]
            return QColor(base.red(), base.green(), base.blue(), 60)
        return QColor(0, 0, 0, 0)

    def _refresh_summary(self):
        errors   = sum(1 for v in self._violations.values()
                       for vv in v if vv.severity == "error")
        warnings = sum(1 for v in self._violations.values()
                       for vv in v if vv.severity == "warning")
        parts = []
        if errors:
            parts.append(f"<font color='#e03030'>● {errors} 个错误</font>")
        if warnings:
            parts.append(f"<font color='#d47020'>● {warnings} 个警告</font>")
        self._lbl_summary.setText("  ".join(parts) if parts
                                   else "<font color='#40b040'>✓ 无违规</font>")

    # ── preview pane ────────────────────────────────────────────────
    def _update_preview(self, idx: int):
        """Update English preview and Chinese translation for the given frame."""
        self._updating = True
        if 0 <= idx < len(self._lines):
            text = self._lines[idx]
        else:
            text = ""
        self._preview.setPlainText(text)
        self._updating = False

        # word count
        wc = len(text.split()) if text.strip() else 0
        self._lbl_wc.setText(f"{wc} 词")

        # colour the left border by violation severity
        viols  = self._violations.get(idx, [])
        top    = _top_violation(viols)
        if top and top.severity == "error":
            border_color = "#e03030"
        elif top and top.severity == "warning":
            border_color = "#d47020"
        elif viols:
            border_color = "#808080"
        else:
            border_color = "#333"
        self._preview.setStyleSheet(_EDIT_STYLE(border_color))

        # frame label
        total = self._frame_count or "—"
        self._lbl_frame.setText(f"第 {idx + 1} / {total} 帧")

        # update word-count colour
        if wc > 30:
            self._lbl_wc.setStyleSheet("color: #e03030; font-weight: bold;")
        elif wc > 20:
            self._lbl_wc.setStyleSheet("color: #d47020; font-weight: bold;")
        else:
            self._lbl_wc.setStyleSheet("color: #a0a0a0;")

        # show cached translation if available
        if idx in self._trans_cache:
            self._trans_pane.setPlainText(self._trans_cache[idx])
            self._trans_pane.setStyleSheet(_READONLY_STYLE(border_color))
            self._lbl_trans_status.setText("<font color='#40b040'>✓ 已翻译</font>")
        else:
            self._trans_pane.setPlainText("")
            self._trans_pane.setStyleSheet(_READONLY_STYLE("#333"))
            self._lbl_trans_status.setText("")

    def _on_preview_changed(self):
        """Real-time word count as user types in the preview pane."""
        if self._updating:
            return
        text = self._preview.toPlainText()
        wc   = len(text.split()) if text.strip() else 0
        self._lbl_wc.setText(f"{wc} 词")
        if wc > 30:
            self._lbl_wc.setStyleSheet("color: #e03030; font-weight: bold;")
        elif wc > 20:
            self._lbl_wc.setStyleSheet("color: #d47020; font-weight: bold;")
        else:
            self._lbl_wc.setStyleSheet("color: #a0a0a0;")

    # ── translation core ─────────────────────────────────────────────
    def _get_credentials(self):
        """Return (ak, sk) from config or env vars."""
        if self._config is not None:
            ak, sk = self._config.get_aliyun_credentials()
            if ak.strip() and sk.strip():
                return ak, sk
        ak = os.environ.get("ALIYUN_ACCESS_KEY_ID", "").strip()
        sk = os.environ.get("ALIYUN_ACCESS_KEY_SECRET", "").strip()
        return ak, sk

    def _translate_async(self, idx: int, src_lang: str, tgt_lang: str, text: str):
        """
        Translate `text` (already detected as src_lang) from src_lang→tgt_lang
        in a background thread. On success stores result in both _trans_cache
        and ann_mgr, then updates UI via _on_translate_done.
        """
        if idx in self._trans_cache or idx in self._trans_pending:
            return
        if not text.strip():
            return

        ak, sk = self._get_credentials()
        if not ak or not sk:
            QTimer.singleShot(0, lambda: self._on_translate_error(idx, "未配置 AK/SK"))
            return

        self._trans_pending.add(idx)

        def worker():
            try:
                from alibabacloud_alimt20181012.client import Client
                from alibabacloud_alimt20181012.models import TranslateGeneralRequest
                from alibabacloud_tea_openapi.utils_models import Config

                config = Config(
                    access_key_id=ak,
                    access_key_secret=sk,
                    region_id="cn-hangzhou",
                    endpoint="mt.cn-hangzhou.aliyuncs.com",
                )
                client = Client(config)
                request = TranslateGeneralRequest(
                    source_text=text,
                    source_language=src_lang,
                    target_language=tgt_lang,
                    format_type="text",
                    scene="general",
                )
                resp = client.translate_general(request)
                body = resp.body
                data = getattr(body, "data", None)
                if data is None:
                    raise ValueError("响应 body.data 为空")
                translated = data.to_map().get("Translated", "")
                if not translated:
                    raise ValueError("译文为空")

                # store in both caches
                self._trans_cache[idx] = translated
                if self._ann_mgr is not None:
                    self._ann_mgr.set_translation(idx, translated)
                    self._ann_mgr.save_translations()

                QTimer.singleShot(0, lambda: self._on_translate_done(idx))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._on_translate_error(idx, str(e)))
            finally:
                self._trans_pending.discard(idx)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_translate_done(self, idx: int):
        """Called on the main thread when a translation succeeds."""
        if idx != self._current_frame:
            return
        if idx in self._trans_cache:
            border = self._get_border_color(idx)
            self._trans_pane.setPlainText(self._trans_cache[idx])
            self._trans_pane.setStyleSheet(_READONLY_STYLE(border))
            self._lbl_trans_status.setText("<font color='#40b040'>✓ 已翻译</font>")

    def _on_translate_error(self, idx: int, msg: str):
        """Called on the main thread when a translation fails."""
        if idx != self._current_frame:
            return
        self._lbl_trans_status.setText(
            f"<font color='#e03030'>翻译失败</font>")
        print(f"[翻译错误 frame {idx}] {msg}")

    def _get_border_color(self, idx: int) -> str:
        viols = self._violations.get(idx, [])
        top   = _top_violation(viols)
        if top and top.severity == "error":
            return "#e03030"
        elif top and top.severity == "warning":
            return "#d47020"
        elif viols:
            return "#808080"
        return "#333"

    # ── manual translate (button) ───────────────────────────────────
    def _translate_current(self):
        """手动翻译当前帧（清除缓存后强制重新请求）。"""
        idx = self._current_frame
        if idx < 0:
            return
        text = self._preview.toPlainText().strip()
        if not text:
            self._lbl_trans_status.setText(
                "<font color='#e03030'>原文为空</font>")
            return

        ak, sk = self._get_credentials()
        if not ak or not sk:
            self._lbl_trans_status.setText(
                "<font color='#e03030'>未配置 AK/SK</font>")
            return

        # invalidate cache for this frame
        self._trans_cache.pop(idx, None)
        self._trans_pending.discard(idx)
        self._lbl_trans_status.setText("<font color='#a0a0a0'>翻译中…</font>")
        self._btn_translate.setEnabled(False)

        src = _detect_lang(text)
        tgt = "en" if src == "zh" else "zh"
        self._translate_async(idx, src, tgt, text)
        # safety re-enable after 15s (prevents stuck disabled button on network error)
        QTimer.singleShot(15000, lambda: self._btn_translate.setEnabled(True))

    # ── auto translate on navigation ────────────────────────────────
    def _schedule_translate(self, idx: int):
        """Show cached translation immediately; dispatch async fetch for neighbours."""
        # Show "翻译中…" if no cached result yet
        if idx not in self._trans_cache:
            self._trans_pane.setPlainText("")
            self._trans_pane.setStyleSheet(_READONLY_STYLE("#333"))
            self._lbl_trans_status.setText("<font color='#a0a0a0'>翻译中…</font>")
            text = self._lines[idx] if idx < len(self._lines) else ""
            if text.strip():
                src = _detect_lang(text)
                tgt = "en" if src == "zh" else "zh"
                self._translate_async(idx, src, tgt, text.strip())

        # Prefetch ±1/±2/±3 neighbours (only if not already cached)
        for delta in (-3, -2, -1, 1, 2, 3):
            neighbour = idx + delta
            if 0 <= neighbour < self._frame_count:
                if neighbour not in self._trans_cache and neighbour not in self._trans_pending:
                    text = self._lines[neighbour] if neighbour < len(self._lines) else ""
                    if text.strip():
                        src = _detect_lang(text)
                        tgt = "en" if src == "zh" else "zh"
                        self._translate_async(neighbour, src, tgt, text.strip())

    # ── editing ─────────────────────────────────────────────────────
    def _apply_edit(self):
        row     = self._current_frame
        new_txt = self._preview.toPlainText().strip()
        if 0 <= row < len(self._lines):
            self.line_edited.emit(row, new_txt)

    def apply_pending_edit(self):
        """Commit preview edits to ann_mgr if the text has changed. Called by MainWindow before frame navigation."""
        if self._ann_mgr is None or self._current_frame < 0:
            return
        orig_lines = self._ann_mgr.lines
        if self._current_frame >= len(orig_lines):
            return
        new_txt = self._preview.toPlainText().strip()
        if new_txt != orig_lines[self._current_frame]:
            self._apply_edit()

    def _cancel_edit(self):
        self._update_preview(self._current_frame)

    def _goto_prev(self):
        self.frame_requested.emit(max(0, self._current_frame - 1))

    def _goto_next(self):
        self.frame_requested.emit(min(self._frame_count - 1, self._current_frame + 1))

    # ── table interaction ────────────────────────────────────────────
    def _on_cell_clicked(self, row: int, _col: int):
        if self._updating:
            return
        if 0 <= row < len(self._lines):
            if row != self._current_frame:
                self.frame_requested.emit(row)
            else:
                self._update_preview(row)

    def _on_double_click(self, row: int, _col: int):
        if 0 <= row < len(self._lines):
            self.frame_requested.emit(row)

    def _on_table_hover(self, index):
        pass

    # ── search ───────────────────────────────────────────────────────
    def _on_search_changed(self, text: str):
        self._match_rows  = []
        self._match_cursor = -1
        if not text.strip():
            self._lbl_match_info.setText("")
            return
        q = text.lower()
        for i, line in enumerate(self._lines):
            if q in line.lower():
                self._match_rows.append(i)
        count = len(self._match_rows)
        self._lbl_match_info.setText(f"{count} 个匹配")
        if self._match_rows:
            self._match_cursor = 0
            self._scroll_to_match()

    def _jump_match(self, direction: int):
        if not self._match_rows:
            return
        self._match_cursor = (self._match_cursor + direction) % len(self._match_rows)
        self._scroll_to_match()

    def _scroll_to_match(self):
        if 0 <= self._match_cursor < len(self._match_rows):
            row = self._match_rows[self._match_cursor]
            self.table.scrollTo(self.table.model().index(row, 0))
            self.table.selectRow(row)
            n = len(self._match_rows)
            self._lbl_match_info.setText(f"{self._match_cursor + 1}/{n}")


# ──────────────────────────────────────────────────────────────────── style helpers
def _EDIT_STYLE(border_color: str) -> str:
    return f"""
        QTextEdit {{
            background-color: #1e1e1e;
            color: #d4d4d4;
            border-left: 4px solid {border_color};
            border-top: 2px solid #333;
            border-right: 2px solid #333;
            border-bottom: 2px solid #333;
            border-radius: 4px;
            padding: 6px;
            font-family: Consolas;
            font-size: 10pt;
        }}
    """


def _READONLY_STYLE(border_color: str) -> str:
    return f"""
        QTextEdit {{
            background-color: #1a1a2e;
            color: #c8c8e0;
            border-left: 4px solid {border_color};
            border-top: 2px solid #333;
            border-right: 2px solid #333;
            border-bottom: 2px solid #333;
            border-radius: 4px;
            padding: 6px;
            font-family: Microsoft YaHei;
            font-size: 10pt;
        }}
    """
