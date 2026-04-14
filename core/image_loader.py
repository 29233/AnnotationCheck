"""
Image loading utilities.

Qt builds that lack the JPEG plugin (common in conda environments) cannot
use QPixmap(path) or QImage.fromData(jpeg_bytes) directly.
This module wraps Pillow to decode any image format and convert the result
to a QPixmap / QImage, completely bypassing Qt's built-in codec registry.
"""
from typing import Optional, Tuple
from io import BytesIO

from PIL import Image
from PyQt5.QtGui import QPixmap, QImage


def load_pixmap(path: str) -> Tuple[Optional[QPixmap], int, int]:
    """
    Load an image from *path* using Pillow and return a QPixmap.

    Returns
    -------
    (pixmap, width, height)
    pixmap may be None if loading fails.
    """
    try:
        pil_img = Image.open(path)
        w, h = pil_img.size

        # Convert to RGB (Qt does not handle RGBA->QPixmap well on all platforms)
        if pil_img.mode in ("RGBA", "P"):
            rgb = pil_img.convert("RGB")
        else:
            rgb = pil_img

        # Fast path: use PNG encoding as intermediate so Qt can decode it.
        # Qt's PNG codec is always available.
        buf = BytesIO()
        rgb.save(buf, format="PNG")
        buf.seek(0)
        qimg = QImage.fromData(buf.read())
        if qimg.isNull():
            # Fallback: raw RGB bytes → QImage
            bytes_data = rgb.tobytes()
            qimg = QImage(bytes_data, w, h, w * 3, QImage.Format_RGB888)

        if qimg.isNull():
            return None, 0, 0

        return QPixmap.fromImage(qimg), w, h

    except Exception:
        return None, 0, 0
