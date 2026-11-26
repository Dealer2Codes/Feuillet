"""Éditeur de cadre : affiche l'image et quatre poignées déplaçables.

Les coins sont exprimés en pixels de l'image (pivotée) affichée, pour être
passés tels quels à ``PageSettings.corners``.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

HANDLE_RADIUS = 8.0


class CornerEditor(QWidget):
    cornersChanged = Signal(object)  # np.ndarray (4, 2) en pixels image

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._pixmap: QPixmap | None = None
        self._img_size = (1, 1)  # largeur, hauteur de l'image réelle
        self._corners: np.ndarray | None = None
        self._drag: int | None = None
        self.editable = True

    # ---- données
    def set_image(self, pixmap: QPixmap | None, image_size: tuple[int, int], corners: np.ndarray | None) -> None:
        self._pixmap = pixmap
        self._img_size = image_size
        self._corners = None if corners is None else np.array(corners, dtype=np.float32)
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._corners = None
        self.update()

    def corners(self) -> np.ndarray | None:
        return None if self._corners is None else self._corners.copy()

    # ---- repère
    def _target(self) -> QRectF:
        if not self._pixmap:
            return QRectF()
        w, h = self._img_size
        avail = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        scale = min(avail.width() / w, avail.height() / h)
        tw, th = w * scale, h * scale
        return QRectF(avail.x() + (avail.width() - tw) / 2, avail.y() + (avail.height() - th) / 2, tw, th)

    def _to_widget(self, pt) -> QPointF:
        t = self._target()
        return QPointF(t.x() + pt[0] / self._img_size[0] * t.width(), t.y() + pt[1] / self._img_size[1] * t.height())

    def _to_image(self, pos: QPointF) -> tuple[float, float]:
        t = self._target()
        x = (pos.x() - t.x()) / t.width() * self._img_size[0]
        y = (pos.y() - t.y()) / t.height() * self._img_size[1]
        return min(max(x, 0), self._img_size[0] - 1), min(max(y, 0), self._img_size[1] - 1)

    # ---- dessin
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.palette().window())
        if not self._pixmap:
            return
        target = self._target()
        p.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        if self._corners is None:
            return
        pts = [self._to_widget(c) for c in self._corners]
        shade = QPainterPath()
        shade.addRect(target)
        poly = QPainterPath()
        poly.moveTo(pts[0])
        for q in pts[1:]:
            poly.lineTo(q)
        poly.closeSubpath()
        p.fillPath(shade.subtracted(poly), QColor(0, 0, 0, 90))
        p.setPen(QPen(QColor(0, 120, 215), 2))
        p.drawPath(poly)
        if self.editable:
            p.setBrush(QBrush(QColor(255, 255, 255)))
            for q in pts:
                p.drawEllipse(q, HANDLE_RADIUS, HANDLE_RADIUS)

    # ---- souris
    def _hit(self, pos: QPointF) -> int | None:
        if self._corners is None or not self.editable:
            return None
        for i, c in enumerate(self._corners):
            q = self._to_widget(c)
            if (q.x() - pos.x()) ** 2 + (q.y() - pos.y()) ** 2 <= (HANDLE_RADIUS * 1.8) ** 2:
                return i
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = self._hit(event.position())

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and self._corners is not None:
            self._corners[self._drag] = self._to_image(event.position())
            self.update()
        else:
            hit = self._hit(event.position())
            self.setCursor(Qt.CursorShape.SizeAllCursor if hit is not None else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, _event) -> None:
        if self._drag is not None:
            self._drag = None
            self.cornersChanged.emit(self.corners())
