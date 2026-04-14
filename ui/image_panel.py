from typing import Optional

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPen
from PyQt5.QtWidgets import QWidget, QSplitter, QVBoxLayout, QSizePolicy, QDialog

from core.image_loader import load_pixmap


# ─────────────────────────────────────────────── single image view
class ImageView(QWidget):
    """One image pane: zoom (Ctrl+wheel), pan (drag), frame-number overlay."""

    double_clicked = pyqtSignal()

    def __init__(self, modal_label: str, parent=None):
        super().__init__(parent)
        self.modal_label = modal_label
        self._pixmap: Optional[QPixmap] = None
        self._frame_idx = -1
        self._zoom = 1.0
        self._offset = QPoint(0, 0)
        self._drag_start: Optional[QPoint] = None
        self._drag_offset: Optional[QPoint] = None
        self._border_color: Optional[QColor] = None
        self.setMinimumSize(120, 80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    # ── public API ──────────────────────────────────────────────
    def set_image(self, path: Optional[str], frame_idx: int):
        self._frame_idx = frame_idx
        if path:
            self._pixmap, _, _ = load_pixmap(path)
        else:
            self._pixmap = None
        self.update()

    def set_pixmap(self, pixmap: Optional[QPixmap], frame_idx: int):
        self._pixmap = pixmap
        self._frame_idx = frame_idx
        self.update()

    def set_border_color(self, color: Optional[QColor]):
        self._border_color = color
        self.update()

    def reset_view(self):
        self._zoom = 1.0
        self._offset = QPoint(0, 0)
        self.update()

    # ── paint ────────────────────────────────────────────────────
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if self._pixmap and not self._pixmap.isNull():
            pw, ph = self._pixmap.width(), self._pixmap.height()
            scale = min(self.width() / pw, self.height() / ph) * self._zoom
            dw = int(pw * scale)
            dh = int(ph * scale)
            dx = (self.width() - dw) // 2 + self._offset.x()
            dy = (self.height() - dh) // 2 + self._offset.y()
            painter.drawPixmap(dx, dy, dw, dh, self._pixmap)

            # frame-number badge
            if self._frame_idx >= 0:
                text = f"{self.modal_label}  第 {self._frame_idx + 1} 帧"
                font = QFont("Consolas", 9)
                painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.width(text)
                th = fm.height()
                tx, ty = 8, self.height() - 8
                painter.fillRect(tx - 3, ty - th - 1, tw + 8, th + 4,
                                  QColor(0, 0, 0, 170))
                painter.setPen(QColor(230, 230, 230))
                painter.drawText(tx, ty, text)

        # violation border
        if self._border_color:
            pen = QPen(self._border_color, 3)
            painter.setPen(pen)
            painter.drawRect(2, 2, self.width() - 4, self.height() - 4)

        painter.end()

    # ── mouse ────────────────────────────────────────────────────
    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
            self._zoom = max(0.1, min(20.0, self._zoom * factor))
            self.update()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self._drag_offset = QPoint(self._offset)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None:
            self._offset = self._drag_offset + (event.pos() - self._drag_start)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = None

    def mouseDoubleClickEvent(self, _event):
        self.double_clicked.emit()


# ─────────────────────────────────────────────── fullscreen dialog
class _FullscreenDialog(QDialog):
    """Frameless fullscreen preview; closed by Escape or double-click."""

    def __init__(self, pixmap: QPixmap, frame_idx: int, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self._view = ImageView("", self)
        self._view.set_pixmap(pixmap, frame_idx)
        self._view.double_clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


# ─────────────────────────────────────────────── dual-modal panel
class ImagePanel(QWidget):
    """Left panel: two ImageView widgets in a vertical QSplitter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "A"   # A = visible main (top), B = infrared main (top)

        self.view_top = ImageView("可见光", self)
        self.view_bot = ImageView("红外光", self)

        self._splitter = QSplitter(Qt.Vertical, self)
        self._splitter.addWidget(self.view_top)
        self._splitter.addWidget(self.view_bot)
        self._splitter.setSizes([700, 300])
        self._splitter.setHandleWidth(4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)

        self.view_top.double_clicked.connect(self._open_fullscreen_top)
        self.view_bot.double_clicked.connect(self._open_fullscreen_bot)

    # ── public API ──────────────────────────────────────────────
    def set_frame(self, vis_path: Optional[str], inf_path: Optional[str], frame_idx: int):
        if self._mode == "A":
            self.view_top.set_image(vis_path, frame_idx)
            self.view_bot.set_image(inf_path, frame_idx)
            self.view_top.modal_label = "可见光"
            self.view_bot.modal_label = "红外光"
        else:
            self.view_top.set_image(inf_path, frame_idx)
            self.view_bot.set_image(vis_path, frame_idx)
            self.view_top.modal_label = "红外光"
            self.view_bot.modal_label = "可见光"

    def toggle_mode(self):
        """Swap which modality occupies the main (top/large) pane."""
        self._mode = "B" if self._mode == "A" else "A"
        # swap sizes
        sizes = self._splitter.sizes()
        self._splitter.setSizes(list(reversed(sizes)))

    def set_violation_border(self, severity: Optional[str]):
        """severity: 'error' | 'warning' | None"""
        if severity == "error":
            color = QColor(220, 50, 50)
        elif severity == "warning":
            color = QColor(220, 140, 30)
        else:
            color = None
        self.view_top.set_border_color(color)
        self.view_bot.set_border_color(color)

    def splitter_sizes(self):
        return self._splitter.sizes()

    def set_splitter_sizes(self, sizes):
        self._splitter.setSizes(sizes)

    # ── full-screen preview ──────────────────────────────────────
    def _open_fullscreen_top(self):
        self._show_fullscreen(self.view_top._pixmap, self.view_top._frame_idx)

    def _open_fullscreen_bot(self):
        self._show_fullscreen(self.view_bot._pixmap, self.view_bot._frame_idx)

    @staticmethod
    def _show_fullscreen(pixmap: Optional[QPixmap], frame_idx: int):
        if not pixmap:
            return
        dlg = _FullscreenDialog(pixmap, frame_idx)
        dlg.exec_()
