"""Écran Scanner : étapes numérotées, aperçu central, panneau « Résultat attendu »."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from feuillet.core.files import downloads_dir, suggest_output_name
from feuillet.core.i18n import tr
from feuillet.scanner import imaging, ocr
from feuillet.scanner.models import (
    DocumentKind,
    EnhanceMode,
    IdCardLayout,
    OutputOptions,
    PageSettings,
    PageSize,
    ScanPage,
)
from feuillet.scanner.pdf_builder import build_id_card_pdf, build_pdf
from feuillet.ui import theme
from feuillet.ui.common import (
    Task,
    error_text,
    message,
    ndarray_to_pixmap,
    run_task,
    show_error,
)
from feuillet.ui.crop_editor import CornerEditor
from feuillet.ui.icons import icon
from feuillet.ui.scan_dialog import ScanDialog
from feuillet.ui.success_dialog import show_success
from feuillet.ui.widgets import (
    Card,
    DropZone,
    ModeCard,
    ToggleSwitch,
    check_row,
    icon_label,
    relax_widths,
    tool_button,
)

PREVIEW_MAX_SIDE = 1600
# Largeurs des colonnes (pixels logiques) : la colonne centrale garde au moins
# CENTER_MIN ; le panneau de droite se masque quand la place manque.
LEFT_MIN, LEFT_MAX = 320, 400
LEFT_CHROME = 64  # marges de la carte + barre de défilement
RELAXED_MIN = 110
CENTER_MIN = 400
RIGHT_W = 300
GAPS = 16 * 2 + 40
THUMB = 72
ZOOMS = (25, 50, 75, 100, 150, 200)


class ImageView(QScrollArea):
    """Affiche une image ajustée à la zone (par défaut) ou à un zoom fixe."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PreviewCanvas")
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("PreviewCanvas")
        self.label.setWordWrap(True)
        self.label.setMargin(24)
        self.setWidget(self.label)
        self._pixmap: QPixmap | None = None
        self.zoom: float | None = None  # None = ajuster

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self._render()

    def set_text(self, text: str) -> None:
        self._pixmap = None
        self.label.setPixmap(QPixmap())
        self.label.setText(text)

    def _render(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        if self.zoom is None:
            size = self.viewport().size() - QSize(32, 32)
            shown = self._pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
        else:
            shown = self._pixmap.scaledToWidth(max(1, int(self._pixmap.width() * self.zoom)),
                                               Qt.TransformationMode.SmoothTransformation)
        self.label.setText("")
        self.label.setPixmap(shown)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.zoom is None:
            self._render()


class ScannerTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pages: list[ScanPage] = []
        self.current = -1
        self._preview_cache: dict[int, tuple[np.ndarray, float]] = {}
        self._result_cache: dict[int, np.ndarray] = {}
        self._token = 0
        self._loading_ui = False
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self._refresh_preview)
        self._build()
        self._load_settings(PageSettings())  # réglages recommandés activés d'emblée
        self._relax_left_column()
        self._update_state()

    # ================================================================ construction
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(16)

        # --- cartes de mode (en haut)
        self.mode_document = ModeCard("scanner", tr("scanner.card_document"), tr("scanner.card_document_sub"))
        self.mode_card = ModeCard("id_card", tr("scanner.card_id"), tr("scanner.card_id_sub"))
        self.mode_advanced = ModeCard("ocr", tr("scanner.card_advanced"), tr("scanner.card_advanced_sub"))
        kinds = QButtonGroup(self)
        kinds.addButton(self.mode_document)
        kinds.addButton(self.mode_card)
        self.mode_document.setChecked(True)
        self.mode_document.toggled.connect(lambda _on: self._kind_changed())
        self.mode_advanced.toggled.connect(self._toggle_advanced)
        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(self.mode_document, 3)
        top.addWidget(self.mode_card, 2)
        top.addWidget(self.mode_advanced, 2)
        top.addStretch(1)
        root.addLayout(top)

        # --- trois colonnes
        cols = QHBoxLayout()
        cols.setSpacing(16)
        cols.addWidget(self._build_left(), 0)
        center = self._build_center()
        center.setMinimumWidth(CENTER_MIN)
        cols.addWidget(center, 1)
        cols.addWidget(self._build_right(), 0)
        root.addLayout(cols, 1)

    def _build_left(self) -> QWidget:
        # Étape 1
        step1 = Card(tr("scanner.step1"))
        self.btn_add = QPushButton(icon("add_file", "#FFFFFF", 18), tr("scanner.choose_files"))
        self.btn_add.setObjectName("Primary")
        self.btn_scan = QPushButton(icon("scanner", theme.PRIMARY, 18), tr("scanner.from_scanner"))
        self.btn_add.clicked.connect(self._choose_files)
        self.btn_scan.clicked.connect(self._scan)
        row = QHBoxLayout()
        row.setSpacing(10)
        for b in (self.btn_add, self.btn_scan):
            b.setMinimumHeight(40)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self.btn_add, 1)
        row.addWidget(self.btn_scan, 1)
        step1.body.addLayout(row)
        self.drop = DropZone(tr("scanner.drop_title"), tr("scanner.drop_sub"))
        self.drop.filesDropped.connect(self.add_files)
        self.drop.clicked.connect(self._choose_files)
        step1.add(self.drop)
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setFlow(QListWidget.Flow.LeftToRight)
        self.gallery.setWrapping(False)
        self.gallery.setIconSize(QSize(THUMB, THUMB))
        self.gallery.setFixedHeight(THUMB + 46)
        self.gallery.setMovement(QListWidget.Movement.Snap)
        self.gallery.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.gallery.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.gallery.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.gallery.setToolTip(tr("scanner.drop_hint"))
        self.gallery.currentRowChanged.connect(self._select_row)
        self.gallery.model().rowsMoved.connect(lambda *_: self._sync_order())
        step1.add(self.gallery)

        # Étape 2
        step2 = Card(tr("scanner.step2"))
        self.mode = QComboBox()
        for m in EnhanceMode:
            self.mode.addItem(tr(f"mode.{m.value}"), m)
        self.mode.setCurrentIndex(list(EnhanceMode).index(EnhanceMode.AUTO))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(tr("scanner.mode"), self.mode)
        step2.body.addLayout(form)
        self.sw_detect = ToggleSwitch(tr("scanner.auto_detect"))
        self.sw_deskew = ToggleSwitch(tr("scanner.deskew"))
        self.sw_shadows = ToggleSwitch(tr("scanner.remove_shadows"))
        self.sw_sharpen = ToggleSwitch(tr("scanner.sharpen"))
        self.sw_denoise = ToggleSwitch(tr("scanner.denoise"))
        self.sw_marks = ToggleSwitch(tr("scanner.preserve_marks"))
        self.sw_marks.setToolTip(tr("scanner.preserve_marks_tip"))
        self.sw_ocr = ToggleSwitch(tr("scanner.ocr_short"))
        if not ocr.is_available("fra+eng"):
            self.sw_ocr.setEnabled(False)
            self.sw_ocr.setToolTip(tr("error.ocr_not_installed"))
        for sw in (self.sw_detect, self.sw_deskew, self.sw_shadows, self.sw_sharpen, self.sw_denoise,
                   self.sw_marks, self.sw_ocr):
            step2.add(sw)
        for sw in (self.sw_detect, self.sw_deskew, self.sw_shadows, self.sw_sharpen, self.sw_denoise, self.sw_marks):
            sw.toggled.connect(self._settings_changed)
        self.sw_ocr.toggled.connect(lambda _on: self._update_state())
        self.mode.currentIndexChanged.connect(self._settings_changed)

        self.quality = QComboBox()
        self.quality.addItem(tr("scanner.quality_high"), (300, 90))
        self.quality.addItem(tr("scanner.quality_standard"), (200, 85))
        self.quality.addItem(tr("scanner.quality_compact"), (150, 70))
        self.quality.currentIndexChanged.connect(lambda _i: self._update_state())
        self.page_size = QComboBox()
        for ps in PageSize:
            self.page_size.addItem(tr(f"pagesize.{ps.value}"), ps)
        self.page_size.currentIndexChanged.connect(lambda _i: self._update_state())
        out_form = QFormLayout()
        out_form.setContentsMargins(0, 6, 0, 0)
        out_form.setVerticalSpacing(8)
        out_form.addRow(tr("scanner.quality"), self.quality)
        out_form.addRow(tr("scanner.page_size"), self.page_size)
        step2.body.addLayout(out_form)

        # Options avancées (cachées par défaut)
        self.advanced = Card(tr("scanner.card_advanced"))
        self.sw_orient = ToggleSwitch(tr("scanner.auto_orientation"))
        if "osd" not in ocr.available_languages():
            self.sw_orient.setEnabled(False)
            self.sw_orient.setToolTip(tr("scanner.osd_missing"))
        self.sw_orient.toggled.connect(self._settings_changed)
        self.advanced.add(self.sw_orient)
        self.brightness = self._slider(-100, 100)
        self.contrast = self._slider(-100, 100)
        self.brightness.valueChanged.connect(self._settings_changed)
        self.contrast.valueChanged.connect(self._settings_changed)
        self.card_layout = QComboBox()
        self.card_layout.addItem(tr("scanner.card_one_page"), IdCardLayout.ONE_PAGE)
        self.card_layout.addItem(tr("scanner.card_two_pages"), IdCardLayout.TWO_PAGES)
        adv_form = QFormLayout()
        adv_form.setContentsMargins(0, 0, 0, 0)
        adv_form.addRow(tr("scanner.brightness"), self.brightness)
        adv_form.addRow(tr("scanner.contrast"), self.contrast)
        adv_form.addRow(tr("scanner.card_layout"), self.card_layout)
        self.advanced.body.addLayout(adv_form)
        self.btn_apply_all = QPushButton(tr("scanner.apply_all"))
        self.btn_apply_all.clicked.connect(self._apply_to_all)
        self.advanced.add(self.btn_apply_all)
        self.advanced.setVisible(False)

        # Action principale
        self.btn_start = QPushButton(icon("play", "#FFFFFF", 16), tr("scanner.start"))
        self.btn_start.setObjectName("Primary")
        self.btn_start.setProperty("class", "Big")
        self.btn_start.setMinimumHeight(48)
        self.btn_start.setStyleSheet("font-size: 16px;")
        self.btn_start.clicked.connect(self._generate)
        self.progress = QProgressBar()
        self.progress.setVisible(False)

        for combo in (self.mode, self.quality, self.page_size, self.card_layout):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
            combo.setMinimumWidth(0)
        for f in (form, out_form, adv_form):
            # Libellé au-dessus du champ quand la colonne est étroite
            f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.gallery.setMinimumWidth(0)
        self.btn_apply_all.setMinimumWidth(0)
        self.btn_apply_all.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        inner = QWidget()
        inner.setMinimumWidth(0)
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 12, 0)
        col.setSpacing(14)
        col.addWidget(step1)
        col.addWidget(step2)
        col.addWidget(self.advanced)
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # filet : défilement plutôt que texte coupé

        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(10)
        wl.addWidget(scroll, 1)
        wl.addWidget(self.progress)
        wl.addWidget(self.btn_start)
        wrapper.setFixedWidth(LEFT_MAX)
        self.left_col = wrapper
        self.files_row = row
        return wrapper

    @staticmethod
    def _slider(lo: int, hi: int, value: int = 0) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(value)
        return s

    def _build_center(self) -> QWidget:
        card = Card(margins=0, spacing=0)
        # barre d'outils
        bar = QWidget()
        bar.setObjectName("PreviewToolbar")
        tb = QHBoxLayout(bar)
        tb.setContentsMargins(12, 8, 12, 8)
        tb.setSpacing(4)
        self.btn_zoom_out = tool_button("zoom_out", tr("scanner.zoom_out"))
        self.btn_zoom_in = tool_button("zoom_in", tr("scanner.zoom_in"))
        self.zoom = QComboBox()
        self.zoom.addItem(tr("scanner.zoom_fit"), None)
        for z in ZOOMS:
            self.zoom.addItem(f"{z} %", z / 100)
        self.zoom.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)  # largeur selon la police
        self.zoom.currentIndexChanged.connect(self._zoom_changed)
        self.btn_fit = tool_button("fit", tr("scanner.zoom_fit"))
        self.btn_rot_left = tool_button("rotate_left", tr("scanner.rotate_left"))
        self.btn_rot_right = tool_button("rotate_right", tr("scanner.rotate_right"))
        self.btn_frame = tool_button("crop", tr("scanner.adjust_frame"), checkable=True)
        self.btn_compare = tool_button("compare", tr("scanner.compare"), checkable=True)
        self.btn_zoom_out.clicked.connect(lambda: self._step_zoom(-1))
        self.btn_zoom_in.clicked.connect(lambda: self._step_zoom(1))
        self.btn_fit.clicked.connect(lambda: self.zoom.setCurrentIndex(0))
        self.btn_rot_left.clicked.connect(lambda: self._rotate(270))
        self.btn_rot_right.clicked.connect(lambda: self._rotate(90))
        self.btn_frame.toggled.connect(self._frame_mode)
        self.btn_compare.toggled.connect(self._compare_mode)
        for w in (self.btn_zoom_out, self.zoom, self.btn_zoom_in, self.btn_fit):
            tb.addWidget(w)
        tb.addStretch(1)
        for w in (self.btn_rot_left, self.btn_rot_right, self.btn_frame, self.btn_compare):
            tb.addWidget(w)
        card.add(bar)

        # Ligne affichée seulement en mode « ajuster le cadre »
        self.frame_bar = QWidget()
        self.frame_bar.setObjectName("PreviewToolbar")
        self.frame_bar.setStyleSheet("border-radius: 0;")
        fb = QHBoxLayout(self.frame_bar)
        fb.setContentsMargins(12, 6, 12, 6)
        fb.setSpacing(8)
        hint = QLabel(tr("scanner.frame_hint"))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        self.btn_detect = QPushButton(tr("scanner.detect_edges"))
        self.btn_full = QPushButton(tr("scanner.full_image"))
        self.btn_detect.clicked.connect(self._detect_edges)
        self.btn_full.clicked.connect(self._full_frame)
        fb.addWidget(hint, 1)
        fb.addWidget(self.btn_detect)
        fb.addWidget(self.btn_full)
        self.frame_bar.setVisible(False)
        card.add(self.frame_bar)

        # zone d'aperçu
        self.view = ImageView()
        self.view.set_text(tr("scanner.no_page"))
        self.editor = CornerEditor()
        self.editor.cornersChanged.connect(self._corners_edited)
        self.before_view = ImageView()
        self.after_view = ImageView()
        compare = QSplitter(Qt.Orientation.Horizontal)
        compare.addWidget(self._labelled(tr("scanner.before"), self.before_view))
        compare.addWidget(self._labelled(tr("scanner.after"), self.after_view))
        self.stack = QStackedWidget()
        self.stack.setObjectName("PreviewCanvas")
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.editor)
        self.stack.addWidget(compare)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.add(self.stack, 1)

        # pied : navigation entre pages
        foot = QWidget()
        foot.setObjectName("PreviewFooter")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(12, 6, 12, 6)
        self.btn_prev = tool_button("arrow_left", tr("scanner.prev_page"))
        self.btn_next = tool_button("arrow_right", tr("scanner.next_page"))
        self.page_label = QLabel("0 / 0")
        self.page_label.setStyleSheet("font-size: 15px; font-weight: 600; padding: 0 10px;")
        self.btn_delete = tool_button("trash", tr("scanner.remove"))
        self.btn_prev.clicked.connect(lambda: self._go(-1))
        self.btn_next.clicked.connect(lambda: self._go(1))
        self.btn_delete.clicked.connect(self._remove_current)
        fl.addStretch(1)
        fl.addWidget(self.btn_prev)
        fl.addWidget(self.page_label)
        fl.addWidget(self.btn_next)
        fl.addStretch(1)
        fl.addWidget(self.btn_delete)
        card.add(foot)
        return card

    @staticmethod
    def _labelled(title: str, widget: QWidget) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        label = QLabel(title)
        label.setStyleSheet(f"font-weight: 600; color: {theme.MUTED}; padding: 6px 12px; background: #E9EEF5;")
        v.addWidget(label)
        v.addWidget(widget, 1)
        return box

    def _build_right(self) -> QWidget:
        self.expected = Card()
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(icon_label("check_circle", theme.SUCCESS, 26))
        title = QLabel(tr("scanner.expected"))
        title.setObjectName("CardTitle")
        head.addWidget(title, 1)
        self.expected.body.addLayout(head)
        self.expected_list = QVBoxLayout()
        self.expected_list.setSpacing(4)
        self.expected.body.addLayout(self.expected_list)

        original = Card(kind="SoftCard")
        r = QHBoxLayout()
        r.setSpacing(10)
        r.addWidget(icon_label("bulb", theme.PRIMARY, 22), 0, Qt.AlignmentFlag.AlignTop)
        t = QLabel(tr("scanner.original_safe"))
        t.setWordWrap(True)
        r.addWidget(t, 1)
        original.body.addLayout(r)

        info = Card()
        ih = QHBoxLayout()
        ih.setSpacing(8)
        ih.addWidget(icon_label("doc", theme.PRIMARY, 20))
        it = QLabel(tr("scanner.info"))
        it.setObjectName("CardTitle")
        ih.addWidget(it, 1)
        info.body.addLayout(ih)
        self.info_files = QLabel()
        self.info_pages = QLabel()
        self.info_res = QLabel()
        self.info_format = QLabel()
        for w in (self.info_files, self.info_pages, self.info_res, self.info_format):
            w.setStyleSheet("font-size: 14px;")
            info.add(w)

        tip = Card(kind="TipCard")
        th = QHBoxLayout()
        th.setSpacing(8)
        th.addWidget(icon_label("star", "#F59E0B", 20))
        tt = QLabel(tr("scanner.tip"))
        tt.setObjectName("CardTitle")
        th.addWidget(tt, 1)
        tip.body.addLayout(th)
        self.tip_text = QLabel()
        self.tip_text.setWordWrap(True)
        tip.add(self.tip_text)

        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        for w in (self.expected, original, info, tip):
            col.addWidget(w)
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFixedWidth(RIGHT_W)
        relax_widths(inner)
        self.right_col = scroll
        return scroll

    # ================================================================ adaptation à la largeur
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_columns(self.width())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_columns(self.width())

    def _fit_columns(self, width: int) -> None:
        """Répartit la largeur : rien ne se chevauche, quelle que soit la taille."""
        show_right = width >= LEFT_MIN + CENTER_MIN + RIGHT_W + GAPS + 40
        self.right_col.setVisible(show_right)
        room = width - CENTER_MIN - GAPS - (RIGHT_W + 16 if show_right else 0)
        left = max(LEFT_MIN, min(LEFT_MAX, room))
        self.left_col.setFixedWidth(left)
        # Boutons « Choisir » et « Numériser » côte à côte seulement s'ils tiennent
        # vraiment (les polices de Windows sont plus larges que d'autres).
        needed = (self.btn_add.sizeHint().width() + self.btn_scan.sizeHint().width()
                  + self.files_row.spacing() + LEFT_CHROME)
        direction = (QHBoxLayout.Direction.LeftToRight if left >= needed else QHBoxLayout.Direction.TopToBottom)
        if self.files_row.direction() != direction:
            self.files_row.setDirection(direction)
            self.files_row.invalidate()
        # Sous-titres des cartes du haut masqués quand la place manque
        compact = width < 1000
        for card in (self.mode_document, self.mode_card, self.mode_advanced):
            card.sub_label.setVisible(not compact)

    def minimumSizeHint(self) -> QSize:
        return QSize(LEFT_MIN + CENTER_MIN + GAPS, 420)

    def _relax_left_column(self) -> None:
        relax_widths(self.left_col.findChild(QScrollArea).widget(), RELAXED_MIN)

    # ================================================================ état général
    def kind(self) -> DocumentKind:
        return DocumentKind.ID_CARD if self.mode_card.isChecked() else DocumentKind.DOCUMENT

    def _kind_changed(self) -> None:
        is_card = self.kind() is DocumentKind.ID_CARD
        self.sw_deskew.setEnabled(not is_card)
        if is_card and not self.mode_advanced.isChecked():
            self.mode_advanced.setChecked(True)  # la mise en page recto/verso s'y trouve
        self._update_state()
        self._timer.start()

    def _toggle_advanced(self, on: bool) -> None:
        self.advanced.setVisible(on)

    def _update_state(self) -> None:
        has = bool(self.pages)
        for w in (self.btn_start, self.btn_rot_left, self.btn_rot_right, self.btn_frame, self.btn_compare,
                  self.btn_detect, self.btn_full, self.btn_delete, self.btn_apply_all, self.btn_zoom_in,
                  self.btn_zoom_out, self.btn_fit, self.zoom):
            w.setEnabled(has)
        n = len(self.pages)
        self.page_label.setText(f"{self.current + 1 if has else 0} / {n}")
        self.btn_prev.setEnabled(has and self.current > 0)
        self.btn_next.setEnabled(has and self.current < n - 1)
        is_card = self.kind() is DocumentKind.ID_CARD
        self.btn_start.setText(tr("scanner.start_card") if is_card else tr("scanner.start_n", n=n) if n else tr("scanner.start"))

        # Résultat attendu : reflète les réglages réels
        while self.expected_list.count():
            item = self.expected_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = [
            (tr("scanner.exp_frame"), self.sw_detect.isChecked() or is_card),
            (tr("scanner.exp_straight"), self.sw_deskew.isChecked() and not is_card),
            (tr("scanner.exp_shadows"), self.sw_shadows.isChecked()),
            (tr("scanner.exp_marks"), self.sw_marks.isChecked()),
            (tr("scanner.exp_ocr"), self.sw_ocr.isChecked()),
        ]
        if is_card:
            rows.insert(1, (tr("scanner.exp_card_size"), True))
        for text, ok in rows:
            self.expected_list.addWidget(check_row(text, ok))

        sources = {p.source for p in self.pages if p.source}
        dpi, _q = self.quality.currentData()
        self.info_files.setText(tr("scanner.info_files", n=len(sources) or (n if n else 0)))
        self.info_pages.setText(tr("scanner.info_pages", n=n))
        self.info_res.setText(tr("scanner.info_res", dpi=dpi))
        self.info_format.setText(tr("scanner.info_format", size=self.page_size.currentText()))
        self.tip_text.setText(tr("scanner.tip_card") if not is_card else tr("scanner.tip_card_active"))

    # ================================================================ pages
    def current_page(self) -> ScanPage | None:
        return self.pages[self.current] if 0 <= self.current < len(self.pages) else None

    def _choose_files(self) -> None:
        exts = " ".join(f"*{e}" for e in imaging.SUPPORTED_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(self, tr("scanner.choose_files"), "",
                                                f"{tr('scanner.images')} ({exts})")
        if files:
            self.add_files([Path(f) for f in files])

    def add_files(self, paths: list[Path]) -> None:
        errors = []
        for path in paths:
            if path.suffix.lower() not in imaging.SUPPORTED_EXTENSIONS:
                errors.append(tr("error.unsupported_image", path=path.name))
                continue
            try:
                frames = imaging.load_images(path)
            except Exception as exc:
                errors.append(error_text(exc))
                continue
            for i, frame in enumerate(frames):
                label = path.name if len(frames) == 1 else f"{path.name} ({i + 1})"
                self._append(ScanPage(frame, source=path, label=label, settings=self._default_settings()))
        if errors:
            message(self, "warning", tr("app.error_title"), "\n".join(errors))

    def add_images(self, images: list[np.ndarray], label: str) -> None:
        for i, img in enumerate(images, 1):
            self._append(ScanPage(img, label=f"{label} {i}", settings=self._default_settings()))

    def _default_settings(self) -> PageSettings:
        s = PageSettings()
        self._read_settings_into(s)
        return s

    def _append(self, page: ScanPage) -> None:
        self.pages.append(page)
        item = QListWidgetItem(QIcon(ndarray_to_pixmap(imaging.resize_to_max(page.original, THUMB * 2))),
                               str(len(self.pages)))
        item.setData(Qt.ItemDataRole.UserRole, page.id)
        item.setToolTip(page.label)
        self.gallery.addItem(item)
        self.gallery.setCurrentRow(len(self.pages) - 1)
        self._update_state()

    def _select_row(self, row: int) -> None:
        if row < 0 or row >= self.gallery.count():
            self.current = -1
            self.view.set_text(tr("scanner.no_page"))
            self.editor.clear()
            self._update_state()
            return
        pid = self.gallery.item(row).data(Qt.ItemDataRole.UserRole)
        self.current = next(i for i, p in enumerate(self.pages) if p.id == pid)
        self._load_settings(self.pages[self.current].settings)
        self._update_state()
        self._refresh_preview()

    def _go(self, delta: int) -> None:
        target = self.gallery.currentRow() + delta
        if 0 <= target < self.gallery.count():
            self.gallery.setCurrentRow(target)

    def _sync_order(self) -> None:
        order = [self.gallery.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.gallery.count())]
        by_id = {p.id: p for p in self.pages}
        current = self.current_page()
        self.pages = [by_id[i] for i in order if i in by_id]
        for i in range(self.gallery.count()):
            self.gallery.item(i).setText(str(i + 1))
        if current is not None:  # comparaison par identifiant (les images sont des tableaux)
            self.current = next(i for i, p in enumerate(self.pages) if p.id == current.id)
        self._update_state()

    def _remove_current(self) -> None:
        page = self.current_page()
        if page is None:
            return
        row = self.gallery.currentRow()
        self.gallery.blockSignals(True)
        self.gallery.takeItem(row)
        self.gallery.blockSignals(False)
        self.pages = [p for p in self.pages if p.id != page.id]
        self._preview_cache.pop(page.id, None)
        self._result_cache.pop(page.id, None)
        for i in range(self.gallery.count()):
            self.gallery.item(i).setText(str(i + 1))
        self.current = -1
        if self.gallery.count():
            self.gallery.setCurrentRow(min(row, self.gallery.count() - 1))
            self._select_row(self.gallery.currentRow())
        else:
            self._select_row(-1)

    def _rotate(self, degrees: int) -> None:
        page = self.current_page()
        if page is None:
            return
        page.settings.rotate_by(degrees)
        self._preview_cache.pop(page.id, None)
        item = self.gallery.item(self.gallery.currentRow())
        thumb = imaging.rotate_quarter(imaging.resize_to_max(page.original, THUMB * 2), page.settings.rotation)
        item.setIcon(QIcon(ndarray_to_pixmap(thumb)))
        self._refresh_preview()

    def _scan(self) -> None:
        dialog = ScanDialog(self)
        if dialog.exec() and dialog.images:
            self.add_images(dialog.images, tr("scanner.scanned_page"))

    # ================================================================ réglages
    def _load_settings(self, s: PageSettings) -> None:
        self._loading_ui = True
        self.mode.setCurrentIndex(list(EnhanceMode).index(s.mode))
        self.sw_detect.setChecked(s.auto_detect)
        self.sw_deskew.setChecked(s.deskew)
        self.sw_orient.setChecked(s.auto_orientation and self.sw_orient.isEnabled())
        self.sw_shadows.setChecked(s.remove_shadows)
        self.sw_denoise.setChecked(s.denoise)
        self.sw_sharpen.setChecked(s.sharpen)
        self.sw_marks.setChecked(s.preserve_color_marks)
        self.brightness.setValue(s.brightness)
        self.contrast.setValue(s.contrast)
        self._loading_ui = False

    def _read_settings_into(self, s: PageSettings) -> None:
        s.mode = self.mode.currentData()
        s.auto_detect = self.sw_detect.isChecked()
        s.deskew = self.sw_deskew.isChecked()
        s.auto_orientation = self.sw_orient.isChecked()
        s.remove_shadows = self.sw_shadows.isChecked()
        s.denoise = self.sw_denoise.isChecked()
        s.sharpen = self.sw_sharpen.isChecked()
        s.preserve_color_marks = self.sw_marks.isChecked()
        s.brightness = self.brightness.value()
        s.contrast = self.contrast.value()

    def _settings_changed(self, *_args) -> None:
        if self._loading_ui:
            return
        self._update_state()
        page = self.current_page()
        if page is None:
            return
        self._read_settings_into(page.settings)
        self._timer.start()

    def _apply_to_all(self) -> None:
        current = self.current_page()
        if current is None:
            return
        for page in self.pages:
            if page is not current:
                rotation, corners = page.settings.rotation, page.settings.corners
                page.settings = copy.deepcopy(current.settings)
                page.settings.rotation, page.settings.corners = rotation, corners

    def _corners_edited(self, corners_small: np.ndarray) -> None:
        page = self.current_page()
        cached = self._preview_cache.get(page.id) if page else None
        if page is None or cached is None:
            return
        page.settings.corners = (corners_small / cached[1]).astype(np.float32)
        self._timer.start()

    def _detect_edges(self) -> None:
        page = self.current_page()
        if page is None:
            return
        rotated = imaging.rotate_quarter(page.original, page.settings.rotation)
        corners = imaging.detect_document(rotated)
        if corners is None:
            message(self, "info", tr("scanner.detect_edges"), tr("scanner.detect_failed"))
            corners = imaging.full_frame(rotated)
        page.settings.corners = corners
        self._refresh_preview()

    def _full_frame(self) -> None:
        page = self.current_page()
        if page is None:
            return
        h, w = page.original.shape[:2]
        if page.settings.rotation in (90, 270):
            h, w = w, h
        page.settings.corners = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
        self._refresh_preview()

    # ================================================================ aperçu
    def _frame_mode(self, on: bool) -> None:
        if on:
            self.btn_compare.setChecked(False)
        self.frame_bar.setVisible(on)
        self.stack.setCurrentIndex(1 if on else 0)

    def _compare_mode(self, on: bool) -> None:
        if on:
            self.btn_frame.setChecked(False)
        self.stack.setCurrentIndex(2 if on else 0)

    def _zoom_changed(self, _index: int) -> None:
        z = self.zoom.currentData()
        for v in (self.view, self.before_view, self.after_view):
            v.zoom = z
            v._render()

    def _step_zoom(self, step: int) -> None:
        idx = self.zoom.currentIndex()
        if idx == 0:
            idx = ZOOMS.index(100) + 1
        self.zoom.setCurrentIndex(max(1, min(self.zoom.count() - 1, idx + step)))

    def _small_rotated(self, page: ScanPage) -> tuple[np.ndarray, float]:
        cached = self._preview_cache.get(page.id)
        if cached is None:
            small = imaging.resize_to_max(page.original, PREVIEW_MAX_SIDE)
            scale = small.shape[1] / page.original.shape[1]
            cached = (imaging.rotate_quarter(small, page.settings.rotation), scale)
            self._preview_cache[page.id] = cached
        return cached

    def _refresh_preview(self) -> None:
        page = self.current_page()
        if page is None:
            return
        small, scale = self._small_rotated(page)
        settings = copy.deepcopy(page.settings)
        settings.rotation = 0
        if settings.corners is not None:
            settings.corners = settings.corners * scale
        kind = self.kind()
        self._token += 1
        token = self._token

        def work():
            corners = settings.corners
            if corners is None and settings.auto_detect:
                corners = imaging.detect_document(small)
            osd = ocr.detect_rotation(small) if settings.auto_orientation else 0
            settings.corners = corners
            return corners, imaging.process(small, settings, kind, osd)

        def done(res):
            if token != self._token:
                return
            corners, result = res
            self._result_cache[page.id] = result
            before = ndarray_to_pixmap(small)
            after = ndarray_to_pixmap(result)
            self.editor.set_image(before, (small.shape[1], small.shape[0]), corners)
            self.view.set_pixmap(after)
            self.before_view.set_pixmap(before)
            self.after_view.set_pixmap(after)

        if page.id not in self._result_cache:
            self.view.set_text(tr("scanner.processing"))
        run_task(Task(work), done, lambda exc: show_error(self, exc))

    # ================================================================ PDF
    def _options(self) -> OutputOptions:
        dpi, quality = self.quality.currentData()
        return OutputOptions(page_size=self.page_size.currentData(), dpi=dpi, jpeg_quality=quality,
                             ocr=self.sw_ocr.isChecked() and self.sw_ocr.isEnabled(), document_kind=self.kind(),
                             id_card_layout=self.card_layout.currentData())

    def _generate(self) -> None:
        if not self.pages:
            return
        self._sync_order()
        options = self._options()
        if options.document_kind is DocumentKind.ID_CARD and len(self.pages) > 2:
            message(self, "info", tr("scanner.card_id"), tr("scanner.card_two_max"))
        first = self.pages[0].source
        out = downloads_dir()
        default = (suggest_output_name(first, "scan", ".pdf", folder=out) if first
                   else suggest_output_name(out / "scan.pdf", "1"))
        path, _ = QFileDialog.getSaveFileName(self, tr("scanner.generate_pdf"), str(default), "PDF (*.pdf)")
        if not path:
            return
        output = Path(path) if path.lower().endswith(".pdf") else Path(path + ".pdf")
        pages = [copy.deepcopy(p) for p in self.pages]
        originals = [p.source for p in pages if p.source]

        def work(progress):
            processed = []
            for i, page in enumerate(pages):
                osd = ocr.detect_rotation(page.original) if page.settings.auto_orientation else 0
                processed.append(imaging.process(page.original, page.settings, options.document_kind, osd))
                progress(i + 1, len(pages) * 2)
            if options.document_kind is DocumentKind.ID_CARD:
                back = processed[1] if len(processed) > 1 else None
                return build_id_card_pdf(processed[0], back, output, options, originals, overwrite=True)
            return build_pdf(processed, output, options, originals,
                             progress=lambda d, t: progress(len(pages) + d, len(pages) * 2), overwrite=True)

        self._set_busy(True)
        run_task(Task(work, with_progress=True), self._generated, self._failed, self._progress)

    def _progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _generated(self, path: Path) -> None:
        self._set_busy(False)
        try:
            import pymupdf

            with pymupdf.open(path) as doc:
                detail = tr("success.pages", n=doc.page_count)
        except Exception:  # noqa: BLE001 - simple information
            detail = ""
        show_success(self, [Path(path)], detail, title=tr("success.scan_title"))

    def _failed(self, exc: Exception) -> None:
        self._set_busy(False)
        show_error(self, exc)

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.progress.setValue(0)
        for w in (self.btn_start, self.btn_add, self.btn_scan, self.gallery, self.drop):
            w.setEnabled(not busy)
