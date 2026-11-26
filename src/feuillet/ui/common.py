"""Outils partagés de l'interface : conversions d'images, tâches de fond, erreurs."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QMessageBox, QWidget

from feuillet.core.errors import AppError
from feuillet.core.i18n import tr

log = logging.getLogger("feuillet")


def app_icon():
    """Icône de Feuillet à toutes les tailles (barre de titre, barre des tâches, Alt+Tab)."""
    from importlib import resources

    from PySide6.QtGui import QIcon

    icon = QIcon()
    folder = resources.files("feuillet.resources")
    for size in (16, 24, 32, 48, 64, 128, 256):
        data = folder.joinpath(f"icon-{size}.png").read_bytes()
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        icon.addPixmap(pixmap)
    return icon


def ndarray_to_qimage(img: np.ndarray) -> QImage:
    if img.ndim == 2:
        img = np.ascontiguousarray(img)
        h, w = img.shape
        return QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def ndarray_to_pixmap(img: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(ndarray_to_qimage(img))


def pymupdf_pixmap_to_qpixmap(pix) -> QPixmap:
    fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
    return QPixmap.fromImage(image)


class _Signals(QObject):
    finished = Signal(object)
    failed = Signal(object)
    progress = Signal(int, int)


class Task(QRunnable):
    """Exécute ``fn`` hors du fil de l'interface.

    ``fn`` reçoit un rappel ``progress(fait, total)`` s'il accepte l'argument
    ``progress``. Le résultat ou l'exception revient par signaux.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, with_progress: bool = False, **kwargs: Any) -> None:
        super().__init__()
        self.signals = _Signals()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        if with_progress:
            self._kwargs["progress"] = lambda done, total: self.signals.progress.emit(done, total)

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:
            log.error("Tâche en échec : %s\n%s", exc, traceback.format_exc())
            self._emit(self.signals.failed, exc)
        else:
            self._emit(self.signals.finished, result)

    @staticmethod
    def _emit(signal, value: Any) -> None:
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # la fenêtre a été fermée pendant le calcul : résultat ignoré


_ACTIVE: set[Task] = set()  # garde une référence Python tant que la tâche tourne


def run_task(task: Task, on_done: Callable[[Any], None] | None = None,
             on_error: Callable[[Exception], None] | None = None,
             on_progress: Callable[[int, int], None] | None = None) -> Task:
    task.setAutoDelete(False)
    _ACTIVE.add(task)
    task.signals.finished.connect(lambda _r: _ACTIVE.discard(task), Qt.ConnectionType.QueuedConnection)
    task.signals.failed.connect(lambda _e: _ACTIVE.discard(task), Qt.ConnectionType.QueuedConnection)
    if on_done:
        task.signals.finished.connect(on_done, Qt.ConnectionType.QueuedConnection)
    if on_error:
        task.signals.failed.connect(on_error, Qt.ConnectionType.QueuedConnection)
    if on_progress:
        task.signals.progress.connect(on_progress, Qt.ConnectionType.QueuedConnection)
    QThreadPool.globalInstance().start(task)
    return task


def error_text(exc: BaseException) -> str:
    if isinstance(exc, AppError):
        return exc.user_message()
    return tr("error.unexpected", detail=str(exc) or exc.__class__.__name__)


def message(parent: QWidget | None, level: str, title: str, text: str) -> None:
    """Boîte de message en texte brut : un nom de fichier ou un texte extrait
    d'un document n'est jamais interprété comme du HTML."""
    icons = {"info": QMessageBox.Icon.Information, "warning": QMessageBox.Icon.Warning,
             "error": QMessageBox.Icon.Critical}
    box = QMessageBox(icons[level], title, text, QMessageBox.StandardButton.Ok, parent)
    box.setTextFormat(Qt.TextFormat.PlainText)
    localize_buttons(box)
    box.exec()


def show_error(parent: QWidget | None, exc: BaseException) -> None:
    message(parent, "error", tr("app.error_title"), error_text(exc))


_STANDARD_KEYS = {
    "Ok": "common.ok", "Cancel": "common.cancel", "Yes": "common.yes", "No": "common.no", "Close": "common.close",
}


def localize_buttons(box) -> None:
    """Traduit les boutons standard (OK, Annuler, Oui, Non…) d'un QDialogButtonBox ou d'un QMessageBox.

    PySide6-Essentials ne fournit pas les traductions de Qt : sans cela, « Cancel » reste en anglais.
    """
    from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

    enum = QMessageBox.StandardButton if isinstance(box, QMessageBox) else QDialogButtonBox.StandardButton
    for name, key in _STANDARD_KEYS.items():
        btn = box.button(getattr(enum, name))
        if btn is not None:
            btn.setText(tr(key))


def ask_yes_no(parent, title: str, text: str) -> bool:
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(QMessageBox.Icon.Question, title, text,
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setTextFormat(Qt.TextFormat.PlainText)
    localize_buttons(box)
    return box.exec() == QMessageBox.StandardButton.Yes
