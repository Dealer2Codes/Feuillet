"""Fenêtre principale : en-tête, barre latérale de navigation, pages des modules."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSettings, QSize, Qt, QThreadPool
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from feuillet import __version__
from feuillet.core.i18n import current_language, set_language, tr
from feuillet.scanner import ocr
from feuillet.ui import theme
from feuillet.ui.common import app_icon, ask_yes_no, localize_buttons
from feuillet.ui.convert_view import ConvertTab
from feuillet.ui.icons import icon
from feuillet.ui.scanner_view import ScannerTab
from feuillet.ui.watermark_view import WatermarkTab
from feuillet.ui.widgets import icon_label

# Part de l'écran occupée par la fenêtre à l'ouverture.
SCREEN_RATIO = 0.80
# En dessous, l'interface devient illisible (petits écrans 1366 × 768).
MIN_WIDTH, MIN_HEIGHT = 1024, 560


def initial_geometry(available: QRect, ratio: float = SCREEN_RATIO) -> QRect:
    """Rectangle centré couvrant ``ratio`` de la zone utile de l'écran.

    La zone utile exclut la barre des tâches. Sur un petit écran, la taille
    minimale l'emporte, sans jamais dépasser l'écran.
    """
    w = min(available.width(), max(MIN_WIDTH, round(available.width() * ratio)))
    h = min(available.height(), max(MIN_HEIGHT, round(available.height() * ratio)))
    x = available.x() + (available.width() - w) // 2
    y = available.y() + (available.height() - h) // 2
    return QRect(x, y, w, h)


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumWidth(520)
        self.language = QComboBox()
        self.language.addItem("Français", "fr")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(0 if current_language() == "fr" else 1)
        form = QFormLayout()
        form.addRow(tr("menu.language"), self.language)
        form.addRow(tr("settings.ocr"), self._ocr_panel())
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        localize_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)


    # ---------------------------------------------------------------- OCR
    def _ocr_panel(self) -> QWidget:
        """État de Tesseract, avec la marche à suivre quand il manque."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        self.ocr_state = QLabel()
        self.ocr_state.setWordWrap(True)
        self.ocr_help = QLabel(tr("settings.ocr_help", url=OCR_URL))
        self.ocr_help.setWordWrap(True)
        self.ocr_help.setOpenExternalLinks(True)
        self.ocr_help.setTextFormat(Qt.TextFormat.RichText)
        recheck = QPushButton(icon("rotate_right", theme.PRIMARY, 16), tr("settings.ocr_recheck"))
        recheck.clicked.connect(self._refresh_ocr)
        self.ocr_recheck = recheck
        v.addWidget(self.ocr_state)
        v.addWidget(self.ocr_help)
        v.addWidget(recheck, 0, Qt.AlignmentFlag.AlignLeft)
        self._refresh_ocr()
        return box

    def _refresh_ocr(self) -> None:
        for fn in (ocr.find_tesseract, ocr.available_languages):
            fn.cache_clear()
        exe = ocr.find_tesseract()
        if exe is None:
            text, color = tr("status.ocr_off"), "#B45309"
        elif not ocr.is_available():
            text, color = tr("status.ocr_no_french"), "#B45309"
        else:
            text, color = tr("status.ocr_on"), theme.SUCCESS
        self.ocr_state.setText(f"<b style='color:{color}'>{text}</b>")
        ok = exe is not None and ocr.is_available()
        self.ocr_help.setVisible(not ok)
        self.ocr_recheck.setVisible(not ok)


OCR_URL = "https://github.com/UB-Mannheim/tesseract/wiki"


def _page_scroll(page: QWidget) -> QScrollArea:
    """Filet de sécurité : si un écran demande plus de place que la fenêtre (police
    très grande, petit écran), des barres de défilement apparaissent au lieu que
    les éléments se chevauchent ou soient coupés."""
    scroll = QScrollArea()
    scroll.setObjectName("PageScroll")
    scroll.setWidget(page)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    return scroll


