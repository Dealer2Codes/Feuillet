"""Icônes vectorielles de l'interface (traits simples, couleur au choix).

Dessinées pour Feuillet ; rendues par QtSvg à la taille demandée, nettes à
tous les facteurs d'échelle de Windows (100 %, 125 %, 150 %…).
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

PATHS = {
    "scanner": "M3 15h18v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zM5 15l3-9h11M7 18h3M15 11H5",
    "watermark": "M4 20h16M12 4v12M8 8l4-4 4 4M6 16h12",
    "convert": "M4 8h13l-3-3M20 16H7l3 3",
    "merge": "M8 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h3M16 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3M9 12h6M12 9v6",
    "compress": "M8 3v5H3M16 3v5h5M8 21v-5H3M16 21v-5h5",
    "lock": "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3M12 15v2",
    "info": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 8h.01",
    "settings": "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z",
    "shield": "M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6zM8.5 12l2.5 2.5 4.5-5",
    "check": "M5 12.5l4.5 4.5L19 7",
    "check_circle": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12.5l3 3 5-6",
    "upload": "M7 18a4 4 0 0 1-.6-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9M12 12v8M9 15l3-3 3 3",
    "files": "M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z",
    "folder": "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
    "id_card": "M3 6h18v12H3zM6 10h4v4H6zM13 10h5M13 13h5",
    "ocr": "M4 8V5h3M17 5h3v3M20 16v3h-3M7 19H4v-3M8 15l2-6 2 6M8.7 13h2.6M14 9h1.5a1.5 1.5 0 0 1 0 3H14zM14 12h2a1.5 1.5 0 0 1 0 3h-2z",
    "zoom_in": "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4M8 11h6M11 8v6",
    "zoom_out": "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4M8 11h6",
    "fit": "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
    "rotate_right": "M20 11a8 8 0 1 1-2.3-5.7M20 4v5h-5",
    "rotate_left": "M4 11a8 8 0 1 0 2.3-5.7M4 4v5h5",
    "crop": "M6 2v14a2 2 0 0 0 2 2h14M2 6h14a2 2 0 0 1 2 2v14",
    "compare": "M12 3v18M5 6h4v12H5zM15 6h4v12h-4z",
    "arrow_left": "M19 12H5M11 6l-6 6 6 6",
    "arrow_right": "M5 12h14M13 6l6 6-6 6",
    "trash": "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
    "play": "M7 4l13 8-13 8z",
    "pdf": "M7 3h7l5 5v13H7zM14 3v5h5M9.5 17v-4h1.3a1.2 1.2 0 0 1 0 2.4H9.5",
    "bulb": "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
    "star": "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z",
    "doc": "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h4",
    "image": "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM4 16l5-5 4 4 3-3 4 4",
    "globe": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18",
    "plus": "M12 5v14M5 12h14",
    "minus": "M5 12h14",
    "dot": "M12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
    "eye": "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "eye_off": "M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.1 3.9M6.6 6.6C3.8 8.4 2 12 2 12s3.6 7 10 7a9.6 9.6 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2",
    "add_file": "M7 3h7l5 5v13H7zM14 3v5h5M13 11v6M10 14h6",
    "remove_file": "M7 3h7l5 5v13H7zM14 3v5h5M10 14h6",
    "clear": "M4 7h16M6 7l1 13h10l1-13M9 7V4h6v3M10 11l4 5M14 11l-4 5",
    "download": "M12 4v11M7 10l5 5 5-5M5 20h14",
}
FILLED = {"star"}


def svg(name: str, color: str, stroke: float = 1.8) -> str:
    fill = color if name in FILLED else "none"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round"><path d="{PATHS[name]}"/></svg>')


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = "#1F2937", size: int = 20, ratio: float = 2.0) -> QPixmap:
    try:
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:  # QtSvg absent : pas d'icône plutôt qu'un plantage
        return QPixmap()
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode()))
    painter = QPainter(px)
    renderer.render(painter, QRectF(0, 0, px.width(), px.height()))
    painter.end()
    px.setDevicePixelRatio(ratio)
    return px


def icon(name: str, color: str = "#1F2937", size: int = 20, active_color: str | None = None) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    if active_color:
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Active, QIcon.State.On)
    ic.addPixmap(pixmap(name, "#9CA3AF", size), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic
