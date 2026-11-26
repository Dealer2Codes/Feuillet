import sys

import pytest
from PySide6.QtWidgets import QScrollArea

from feuillet.core.errors import ScannerError
from feuillet.scanner import sources
from feuillet.scanner.sources.wia import WIA_ERROR_PAPER_JAM, map_com_error


class FakeComError(Exception):
    pass


def test_wia_error_mapping():
    exc = FakeComError(-2147352567, "Exception occurred.", (0, None, None, None, 0, WIA_ERROR_PAPER_JAM - (1 << 32)), None)
    mapped = map_com_error(exc)
    assert isinstance(mapped, ScannerError) and mapped.code == "scanner_paper_jam"
    assert "Bourrage" in mapped.user_message()


def test_unknown_com_error_is_still_explicit():
    mapped = map_com_error(FakeComError("boom"))
    assert mapped.code == "scanner_failed" and "boom" in mapped.user_message()


@pytest.mark.skipif(sys.platform == "win32", reason="vérifie le comportement hors Windows")
def test_listing_never_raises_and_explains():
    devices, problems = sources.list_all_devices()
    assert devices == []
    assert {p.params.get("backend") for p in problems} == {"WIA"}  # TWAIN facultatif : pas signalé
    assert all(p.user_message() for p in problems)


def test_no_device_gives_actionable_message(monkeypatch):
    from feuillet.scanner.sources.twain import TwainSource
    from feuillet.scanner.sources.wia import WiaSource

    monkeypatch.setattr(WiaSource, "is_available", lambda self: True)
    monkeypatch.setattr(WiaSource, "list_devices", lambda self: [])
    monkeypatch.setattr(TwainSource, "is_available", lambda self: False)
    devices, problems = sources.list_all_devices()
    assert devices == []
    assert [p.code for p in problems] == ["scanner_windows_none"]
    assert "Imprimantes et scanners" in problems[0].user_message()


# ------------------------------------------------------------ interface (fumée)

qt = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    return qt.QApplication.instance() or qt.QApplication([])


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_main_window_builds(app, lang):
    from feuillet.core.i18n import set_language
    from feuillet.ui.main_window import MainWindow

    set_language(lang)
    try:
        window = MainWindow()
        assert window.pages.count() == 3
        window.close()
    finally:
        set_language("fr")


def test_scanner_tab_adds_and_orders_pages(app, tmp_path):
    import cv2
    from synthetic import make_page

    from feuillet.ui.scanner_view import ScannerTab

    paths = []
    for i in range(3):
        p = tmp_path / f"p{i}.png"
        cv2.imwrite(str(p), make_page())
        paths.append(p)
    tab = ScannerTab()
    tab.add_files(paths)
    assert len(tab.pages) == 3 and tab.btn_start.isEnabled()
    item = tab.gallery.takeItem(0)
    tab.gallery.addItem(item)
    tab._sync_order()
    assert [p.source.name for p in tab.pages] == ["p1.png", "p2.png", "p0.png"]


def test_window_centered_at_80_percent(app):
    from PySide6.QtCore import QRect

    from feuillet.ui.main_window import initial_geometry

    # Écran Full HD avec une barre des tâches de 48 px en bas
    g = initial_geometry(QRect(0, 0, 1920, 1032))
    assert (g.width(), g.height()) == (1536, 826)
    assert g.center().x() in (959, 960) and abs(g.center().y() - 516) <= 1
    # Second écran placé à droite : la fenêtre reste sur cet écran
    g2 = initial_geometry(QRect(1920, 0, 2560, 1400))
    assert g2.x() >= 1920 and g2.right() < 1920 + 2560
    # Petit écran : taille minimale, sans dépasser l'écran
    g3 = initial_geometry(QRect(0, 0, 1366, 728))
    assert g3.width() == 1093 and g3.height() == 582 and g3.bottom() < 728


def test_app_icon_has_all_sizes(app):
    from feuillet.ui.common import app_icon

    sizes = {(s.width(), s.height()) for s in app_icon().availableSizes()}
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes


def test_sidebar_shortcut_opens_convert_tool(app):
    from feuillet.ui.main_window import MainWindow

    window = MainWindow()
    window.open_tool("compress")
    assert window.pages.currentIndex() == 2
    assert window.convert.tool.id == "compress"
    window.close()


