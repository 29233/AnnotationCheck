from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                              QSlider, QLabel, QSizePolicy)


class NavBar(QWidget):
    """帧导航栏：首帧 / 上一帧 / [当前帧/总帧数] / 下一帧 / 末帧 + 进度滑块"""

    frame_requested = pyqtSignal(int)   # 0-based
    prev_violation_requested = pyqtSignal()
    next_violation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total = 0
        self._current = 0
        self._updating = False

        # ── row 1: buttons + frame counter ──────────────────────
        self.btn_first    = QPushButton("|◀")
        self.btn_prev     = QPushButton("◀")
        self.lbl_frame   = QLabel("— / —")
        self.lbl_frame.setAlignment(Qt.AlignCenter)
        self.lbl_frame.setMinimumWidth(90)
        self.btn_next     = QPushButton("▶")
        self.btn_last     = QPushButton("▶|")

        self.btn_prev_viol = QPushButton("◀ 上一问题")
        self.btn_next_viol = QPushButton("下一问题 ▶")

        for btn in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last):
            btn.setFixedWidth(36)

        # ── row 2: slider ───────────────────────────────────────
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.setTracking(True)

        row1 = QHBoxLayout()
        row1.setContentsMargins(4, 2, 4, 0)
        row1.addWidget(self.btn_prev_viol)
        row1.addStretch()
        row1.addWidget(self.btn_first)
        row1.addWidget(self.btn_prev)
        row1.addWidget(self.lbl_frame)
        row1.addWidget(self.btn_next)
        row1.addWidget(self.btn_last)
        row1.addStretch()
        row1.addWidget(self.btn_next_viol)

        row2 = QHBoxLayout()
        row2.setContentsMargins(4, 0, 4, 2)
        row2.addWidget(self.slider)

        vbox = QVBoxLayout(self)
        vbox.setSpacing(2)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addLayout(row1)
        vbox.addLayout(row2)

        # ── connections ─────────────────────────────────────────
        self.btn_first.clicked.connect(lambda: self._go(0))
        self.btn_last.clicked.connect(lambda: self._go(self._total - 1))
        self.btn_prev.clicked.connect(lambda: self._go(self._current - 1))
        self.btn_next.clicked.connect(lambda: self._go(self._current + 1))
        self.slider.valueChanged.connect(self._slider_moved)
        self.btn_prev_viol.clicked.connect(self.prev_violation_requested)
        self.btn_next_viol.clicked.connect(self.next_violation_requested)

    # ── public API ───────────────────────────────────────────────
    def setup(self, total: int):
        self._total = total
        self._current = 0
        self._updating = True
        self.slider.setMaximum(max(0, total - 1))
        self.slider.setValue(0)
        self._updating = False
        self._refresh_label()
        self._update_buttons()

    def set_frame(self, idx: int):
        """程序跳转，不发射 frame_requested 信号"""
        self._current = max(0, min(idx, self._total - 1))
        self._updating = True
        self.slider.setValue(self._current)
        self._updating = False
        self._refresh_label()
        self._update_buttons()

    # ── internal ─────────────────────────────────────────────────
    def _go(self, idx: int):
        idx = max(0, min(idx, self._total - 1))
        if idx == self._current:
            return
        self._current = idx
        self.set_frame(idx)
        self.frame_requested.emit(idx)

    def _slider_moved(self, value: int):
        if self._updating:
            return
        self._go(value)

    def _refresh_label(self):
        if self._total == 0:
            self.lbl_frame.setText("— / —")
        else:
            self.lbl_frame.setText(f"{self._current + 1} / {self._total}")

    def _update_buttons(self):
        self.btn_first.setEnabled(self._current > 0)
        self.btn_prev.setEnabled(self._current > 0)
        self.btn_next.setEnabled(self._current < self._total - 1)
        self.btn_last.setEnabled(self._current < self._total - 1)
