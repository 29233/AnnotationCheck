import os
from typing import Optional, List

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QMainWindow, QWidget, QSplitter, QVBoxLayout,
                              QHBoxLayout, QToolBar, QStatusBar, QAction,
                              QFileDialog, QMessageBox, QShortcut, QLabel,
                              QDockWidget, QMenuBar, QMenu, QLineEdit,
                              QDialog, QGridLayout, QDialogButtonBox)

from core.config_manager     import ConfigManager
from core.sequence_loader    import SequenceLoader, SequenceInfo
from core.annotation_manager import AnnotationManager
from core.annotation_validator import AnnotationValidator
from core.review_manager     import ReviewManager, STATUS_IN_PROGRESS, STATUS_DONE

from ui.image_panel    import ImagePanel
from ui.nav_bar        import NavBar
from ui.text_panel     import TextPanel
from ui.sequence_panel import SequencePanel
from ui.flag_panel     import FlagPanel
from ui.flag_dialog    import FlagDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("标注审核工具")
        self.resize(1400, 900)

        # ── core objects ──────────────────────────────────
        self.config    = ConfigManager()
        self.ann_mgr   = AnnotationManager()
        self.validator = AnnotationValidator()
        self.loader:   Optional[SequenceLoader]  = None
        self.review:   Optional[ReviewManager]   = None
        self.seq_info: Optional[SequenceInfo]    = None

        self._current_frame = 0
        self._violations: dict = {}          # cached full validation result
        self._violation_indices: List[int] = []
        self._viol_cursor = -1

        # ── build UI ──────────────────────────────────────
        self._build_toolbar()
        self._build_central()
        self._build_docks()
        self._build_statusbar()
        self._build_shortcuts()
        self._build_menubar()
        self._check_first_launch()

        # ── auto-save timer ───────────────────────────────
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save)
        interval = self.config.get("auto_save_interval", 180) * 1000
        self._auto_save_timer.start(interval)

        # ── restore last session ──────────────────────────
        last_root = self.config.get("last_data_root", "")
        if last_root and os.path.isdir(last_root):
            self._open_root(last_root)
            last_seq = self.config.get("last_sequence", "")
            if last_seq:
                self._load_sequence(last_seq)

    # ═══════════════════════════════════════ UI builders
    def _build_toolbar(self):
        tb = QToolBar("主工具栏", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        self._act_open   = QAction("打开数据集", self)
        self._act_save   = QAction("保存  Ctrl+S", self)
        self._act_toggle = QAction("切换模态  Tab", self)
        self._act_flag   = QAction("标记帧  F", self)
        self._act_done   = QAction("标记完成", self)

        tb.addAction(self._act_open)
        tb.addAction(self._act_save)
        tb.addSeparator()
        tb.addAction(self._act_toggle)
        tb.addSeparator()
        tb.addAction(self._act_flag)
        tb.addAction(self._act_done)

        self._act_open.triggered.connect(self._on_open)
        self._act_save.triggered.connect(self._save)
        self._act_toggle.triggered.connect(self._toggle_modal)
        self._act_flag.triggered.connect(self._flag_current_frame)
        self._act_done.triggered.connect(self._mark_done)

    def _build_central(self):
        # top-level horizontal splitter: [image+nav] | [text]
        self._main_splitter = QSplitter(Qt.Horizontal)

        # ── left: image + nav ────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        self.image_panel = ImagePanel()
        self.nav_bar     = NavBar()
        left_layout.addWidget(self.image_panel)
        left_layout.addWidget(self.nav_bar)
        left.setMinimumWidth(300)

        # ── right: text panel ────────────────────────────
        self.text_panel = TextPanel()
        self.text_panel.set_config_manager(self.config)
        self.text_panel.set_annotation_manager(self.ann_mgr)

        self._main_splitter.addWidget(left)
        self._main_splitter.addWidget(self.text_panel)
        self._main_splitter.setSizes([700, 700])

        self.setCentralWidget(self._main_splitter)

        # ── connections ──────────────────────────────────
        self.nav_bar.frame_requested.connect(self._go_to_frame)
        self.nav_bar.prev_violation_requested.connect(self._prev_violation)
        self.nav_bar.next_violation_requested.connect(self._next_violation)
        self.text_panel.frame_requested.connect(self._go_to_frame)
        self.text_panel.line_edited.connect(self._on_line_edited)

    def _build_docks(self):
        # ── sequence list (left dock) ─────────────────────
        self.seq_panel = SequencePanel()
        seq_dock = QDockWidget("序列列表", self)
        seq_dock.setWidget(self.seq_panel)
        seq_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, seq_dock)
        self.seq_panel.sequence_selected.connect(self._load_sequence)

        # ── flag/issue panel (right dock) ─────────────────
        self.flag_panel = FlagPanel()
        flag_dock = QDockWidget("问题列表", self)
        flag_dock.setWidget(self.flag_panel)
        flag_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, flag_dock)
        self.flag_panel.frame_requested.connect(self._go_to_frame)

    def _build_statusbar(self):
        self._sb = QStatusBar(self)
        self.setStatusBar(self._sb)
        self._lbl_seq    = QLabel("")
        self._lbl_frame  = QLabel("")
        self._lbl_diff   = QLabel("")
        self._lbl_viols  = QLabel("")
        self._lbl_flags  = QLabel("")
        self._lbl_saved  = QLabel("未加载文件")
        for lbl in (self._lbl_seq, self._lbl_frame, self._lbl_diff,
                    self._lbl_viols, self._lbl_flags, self._lbl_saved):
            self._sb.addPermanentWidget(lbl)
            self._sb.addPermanentWidget(QLabel("  |  "))

    def _build_shortcuts(self):
        def sc(key, fn):
            QShortcut(QKeySequence(key), self).activated.connect(fn)

        sc("Right", lambda: self._go_to_frame(self._current_frame + 1))
        sc("Left",  lambda: self._go_to_frame(self._current_frame - 1))
        sc("D",     lambda: self._go_to_frame(self._current_frame + 1))
        sc("A",     lambda: self._go_to_frame(self._current_frame - 1))
        sc("Ctrl+Right", lambda: self._go_to_frame(self._current_frame + 10))
        sc("Ctrl+Left",  lambda: self._go_to_frame(self._current_frame - 10))
        sc("Home",  lambda: self._go_to_frame(0))
        sc("End",   lambda: self._go_to_frame(self.seq_info.frame_count - 1
                                               if self.seq_info else 0))
        sc("Tab",   self._toggle_modal)
        sc("Ctrl+S", self._save)
        sc("Ctrl+Z", self._undo)
        sc("Ctrl+Y", self._redo)
        sc("Ctrl+F", self.text_panel.focus_search)
        sc("F",      self._flag_current_frame)
        sc("[",      self._prev_flag)
        sc("]",      self._next_flag)
        sc("Ctrl+[", self._prev_violation)
        sc("Ctrl+]", self._next_violation)

    def _build_menubar(self):
        mb = self.menuBar()

        # ── 配置 ───────────────────────────────────────────────────────
        config_menu = mb.addMenu("配置")

        sdk_action = QAction("阿里云 SDK 设置…", self)
        sdk_action.triggered.connect(self._show_sdk_config_dialog)
        config_menu.addAction(sdk_action)

        # ── 帮助 ───────────────────────────────────────────────────────
        help_menu = mb.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ── config dialog ────────────────────────────────────────────────
    def _show_sdk_config_dialog(self):
        ak, sk = self.config.get_aliyun_credentials()
        dlg = _SDKConfigDialog(ak, sk, self)
        if dlg.exec_() == _SDKConfigDialog.Accepted:
            self.config.set_aliyun_credentials(dlg.ak, dlg.sk)
            # sync to env so background threads see new credentials
            os.environ["ALIYUN_ACCESS_KEY_ID"] = dlg.ak
            os.environ["ALIYUN_ACCESS_KEY_SECRET"] = dlg.sk
            QMessageBox.information(self, "设置已保存",
                                   "阿里云 SDK 凭证已保存。")

    def _show_about(self):
        QMessageBox.about(self, "关于",
                          "标注审核工具 v1.0\n\n"
                          "双模态（可见光+红外光）图像序列标注审核工具。")

    # ── first-launch check ──────────────────────────────────────────
    def _check_first_launch(self):
        if not self.config.get("sdk_configured", False):
            QTimer.singleShot(500, self._show_sdk_config_dialog)

    # ═══════════════════════════════════════ open / load
    def _on_open(self):
        root = QFileDialog.getExistingDirectory(
            self, "选择 data/ 根目录",
            self.config.get("last_data_root", ""))
        if root:
            self._open_root(root)

    def _open_root(self, root: str):
        self.loader = SequenceLoader(root)
        self.review = ReviewManager(root)
        self.config.set("last_data_root", root)
        seqs     = self.loader.list_sequences()
        progress = self.review.all_progress()
        self.seq_panel.set_sequences(seqs, progress)

    def _load_sequence(self, seq_name: str):
        if not self.loader:
            return
        # prompt save if dirty
        if not self._prompt_save():
            return

        # save last position for previous sequence
        if self.seq_info and self.review:
            self._persist_progress()

        self.seq_info = self.loader.load_sequence(seq_name)
        self.review.load_sequence(seq_name)
        self.config.set("last_sequence", seq_name)

        # load annotation
        self.ann_mgr.clear()
        if self.seq_info.has_text:
            self.ann_mgr.load(self.seq_info.text_path)
        else:
            QMessageBox.warning(self, "缺失标注文件",
                                f"未找到序列 '{seq_name}' 对应的标注文件。\n"
                                "请联系项目负责人。")

        # validate once and cache
        self._violations = self.validator.validate_all(self.ann_mgr.lines)
        self._cache_violation_indices(self._violations)

        # populate text panel
        self.text_panel.load(self.ann_mgr.lines, self._violations,
                             self.seq_info.frame_count)

        # navigation
        prog = self.review.get_progress(seq_name)
        start_frame = prog.get("last_frame", 0)
        self.nav_bar.setup(self.seq_info.frame_count)

        self._current_frame = -1   # force refresh
        self._go_to_frame(start_frame)

        # sidebar highlight
        self.seq_panel.highlight_current(seq_name)

        # flag panel
        self._refresh_flag_panel()

        # status bar
        self._update_status_bar()
        self.setWindowTitle(f"标注审核工具 — {seq_name}")

    # ═══════════════════════════════════════ frame navigation
    @pyqtSlot(int)
    def _go_to_frame(self, idx: int):
        if not self.seq_info:
            return
        idx = max(0, min(idx, self.seq_info.frame_count - 1))
        if idx == self._current_frame:
            return
        self._current_frame = idx

        vis = (self.seq_info.visible_paths[idx]
               if idx < len(self.seq_info.visible_paths) else None)
        inf = (self.seq_info.infrared_paths[idx]
               if idx < len(self.seq_info.infrared_paths) else None)
        self.image_panel.set_frame(vis, inf, idx)

        # use cached violations for border color
        frame_viols = self._violations.get(idx, [])
        if any(v.severity == "error" for v in frame_viols):
            self.image_panel.set_violation_border("error")
        elif any(v.severity == "warning" for v in frame_viols):
            self.image_panel.set_violation_border("warning")
        else:
            self.image_panel.set_violation_border(None)

        self.text_panel.set_current_frame(idx)
        self.nav_bar.set_frame(idx)
        self._update_status_bar()

    def _prev_violation(self):
        if not self._violation_indices:
            return
        cur = self._current_frame
        prev_list = [i for i in self._violation_indices if i < cur]
        if prev_list:
            self._go_to_frame(prev_list[-1])

    def _next_violation(self):
        if not self._violation_indices:
            return
        cur = self._current_frame
        next_list = [i for i in self._violation_indices if i > cur]
        if next_list:
            self._go_to_frame(next_list[0])

    def _prev_flag(self):
        if not self.review:
            return
        idxs = self.review.flagged_indices()
        prev = [i for i in idxs if i < self._current_frame]
        if prev:
            self._go_to_frame(prev[-1])

    def _next_flag(self):
        if not self.review:
            return
        idxs = self.review.flagged_indices()
        nxt = [i for i in idxs if i > self._current_frame]
        if nxt:
            self._go_to_frame(nxt[0])

    # ═══════════════════════════════════════ editing
    @pyqtSlot(int, str)
    def _on_line_edited(self, idx: int, new_text: str):
        if not self.ann_mgr.lines:
            return
        self.ann_mgr.set_line(idx, new_text)
        # revalidate and cache
        self._violations = self.validator.validate_all(self.ann_mgr.lines)
        self._cache_violation_indices(self._violations)
        self.text_panel.update_violations(self._violations)
        # refresh border for current frame
        frame_viols = self._violations.get(self._current_frame, [])
        if any(v.severity == "error" for v in frame_viols):
            self.image_panel.set_violation_border("error")
        elif any(v.severity == "warning" for v in frame_viols):
            self.image_panel.set_violation_border("warning")
        else:
            self.image_panel.set_violation_border(None)
        self._refresh_flag_panel()
        self._update_status_bar()
        self._flash_saved("已编辑 — 未保存")

    def _undo(self):
        if self.ann_mgr.undo():
            self._after_undo_redo()

    def _redo(self):
        if self.ann_mgr.redo():
            self._after_undo_redo()

    def _after_undo_redo(self):
        self._violations = self.validator.validate_all(self.ann_mgr.lines)
        self._cache_violation_indices(self._violations)
        self.text_panel.reload_all(self.ann_mgr.lines, self._violations)
        self._refresh_flag_panel()
        self._update_status_bar()

    # ═══════════════════════════════════════ save
    def _save(self):
        if not self.ann_mgr.text_path:
            return
        if self.ann_mgr.save():
            self._flash_saved("已保存 ✓")
        self._persist_progress()

    def _auto_save(self):
        if self.ann_mgr.modified and self.ann_mgr.text_path:
            if self.config.get("auto_save_enabled", True):
                self.ann_mgr.save()

    def _prompt_save(self) -> bool:
        """返回 True 表示可以继续（已保存或已放弃）。"""
        if not self.ann_mgr.modified:
            return True
        resp = QMessageBox.question(
            self, "未保存的更改",
            "当前有未保存的更改，切换前是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if resp == QMessageBox.Save:
            self._save()
            return True
        if resp == QMessageBox.Discard:
            return True
        return False   # Cancel

    # ═══════════════════════════════════════ flags / marking
    def _flag_current_frame(self):
        if not self.review or not self.seq_info:
            return
        existing = self.review.get_flag(self._current_frame) or {}
        dlg = FlagDialog(self._current_frame, existing, self)
        if dlg.exec_() != FlagDialog.Accepted:
            return
        if dlg.removed:
            self.review.remove_flag(self._current_frame)
        else:
            self.review.add_flag(self._current_frame, dlg.flag_type, dlg.note)
        self._refresh_flag_panel()
        self._update_status_bar()

    def _mark_done(self):
        if not self.seq_info or not self.review:
            return
        # warn if there are still error-level violations
        errors = sum(1 for v in self._violations.values()
                     for vv in v if vv.severity == "error")
        if errors:
            resp = QMessageBox.question(
                self, "存在未解决的错误",
                f"仍有 {errors} 个错误级违规未处理。\n"
                "仍然标记为完成吗？",
                QMessageBox.Yes | QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
        self._persist_progress(status=STATUS_DONE)
        QMessageBox.information(self, "已完成",
                                f"序列 '{self.seq_info.name}' 已标记为完成。")
        self.seq_panel.refresh_item(
            self.seq_info.name,
            self.review.get_progress(self.seq_info.name))

    # ═══════════════════════════════════════ helpers
    def _toggle_modal(self):
        self.image_panel.toggle_mode()

    def _persist_progress(self, status: str = STATUS_IN_PROGRESS):
        if not (self.review and self.seq_info):
            return
        vcount = sum(1 for v in self._violations.values() if v)
        fcount = len(self.review.flagged_indices())
        self.review.update_progress(
            self.seq_info.name, status,
            self._current_frame, vcount, fcount)

    def _cache_violation_indices(self, violations: dict):
        self._violation_indices = sorted(violations.keys())

    def _refresh_flag_panel(self):
        if not self.review:
            return
        self.flag_panel.refresh(self.review.all_flags(), self._violations)

    def _update_status_bar(self):
        if not self.seq_info:
            return
        name   = self.seq_info.name
        total  = self.seq_info.frame_count
        f      = self._current_frame + 1
        diff   = self.seq_info.line_frame_diff
        diff_s = (f"<font color='red'>行帧差: {diff:+d}</font>"
                  if diff != 0 else "行帧差: 0")
        viols  = len(self._violation_indices)
        flags  = len(self.review.flagged_indices()) if self.review else 0
        self._lbl_seq.setText(f"<b>{name}</b>")
        self._lbl_frame.setText(f"第 {f} / {total} 帧")
        self._lbl_diff.setText(diff_s)
        self._lbl_viols.setText(f"违规: {viols}")
        self._lbl_flags.setText(f"标记: {flags}")

    def _flash_saved(self, msg: str):
        self._lbl_saved.setText(msg)
        QTimer.singleShot(3000, lambda: self._lbl_saved.setText(
            "已保存 ✓" if not self.ann_mgr.modified else "未保存"))

    # ═══════════════════════════════════════ close
    def closeEvent(self, event):
        if not self._prompt_save():
            event.ignore()
            return
        self._persist_progress()
        self.config.set("layout_mode",
                        self.image_panel._mode)
        self.config.set("splitter_ratio",
                        self.image_panel.splitter_sizes())
        event.accept()


# ═══════════════════════════════════════════════════════════ SDK config dialog
class _SDKConfigDialog(QDialog):
    def __init__(self, ak: str, sk: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("阿里云 SDK 凭证配置")
        self.ak = ak
        self.sk = sk

        lbl_inst = QLabel("请输入阿里云 Access Key 凭证：\n"
                          "获取地址：https://ram.console.aliyun.com/manage/ak")
        self._le_ak = QLineEdit(ak)
        self._le_ak.setPlaceholderText("Access Key ID")
        self._le_sk = QLineEdit(sk)
        self._le_sk.setPlaceholderText("Access Key Secret")
        self._le_sk.setEchoMode(QLineEdit.Password)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        lay = QGridLayout(self)
        lay.addWidget(lbl_inst, 0, 0, 1, 2)
        lay.addWidget(QLabel("Access Key ID:"), 1, 0)
        lay.addWidget(self._le_ak, 1, 1)
        lay.addWidget(QLabel("Access Key Secret:"), 2, 0)
        lay.addWidget(self._le_sk, 2, 1)
        lay.addWidget(buttons, 3, 0, 1, 2)

    def _on_ok(self):
        self.ak = self._le_ak.text().strip()
        self.sk = self._le_sk.text().strip()
        if not self.ak or not self.sk:
            QMessageBox.warning(self, "错误", "AK/SK 不能为空。")
            return
        self.accept()