def test_expected_result_follows_settings(app):
    from feuillet.ui.scanner_view import ScannerTab

    tab = ScannerTab()
    tab.sw_shadows.setChecked(True)
    tab._update_state()
    count = tab.expected_list.count()
    tab.mode_card.setChecked(True)
    assert tab.expected_list.count() == count + 1  # ligne « taille réelle » ajoutée
    assert tab.advanced.isVisibleTo(tab)


# Contrôle strict (tout tient sans défilement) là où les polices de référence sont connues.
# Sous Windows, la police réelle peut différer : le test exige alors au minimum le défilement,
# et tools/diagnostic_layout.py indique l'élément en cause.
THEME_IS_STRICT = sys.platform != "win32"

# Polices larges (comme Segoe UI sous Windows à 125 %) : le test doit tenir avec n'importe quelle police.
WIDE_FONTS = '\n* { font-family: "DejaVu Sans"; }\nQPushButton, QComboBox, QLabel, QCheckBox { font-size: 16px; }'


@pytest.fixture(params=["theme", "wide_fonts"])
def themed(app, request):
    """Applique le thème réel de Feuillet (et, en variante, des polices plus larges)."""
    from feuillet.ui.theme import apply_theme

    old_sheet, old_style = app.styleSheet(), app.style().name()
    apply_theme(app)
    if request.param == "wide_fonts":
        app.setStyleSheet(app.styleSheet() + WIDE_FONTS)
    yield app
    app.setStyleSheet(old_sheet)
    app.setStyle(old_style)


@pytest.mark.parametrize("width", [1000, 1100, 1230, 1536, 1920])
def test_scanner_columns_never_overlap(themed, width):
    app = themed
    """Régression : à 125 % ou 150 % d'échelle Windows, les cartes se chevauchaient."""
    from feuillet.ui.main_window import MainWindow

    window = MainWindow()
    window.setGeometry(0, 0, width, 760)
    window.show()
    app.processEvents()
    tab = window.scanner
    left = tab.left_col.geometry()
    center = tab.stack.parentWidget().geometry()
    assert left.right() < center.left()
    assert center.width() >= 380
    if tab.right_col.isVisible():
        assert center.right() < tab.right_col.geometry().left()
    # le contenu de la colonne gauche tient dans sa largeur (rien de rogné)
    left_scroll = tab.left_col.findChild(QScrollArea)
    inner_fits = left_scroll.widget().minimumSizeHint().width() <= tab.left_col.width()
    assert inner_fits or left_scroll.horizontalScrollBar().isVisible()
    if THEME_IS_STRICT:
        assert inner_fits
    window.close()


def test_convert_buttons_have_icons_and_downloads_default(app, tmp_path, monkeypatch):
    monkeypatch.setenv("FEUILLET_OUTPUT_DIR", str(tmp_path))
    from PySide6.QtWidgets import QPushButton

    from feuillet.core.i18n import tr
    from feuillet.ui.convert_view import ConvertTab

    tab = ConvertTab()
    assert tab.out_dir.text() == str(tmp_path)
    for key in ("convert.add_files", "convert.remove", "convert.clear"):
        btn = next(b for b in tab.findChildren(QPushButton) if b.toolTip() == tr(key))
        assert not btn.icon().isNull() and btn.text() == ""
    icons = [b for b in tab.findChildren(QPushButton) if b.objectName() == "IconAction"]
    assert len({b.geometry().top() for b in icons}) == 1  # les trois sur la même ligne
    tab.select_tool("compress")
    assert tab.btn_run.text() == tr("convert.run.compress")
    assert not tab.btn_run.icon().isNull()


@pytest.mark.parametrize("size", [(1024, 560), (1093, 580), (1366, 700), (1920, 1000)])
def test_every_screen_fits_small_windows(themed, size):
    app = themed
    """Régression : sur 1366×768 à 125 %, les cartes de Convertir étaient écrasées."""
    from PySide6.QtWidgets import QScrollArea

    from feuillet.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(*size)
    window.show()
    app.processEvents()
    assert window.width() == size[0] and window.height() == size[1]
    for index in range(window.pages.count()):
        window.pages.setCurrentIndex(index)
        app.processEvents()
        frame = window.pages.widget(index)
        page = window.page_widget(index)
        hint = page.minimumSizeHint()
        fits = hint.width() <= window.pages.width() and hint.height() <= window.pages.height()
        # Avec le thème de Feuillet, chaque écran tient ; si une police inattendue le rend trop
        # large, des barres de défilement doivent apparaître : jamais d'éléments coupés ou superposés.
        assert fits or frame.horizontalScrollBar().isVisible() or frame.verticalScrollBar().isVisible(), (index, hint)
        if THEME_IS_STRICT:
            assert fits, (index, hint)
        for scroll in page.findChildren(QScrollArea):
            if scroll.isVisible() and scroll.widget() is not None:
                inner_fits = scroll.widget().minimumSizeHint().width() <= scroll.viewport().width() + 1
                assert inner_fits or scroll.horizontalScrollBar().isVisible(), (index, scroll)
                if THEME_IS_STRICT:
                    assert inner_fits, (index, scroll)
    window.close()