# Boutons de la barre latérale qui ouvrent directement un outil de Convertir.
SHORTCUT_IDS = {"merge": 3, "split": 3, "compress": 4, "protect": 5, "unlock": 5}
SHORTCUT_TOOLS = {3: "merge", 4: "compress", 5: "protect"}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(1000, MIN_HEIGHT)
        self.setWindowIcon(app_icon())
        self._place_on_screen()
        self._build()

    def _place_on_screen(self) -> None:
        """80 % de l'écran où se trouve la souris, centré."""
        from PySide6.QtGui import QCursor

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(MIN_WIDTH, MIN_HEIGHT)
            return
        self.setGeometry(initial_geometry(screen.availableGeometry()))

    # ================================================================ construction
    def _build(self) -> None:
        self.setWindowTitle(tr("app.title"))
        self.scanner = ScannerTab()
        self.watermark = WatermarkTab()
        self.convert = ConvertTab()
        self.pages = QStackedWidget()
        self.pages.setObjectName("Content")
        for page in (self.scanner, self.watermark, self.convert):
            self.pages.addWidget(_page_scroll(page))

        central = QWidget()
        central.setObjectName("Content")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)
        self.tabs = self.pages  # compatibilité (tests, raccourcis)
        self.convert.toolChanged.connect(self._sync_convert_nav)
        self._navigate(0)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 14, 24, 14)
        row.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(QSize(56, 56)))
        logo.setFixedSize(56, 56)
        name = QLabel("Feuillet")
        name.setObjectName("AppName")
        tagline = QLabel(tr("app.tagline"))
        tagline.setObjectName("AppTagline")
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(name)
        text.addWidget(tagline)
        row.addWidget(logo)
        row.addLayout(text)
        row.addStretch(1)

        banner = QFrame()
        banner.setObjectName("PrivacyBanner")
        b = QHBoxLayout(banner)
        b.setContentsMargins(16, 10, 20, 10)
        b.setSpacing(12)
        b.addWidget(icon_label("shield", theme.SUCCESS, 34))
        bt = QVBoxLayout()
        bt.setSpacing(2)
        t1 = QLabel(tr("app.privacy_title"))
        t1.setObjectName("PrivacyTitle")
        t2 = QLabel(tr("app.privacy_sub"))
        t2.setObjectName("PrivacySub")
        bt.addWidget(t1)
        bt.addWidget(t2)
        b.addLayout(bt)
        row.addWidget(banner)
        self.privacy_sub = t2
        self.tagline = tagline
        return header

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        col = QVBoxLayout(side)
        col.setContentsMargins(14, 18, 14, 18)
        col.setSpacing(6)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.sidebar_layout = col
        self.nav_buttons: list[QPushButton] = []

        def nav_button(icon_name: str, text: str, checkable: bool = True) -> QPushButton:
            btn = QPushButton(icon(icon_name, "#DCE6FF", 22, active_color="#FFFFFF"), "  " + text)
            btn.setIconSize(QSize(22, 22))
            btn.setCheckable(checkable)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(38)
            btn.setMaximumHeight(46)
            col.addWidget(btn)
            self.nav_buttons.append(btn)
            return btn

        self.nav_scanner = nav_button("scanner", tr("nav.scanner"))
        self.nav_watermark = nav_button("watermark", tr("nav.watermark"))
        self.nav_convert = nav_button("convert", tr("nav.convert"))
        for i, b in enumerate((self.nav_scanner, self.nav_watermark, self.nav_convert)):
            self.nav.addButton(b, i)
        # Raccourcis vers les outils les plus utilisés du module Convertir : ils
        # font partie du même groupe, donc un seul bouton est surligné à la fois.
        for icon_name, key, tool in (("merge", "nav.merge_split", "merge"), ("compress", "nav.compress", "compress"),
                                     ("lock", "nav.protect", "protect")):
            b = nav_button(icon_name, tr(key))
            self.nav.addButton(b, SHORTCUT_IDS[tool])
        self.nav.idClicked.connect(self._on_nav_clicked)

        sep = QFrame()
        sep.setObjectName("SidebarSeparator")
        col.addSpacing(8)
        col.addWidget(sep)
        col.addSpacing(8)
        about = nav_button("info", tr("menu.about"), checkable=False)
        about.clicked.connect(self._about)
        settings = nav_button("settings", tr("nav.settings"), checkable=False)
        settings.clicked.connect(self._settings)
        col.addStretch(1)

        badge = QFrame()
        badge.setObjectName("OfflineBadge")
        bl = QHBoxLayout(badge)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(10)
        bl.addWidget(icon_label("check_circle", "#4ADE80", 24))
        bt = QVBoxLayout()
        bt.setSpacing(0)
        t1 = QLabel(tr("nav.offline"))
        t1.setStyleSheet("font-weight: 600;")
        t2 = QLabel(tr("nav.offline_sub"))
        t2.setObjectName("BadgeSub")
        bt.addWidget(t1)
        bt.addWidget(t2)
        bl.addLayout(bt, 1)
        col.addWidget(badge)
        self.offline_badge = badge
        return side

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "privacy_sub"):
            narrow = self.width() < 1150
            self.privacy_sub.setVisible(not narrow)
            self.tagline.setVisible(self.width() >= 980)
        if hasattr(self, "offline_badge"):
            # Petit écran (ex. 1366×768 à 125 %) : barre latérale compacte.
            short = self.height() < 680
            self.offline_badge.setVisible(not short)
            self.sidebar_layout.setSpacing(2 if short else 6)
            for b in self.nav_buttons:
                b.setFixedHeight(38 if short else 46)

    # ================================================================ navigation
    def page_widget(self, index: int) -> QWidget:
        """Écran affiché à l'index donné (sans son cadre défilant)."""
        return self.pages.widget(index).widget()

    def _on_nav_clicked(self, button_id: int) -> None:
        if button_id in SHORTCUT_TOOLS:
            self.open_tool(SHORTCUT_TOOLS[button_id])
        else:
            self._navigate(button_id)

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        if index == 2 and self.convert.tool is not None:
            self._sync_convert_nav(self.convert.tool.id)
        else:
            self.nav.button(index).setChecked(True)

    def open_tool(self, tool_id: str) -> None:
        self.pages.setCurrentIndex(2)
        self.convert.select_tool(tool_id)
        self._sync_convert_nav(tool_id)

    def _sync_convert_nav(self, tool_id: str) -> None:
        """Surligne le raccourci de l'outil affiché (Compresser…), sinon « Convertir »."""
        if self.pages.currentIndex() != 2:
            return
        self.nav.button(SHORTCUT_IDS.get(tool_id, 2)).setChecked(True)

    def _settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec():
            self.change_language(dialog.language.currentData())

    def change_language(self, code: str) -> None:
        if code == current_language():
            return
        if self.scanner.pages or self.watermark.source:
            if not ask_yes_no(self, tr("menu.language"), tr("app.language_reset_warning")):
                return
        index = self.pages.currentIndex()
        set_language(code)
        QSettings().setValue("language", code)
        self._build()
        self._navigate(index)

    def closeEvent(self, event) -> None:
        QThreadPool.globalInstance().waitForDone(5000)  # laisse finir un export en cours
        super().closeEvent(event)

    def _about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("menu.about"))
        box.setIconPixmap(app_icon().pixmap(QSize(64, 64)))
        box.setText(tr("app.about", version=__version__))
        box.exec()
