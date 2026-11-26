"""Composants visuels réutilisables : cartes, interrupteurs, zone de dépôt…"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from feuillet.core.i18n import tr
from feuillet.ui import theme
from feuillet.ui.icons import icon, pixmap


def icon_label(name: str, color: str, size: int = 20) -> QLabel:
    label = QLabel()
    label.setPixmap(pixmap(name, color, size))
    label.setFixedSize(size, size)
    return label


class Card(QFrame):
    """Carte blanche à coins arrondis, avec titre facultatif."""

    def __init__(self, title: str = "", parent: QWidget | None = None, kind: str = "Card",
                 spacing: int = 10, margins: int = 16) -> None:
        super().__init__(parent)
        self.setObjectName(kind)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(spacing)
        self.title_label = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("CardTitle")
            self.title_label.setWordWrap(True)
            self.body.addWidget(self.title_label)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget


class ToggleSwitch(QCheckBox):
    """Interrupteur animé, avec son libellé à droite (reste une vraie case à cocher)."""

    TRACK_W, TRACK_H = 40, 22

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.setMinimumHeight(30)
        # Largeur minimale explicite : le texte passe à la ligne au lieu
        # d'imposer sa largeur à toute la colonne.
        self.setMinimumWidth(self.TRACK_W + 12 + 80)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, get_knob, set_knob)

    def setChecked(self, on: bool) -> None:
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self) -> QSize:
        text_w = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(self.TRACK_W + 12 + text_w + 4, max(30, self.fontMetrics().height() + 8))

    def minimumSizeHint(self) -> QSize:
        return QSize(self.TRACK_W + 12 + 60, max(30, self.fontMetrics().height() + 8))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        text_w = max(40, width - self.TRACK_W - 12)
        rect = self.fontMetrics().boundingRect(0, 0, text_w, 1000, Qt.TextFlag.TextWordWrap, self.text())
        return max(30, rect.height() + 8)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - self.TRACK_H) / 2
        track = QRectF(0, y, self.TRACK_W, self.TRACK_H)
        off, on = QColor("#CBD5E1"), QColor(theme.PRIMARY)
        if not self.isEnabled():
            off, on = QColor("#E2E8F0"), QColor("#A5B8E8")
        color = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)
        d = self.TRACK_H - 6
        x = 3 + (self.TRACK_W - d - 6) * self._pos
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, y + 3, d, d))
        if self.hasFocus():
            p.setPen(QColor(theme.PRIMARY))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(track.adjusted(-2, -2, 2, 2), self.TRACK_H / 2 + 2, self.TRACK_H / 2 + 2)
        p.setPen(QColor(theme.TEXT if self.isEnabled() else "#94A3B8"))
        text_rect = self.rect().adjusted(self.TRACK_W + 12, 0, 0, 0)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                   self.text())


class ModeCard(QAbstractButton):
    """Grande carte cliquable (icône, titre, sous-titre), utilisée comme onglet."""

    def __init__(self, icon_name: str, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setObjectName("ModeCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self._icon_name = icon_name
        self.icon_label = QLabel()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("ModeTitle")
        self.sub_label = QLabel(subtitle)
        self.sub_label.setObjectName("ModeSub")
        self.sub_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        self.title_label.setWordWrap(True)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(self.title_label)
        text.addWidget(self.sub_label)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 18, 12)
        row.setSpacing(14)
        row.addWidget(self.icon_label)
        row.addLayout(text, 1)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(64)
        self.setMinimumWidth(150)
        self.toggled.connect(self._restyle)
        self._restyle(False)

    def _restyle(self, on: bool) -> None:
        self.icon_label.setPixmap(pixmap(self._icon_name, "#FFFFFF" if on else theme.PRIMARY, 30))
        self.title_label.setStyleSheet(f"color: {'#FFFFFF' if on else theme.TEXT};")
        self.sub_label.setStyleSheet(f"color: {'#DCE6FF' if on else theme.MUTED};")

    def paintEvent(self, _event) -> None:
        from PySide6.QtWidgets import QStyle, QStyleOption

        opt = QStyleOption()
        opt.initFrom(self)
        if self.isChecked():
            opt.state |= QStyle.StateFlag.State_On
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return QSize(150, 64)


class DropZone(QFrame):
    """Zone de dépôt de fichiers (glisser-déposer ou clic)."""

    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)
        art = QLabel()
        art.setPixmap(pixmap("upload", theme.PRIMARY, 36))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setWordWrap(True)
        t.setStyleSheet("font-size: 14px;")
        s = QLabel(subtitle)
        s.setObjectName("Muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setWordWrap(True)
        layout.addStretch(1)
        for w in (art, t, s):
            layout.addWidget(w)
        layout.addStretch(1)

    def _hover(self, on: bool) -> None:
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._hover(True)

    def dragLeaveEvent(self, _event) -> None:
        self._hover(False)

    def dropEvent(self, event) -> None:
        self._hover(False)
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        event.acceptProposedAction()
        self.filesDropped.emit(paths)


def check_row(text: str, ok: bool = True) -> QWidget:
    """Ligne « ✓ texte » du panneau Résultat attendu."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 2, 0, 2)
    row.setSpacing(10)
    row.addWidget(icon_label("check_circle", theme.SUCCESS if ok else "#CBD5E1", 20))
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("font-size: 14px;" + ("" if ok else f"color: {theme.SUBTLE};"))
    row.addWidget(label, 1)
    return w


def tool_button(icon_name: str, tooltip: str, checkable: bool = False) -> QPushButton:
    from PySide6.QtWidgets import QToolButton

    b = QToolButton()
    b.setIcon(icon(icon_name, theme.TEXT, 20, active_color=theme.PRIMARY))
    b.setIconSize(QSize(20, 20))
    b.setToolTip(tooltip)
    b.setAccessibleName(tooltip)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def add_password_toggle(edit: QLineEdit) -> QAction:
    """Masque le mot de passe et ajoute un bouton « œil » pour l'afficher ou le masquer."""
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    show_icon = icon("eye", theme.MUTED, 20)
    hide_icon = icon("eye_off", theme.PRIMARY, 20)
    action = edit.addAction(show_icon, QLineEdit.ActionPosition.TrailingPosition)
    action.setCheckable(True)
    action.setToolTip(tr("common.show_password"))
    action.setObjectName("PasswordToggle")

    def toggle(visible: bool) -> None:
        edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        action.setIcon(hide_icon if visible else show_icon)
        action.setToolTip(tr("common.hide_password" if visible else "common.show_password"))

    action.toggled.connect(toggle)
    return action


def relax_widths(container: QWidget, floor: int = 110) -> None:
    """Empêche les éléments d'un panneau d'imposer une largeur plus grande que le panneau.

    Les polices de Windows (Segoe UI, mise à l'échelle 125 %…) sont plus larges que
    prévu : les textes passent donc à la ligne, les listes déroulantes et les boutons
    peuvent rétrécir, et les formulaires placent le libellé au-dessus du champ.
    """
    from PySide6.QtWidgets import QComboBox, QFormLayout

    for w in [container, *container.findChildren(QWidget)]:
        if isinstance(w, QLabel) and w.pixmap().isNull() and w.text() and not w.wordWrap():
            w.setWordWrap(True)
        elif isinstance(w, QComboBox):
            w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(6)
        elif isinstance(w, QPushButton) and not isinstance(w, ToggleSwitch) and w.text():
            w.setMinimumWidth(min(w.minimumSizeHint().width(), floor))
        layout = w.layout()
        if isinstance(layout, QFormLayout):
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