def test_password_field_can_be_revealed(app):
    from PySide6.QtWidgets import QLineEdit

    from feuillet.ui.convert_view import ConvertTab

    for tool in ("protect", "unlock"):
        tab = ConvertTab()
        tab.select_tool(tool)
        edit = tab._inputs["password"]
        assert edit.echoMode() == QLineEdit.EchoMode.Password
        toggle = next(a for a in edit.actions() if a.objectName() == "PasswordToggle")
        toggle.trigger()
        assert edit.echoMode() == QLineEdit.EchoMode.Normal
        toggle.trigger()
        assert edit.echoMode() == QLineEdit.EchoMode.Password


def test_settings_dialog_is_translated_and_explains_ocr(app, monkeypatch):
    from PySide6.QtWidgets import QDialogButtonBox

    from feuillet.core.i18n import tr
    from feuillet.scanner import ocr
    from feuillet.ui.main_window import SettingsDialog

    monkeypatch.setattr(ocr, "_candidates", list)
    ocr.find_tesseract.cache_clear()
    dialog = SettingsDialog()
    box = dialog.findChild(QDialogButtonBox)
    assert box.button(QDialogButtonBox.StandardButton.Cancel).text() == tr("common.cancel")
    assert not dialog.ocr_help.isHidden()
    assert "UB-Mannheim" in dialog.ocr_help.text()
    ocr.find_tesseract.cache_clear()


def test_success_dialog_lists_files_and_compression_gain(app, tmp_path, monkeypatch):
    from feuillet.core.i18n import tr
    from feuillet.ui import convert_view
    from feuillet.ui.success_dialog import SuccessDialog

    big, small = tmp_path / "a.pdf", tmp_path / "a_compresse.pdf"
    big.write_bytes(b"x" * 10_000)
    small.write_bytes(b"x" * 4_000)
    shown = {}
    monkeypatch.setattr(convert_view, "show_success",
                        lambda parent, files, detail="", title=None: shown.update(files=files, detail=detail,
                                                                                    title=title))
    tab = convert_view.ConvertTab()
    tab._ran_tool, tab._ran_inputs = "compress", [big]
    tab._done(([small], []))
    assert shown["files"] == [small]
    assert "60" in shown["detail"]  # 10 000 -> 4 000 octets : -60 %
    assert tr("convert.tool.compress") in shown["title"]

    dialog = SuccessDialog(None, [small], "détail")
    assert dialog.btn_open is not None and dialog.folder == tmp_path
    many = SuccessDialog(None, [tmp_path / f"f{i}.pdf" for i in range(8)])
    assert many.btn_open is None  # plusieurs fichiers : « Ouvrir le dossier » seulement


def test_tool_tree_submenus_are_indented(app):
    from feuillet.ui.convert_view import ConvertTab

    tab = ConvertTab()
    assert tab.tree.indentation() >= 24
    top = tab.tree.topLevelItem(0)
    child = top.child(0)
    assert top.font(0).bold() and not child.font(0).bold()
    assert top.foreground(0).color() != child.foreground(0).color()


def test_sidebar_highlight_follows_current_tool(app):
    from feuillet.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    nav = window.nav
    window._on_nav_clicked(4)  # clic sur « Compresser »
    assert window.convert.tool.id == "compress"
    assert nav.checkedId() == 4 and not window.nav_convert.isChecked()
    window.convert.select_tool("pdf_to_word")  # outil sans raccourci -> « Convertir »
    assert nav.checkedId() == 2
    window.convert.select_tool("split")  # -> « Fusionner / Diviser »
    assert nav.checkedId() == 3
    window._on_nav_clicked(0)  # Scanner
    assert nav.checkedId() == 0
    window.convert.select_tool("protect")  # changement en arrière-plan : Scanner reste surligné
    assert nav.checkedId() == 0
    window._on_nav_clicked(2)  # retour sur Convertir : l'outil affiché est « protect »
    assert nav.checkedId() == 5
    window.close()
