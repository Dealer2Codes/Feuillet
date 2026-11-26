"""Message de succès affiché à la fin de chaque traitement."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from feuillet.core.i18n import tr
from feuillet.ui import theme
from feuillet.ui.icons import icon, pixmap

MAX_LISTED = 5


class SuccessDialog(QDialog):
    """Confirmation claire : ce qui a été créé, où, et accès direct au résultat."""

    def __init__(self, parent: QWidget | None, files: Sequence[Path], detail: str = "",
                 title: str | None = None) -> None:
        super().__init__(parent)
        self.files = [Path(f) for f in files]
        self.setWindowTitle(tr("success.window_title"))
        self.setMinimumWidth(440)

        badge = QLabel()
        badge.setObjectName("SuccessBadge")
        badge.setFixedSize(56, 56)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(pixmap("check_circle", theme.SUCCESS, 34))

        heading = QLabel(title or tr("success.title"))
        heading.setObjectName("SuccessTitle")
        heading.setWordWrap(True)
        count = len(self.files)
        summary = QLabel(tr("success.one_file") if count == 1 else tr("success.n_files", n=count))
        summary.setWordWrap(True)
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(heading)
        head_text.addWidget(summary)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(head_text, 1)

        names = [f.name for f in self.files[:MAX_LISTED]]
        if count > MAX_LISTED:
            names.append(tr("success.more", n=count - MAX_LISTED))
        listing = QLabel("\n".join(names))
        listing.setObjectName("SuccessFiles")
        listing.setTextFormat(Qt.TextFormat.PlainText)
        listing.setWordWrap(True)
        listing.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.folder_label = QLabel(tr("success.folder", folder=str(self.folder)) if self.folder else "")
        self.folder_label.setTextFormat(Qt.TextFormat.PlainText)
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet(f"color: {theme.SUBTLE}; font-size: 12px;")

        self.detail_label = QLabel(detail)
        self.detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: 600;")
        self.detail_label.setVisible(bool(detail))
        original = QLabel(tr("success.original_safe"))
        original.setWordWrap(True)
        original.setStyleSheet(f"color: {theme.SUBTLE}; font-size: 12px;")

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_folder = QPushButton(icon("folder", theme.TEXT, 18), tr("success.open_folder"))
        self.btn_folder.clicked.connect(self._open_folder)
        buttons.addWidget(self.btn_folder)
        self.btn_open = None
        if count == 1:
            self.btn_open = QPushButton(icon("doc", "#FFFFFF", 18), tr("success.open_file"))
            self.btn_open.setObjectName("Primary")
            self.btn_open.clicked.connect(self._open_file)
            buttons.addWidget(self.btn_open)
        close = QPushButton(tr("common.close"))
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        for b in (self.btn_folder, self.btn_open):
            if b is not None:
                b.setIconSize(QSize(18, 18))
        (self.btn_open or close).setDefault(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addWidget(self.detail_label)
        layout.addWidget(listing)
        layout.addWidget(self.folder_label)
        layout.addWidget(original)
        layout.addSpacing(4)
        layout.addLayout(buttons)

    @property
    def folder(self) -> Path | None:
        return self.files[0].parent if self.files else None

    def _open_file(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.files[0])))
        self.accept()

    def _open_folder(self) -> None:
        if self.folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder)))
        self.accept()


def show_success(parent: QWidget | None, files: Sequence[Path], detail: str = "", title: str | None = None) -> None:
    SuccessDialog(parent, files, detail, title).exec()


def human_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unit == "Go":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n} o"
