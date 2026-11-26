"""Onglet Filigrane : PDF et Word, aperçu en temps réel."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from feuillet.core.errors import AppError
from feuillet.core.files import downloads_dir, suggest_output_name
from feuillet.core.i18n import tr
from feuillet.ui import theme
from feuillet.ui.common import (
    Task,
    error_text,
    pymupdf_pixmap_to_qpixmap,
    run_task,
    show_error,
)
from feuillet.ui.icons import icon
from feuillet.ui.success_dialog import show_success
from feuillet.ui.widgets import relax_widths
from feuillet.watermark.docx_watermark import apply_docx_watermark, count_sections
from feuillet.watermark.fonts import available_fonts
from feuillet.watermark.models import (
    PRESET_TEXTS,
    PageSelection,
    Position,
    SelectionMode,
    WatermarkKind,
    WatermarkSpec,
    parse_page_ranges,
)
from feuillet.watermark.pdf_watermark import (
    apply_pdf_watermark,
    open_pdf,
    render_blank_preview,
    render_preview,
)


class WatermarkTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source: Path | None = None
        self.pdf: pymupdf.Document | None = None
        self.sections = 0
        self.color = QColor(200, 30, 30)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._refresh_preview)
        self._build()
        self._update_state()

    # ================================================================ construction
    def _build(self) -> None:
        # --- fichier
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText(tr("watermark.no_file"))
        btn_open = QPushButton(icon("add_file", theme.PRIMARY, 18), tr("watermark.choose_file"))
        btn_open.clicked.connect(self._choose_file)
        self.file_info = QLabel()
        file_box = QGroupBox(tr("watermark.document"))
        fl = QVBoxLayout(file_box)
        row = QHBoxLayout()
        row.addWidget(self.file_edit, 1)
        row.addWidget(btn_open)
        fl.addLayout(row)
        fl.addWidget(self.file_info)

        # --- type
        self.rb_text = QRadioButton(tr("watermark.kind_text"))
        self.rb_image = QRadioButton(tr("watermark.kind_image"))
        self.rb_text.setChecked(True)
        kinds = QButtonGroup(self)
        kinds.addButton(self.rb_text)
        kinds.addButton(self.rb_image)
        self.rb_text.toggled.connect(self._update_state)

        # --- texte
        self.text = QComboBox()
        self.text.setEditable(True)
        self.text.addItems([*PRESET_TEXTS, tr("watermark.preset_org")])
        self.font_combo = QComboBox()
        for f in available_fonts():
            self.font_combo.addItem(f.family)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 300)
        self.size_spin.setValue(60)
        self.size_spin.setSuffix(" pt")
        self.btn_color = QPushButton()
        self.btn_color.clicked.connect(self._choose_color)
        self._paint_color_button()
        self.text_box = QGroupBox(tr("watermark.text_settings"))
        tf = QFormLayout(self.text_box)
        tf.addRow(tr("watermark.text"), self.text)
        tf.addRow(tr("watermark.font"), self.font_combo)
        tf.addRow(tr("watermark.size"), self.size_spin)
        tf.addRow(tr("watermark.color"), self.btn_color)

        # --- image
        self.image_edit = QLineEdit()
        self.image_edit.setReadOnly(True)
        btn_img = QPushButton(icon("image", theme.PRIMARY, 18), tr("watermark.choose_image"))
        btn_img.clicked.connect(self._choose_image)
        self.image_scale = QSlider(Qt.Orientation.Horizontal)
        self.image_scale.setRange(5, 100)
        self.image_scale.setValue(40)
        self.image_box = QGroupBox(tr("watermark.image_settings"))
        imf = QFormLayout(self.image_box)
        r = QHBoxLayout()
        r.addWidget(self.image_edit, 1)
        r.addWidget(btn_img)
        imf.addRow(tr("watermark.image"), r)
        imf.addRow(tr("watermark.image_size"), self.image_scale)
        png_hint = QLabel(tr("watermark.png_hint"))
        png_hint.setWordWrap(True)
        imf.addRow(png_hint)

        # --- apparence commune
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(25)
        self.angle = QSpinBox()
        self.angle.setRange(-180, 180)
        self.angle.setValue(45)
        self.angle.setSuffix(" °")
        self.position = QComboBox()
        for p in Position:
            self.position.addItem(tr(f"position.{p.value}"), p)
        self.custom_x = QDoubleSpinBox()
        self.custom_y = QDoubleSpinBox()
        for s in (self.custom_x, self.custom_y):
            s.setRange(0, 100)
            s.setValue(50)
            s.setSuffix(" %")
        self.tile = QCheckBox(tr("watermark.tile"))
        self.tile_gap = QSpinBox()
        self.tile_gap.setRange(0, 400)
        self.tile_gap.setValue(60)
        self.tile_gap.setSuffix(" pt")
        look = QGroupBox(tr("watermark.appearance"))
        lf = QFormLayout(look)
        lf.addRow(tr("watermark.opacity"), self.opacity)
        lf.addRow(tr("watermark.angle"), self.angle)
        lf.addRow(tr("watermark.position"), self.position)
        xy = QHBoxLayout()
        xy.addWidget(QLabel("X"))
        xy.addWidget(self.custom_x)
        xy.addWidget(QLabel("Y"))
        xy.addWidget(self.custom_y)
        lf.addRow(tr("watermark.custom_position"), xy)
        lf.addRow(self.tile)
        lf.addRow(tr("watermark.tile_gap"), self.tile_gap)
        # Colonne étroite : le libellé passe au-dessus du champ au lieu d'élargir la carte.
        for form in (imf, lf, tf):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        # Largeurs minimales explicites (sinon Qt réserve la place du texte le plus long).
        for w in (self.file_edit, self.image_edit, self.btn_color, self.text, self.font_combo, self.position):
            w.setMinimumWidth(90)
        for w in (self.custom_x, self.custom_y, self.size_spin, self.angle, self.tile_gap):
            w.setMinimumWidth(76)
        self.tile.setText(tr("watermark.tile"))

        # --- pages
        self.rb_all = QRadioButton(tr("watermark.pages_all"))
        self.rb_only = QRadioButton(tr("watermark.pages_only"))
        self.rb_except = QRadioButton(tr("watermark.pages_except"))
        self.rb_all.setChecked(True)
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText(tr("watermark.ranges_hint"))
        self.pages_note = QLabel()
        self.pages_note.setWordWrap(True)
        pages_box = QGroupBox(tr("watermark.pages"))
        pf = QVBoxLayout(pages_box)
        for w in (self.rb_all, self.rb_only, self.rb_except, self.ranges, self.pages_note):
            pf.addWidget(w)
        for rb in (self.rb_all, self.rb_only, self.rb_except):
            rb.toggled.connect(self._update_state)

        # --- action
        self.btn_apply = QPushButton(icon("watermark", "#FFFFFF", 18), tr("watermark.apply"))
        self.btn_apply.setObjectName("Primary")
        self.btn_apply.setMinimumHeight(46)
        self.btn_apply.setStyleSheet("font-size: 16px;")
        self.btn_apply.clicked.connect(self._apply)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        disclaimer = QLabel(tr("watermark.disclaimer"))
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: palette(mid); font-size: 11px;")

        left = QVBoxLayout()
        for w in (file_box, self.text_box, self.image_box, look, pages_box):
            left.addWidget(w)
        left.addStretch(1)
        left.addWidget(self.progress)
        left.addWidget(self.btn_apply)
        left.addWidget(disclaimer)
        inner = QWidget()
        inner.setLayout(left)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        # La colonne prend la largeur dont ses champs ont besoin : jamais rognée.
        scroll.setMinimumWidth(320)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # filet : défilement plutôt que texte coupé
        left.setContentsMargins(0, 0, 14, 0)
        for combo in (self.text, self.font_combo, self.position):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
            combo.setMinimumWidth(0)

        # --- aperçu
        self.preview = QLabel(tr("watermark.preview_empty"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(200, 240)
        self.preview.setWordWrap(True)
        self.preview.setMargin(16)
        self.preview.setStyleSheet("background: #E9EEF5; border-radius: 12px;")
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(lambda _v: self._timer.start())
        self.preview_note = QLabel()
        self.preview_note.setWordWrap(True)
        pv = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel(f"<b>{tr('watermark.preview')}</b>"))
        top.addStretch(1)
        top.addWidget(QLabel(tr("watermark.page")))
        top.addWidget(self.page_spin)
        pv.addLayout(top)
        pv.addWidget(self.preview, 1)
        pv.addWidget(self.preview_note)
        right = QWidget()
        right.setLayout(pv)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(scroll)
        split.addWidget(right)
        relax_widths(inner)
        relax_widths(right)
        split.setChildrenCollapsible(False)
        split.setStretchFactor(1, 1)
        split.setSizes([470, 700])
        split.setHandleWidth(14)
        from feuillet.ui.convert_view import _page_header

        page = QVBoxLayout(self)
        page.setContentsMargins(20, 18, 20, 18)
        page.setSpacing(14)
        page.addWidget(_page_header(tr("watermark.page_title"), tr("watermark.page_sub")))
        page.addWidget(split, 1)

        for w in (self.text, self.font_combo, self.position):
            w.currentIndexChanged.connect(self._changed)
        self.text.editTextChanged.connect(self._changed)
        for w in (self.size_spin, self.angle, self.tile_gap, self.opacity, self.image_scale):
            w.valueChanged.connect(self._changed)
        for w in (self.custom_x, self.custom_y):
            w.valueChanged.connect(self._changed)
        self.tile.toggled.connect(self._changed)
        self.position.currentIndexChanged.connect(self._update_state)

    # ================================================================ état
    @property
    def is_docx(self) -> bool:
        return bool(self.source and self.source.suffix.lower() == ".docx")

    def _update_state(self) -> None:
        is_text = self.rb_text.isChecked()
        self.text_box.setVisible(is_text)
        self.image_box.setVisible(not is_text)
        custom = self.position.currentData() is Position.CUSTOM
        self.custom_x.setEnabled(custom)
        self.custom_y.setEnabled(custom)
        self.tile.setEnabled(not self.is_docx)
        if self.is_docx:
            self.tile.setChecked(False)
            self.rb_except.setEnabled(False)
            if self.rb_except.isChecked():
                self.rb_all.setChecked(True)
            self.rb_only.setText(tr("watermark.sections_only"))
            self.pages_note.setText(tr("watermark.docx_pages_note", n=self.sections))
            self.preview_note.setText(tr("watermark.docx_preview_note"))
            self.page_spin.setEnabled(False)
        else:
            self.rb_except.setEnabled(True)
            self.rb_only.setText(tr("watermark.pages_only"))
            self.pages_note.setText("")
            self.preview_note.setText("")
            self.page_spin.setEnabled(self.pdf is not None)
        self.ranges.setEnabled(not self.rb_all.isChecked())
        self.btn_apply.setEnabled(self.source is not None)
        self._timer.start()

    def _changed(self) -> None:
        self._timer.start()

    def _paint_color_button(self) -> None:
        self.btn_color.setText(self.color.name().upper())
        self.btn_color.setStyleSheet(
            f"background:{self.color.name()}; color:{'black' if self.color.lightness() > 140 else 'white'};")

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(self.color, self, tr("watermark.color"))
        if color.isValid():
            self.color = color
            self._paint_color_button()
            self._changed()

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("watermark.choose_file"), "",
                                              f"{tr('watermark.documents')} (*.pdf *.docx)")
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        if self.pdf is not None:
            self.pdf.close()
            self.pdf = None
        try:
            if path.suffix.lower() == ".pdf":
                self.pdf = open_pdf(path)
                self.sections = 0
                self.file_info.setText(tr("watermark.pdf_info", n=self.pdf.page_count))
                self.page_spin.setMaximum(self.pdf.page_count)
            elif path.suffix.lower() == ".docx":
                self.sections = count_sections(path)
                self.file_info.setText(tr("watermark.docx_info", n=self.sections))
            else:
                raise AppError("unsupported_document", path=path.name)
        except Exception as exc:
            show_error(self, exc)
            return
        self.source = path
        self.file_edit.setText(str(path))
        self._update_state()

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("watermark.choose_image"), "",
                                              f"{tr('scanner.images')} (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self.image_edit.setText(path)
            self._changed()

    # ================================================================ modèle
    def spec(self) -> WatermarkSpec:
        return WatermarkSpec(
            kind=WatermarkKind.TEXT if self.rb_text.isChecked() else WatermarkKind.IMAGE,
            text=self.text.currentText(),
            font_name=self.font_combo.currentText(),
            font_size=float(self.size_spin.value()),
            color=(self.color.red(), self.color.green(), self.color.blue()),
            opacity=self.opacity.value() / 100,
            angle=float(self.angle.value()),
            position=self.position.currentData(),
            custom_x=self.custom_x.value() / 100,
            custom_y=self.custom_y.value() / 100,
            image_path=Path(self.image_edit.text()) if self.image_edit.text() else None,
            image_scale=self.image_scale.value() / 100,
            tile=self.tile.isChecked() and not self.is_docx,
            tile_gap=float(self.tile_gap.value()),
        )

    def selection(self) -> PageSelection:
        if self.rb_all.isChecked():
            return PageSelection()
        mode = SelectionMode.ONLY if self.rb_only.isChecked() else SelectionMode.EXCEPT
        return PageSelection(mode, self.ranges.text())

    # ================================================================ aperçu
    def _refresh_preview(self) -> None:
        try:
            spec = self.spec()
            spec.validate()
        except AppError as exc:
            self.preview.setText(error_text(exc))
            return
        try:
            if self.pdf is not None:
                index = self.page_spin.value() - 1
                selected = self._selected_pages_or_none()
                shown = spec if selected is None or index in selected else None
                pix = render_preview(self.pdf, index, shown, max_side=1100)
            else:
                pix = render_blank_preview(spec, max_side=1100)
        except Exception as exc:
            self.preview.setText(error_text(exc))
            return
        qpix = pymupdf_pixmap_to_qpixmap(pix)
        self.preview.setPixmap(qpix.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

    def _selected_pages_or_none(self) -> set[int] | None:
        if self.pdf is None or self.rb_all.isChecked() or not self.ranges.text().strip():
            return None
        try:
            return set(self.selection().resolve(self.pdf.page_count))
        except AppError:
            return None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._timer.start()

    # ================================================================ application
    def _apply(self) -> None:
        if self.source is None:
            return
        spec = self.spec()
        try:
            spec.validate()
            if self.is_docx:
                sections = None
                if not self.rb_all.isChecked():
                    sections = parse_page_ranges(self.ranges.text(), self.sections) or None
                    if sections is None:
                        raise AppError("empty_page_selection")
            else:
                self.selection().resolve(self.pdf.page_count)
        except AppError as exc:
            show_error(self, exc)
            return
        default = suggest_output_name(self.source, tr("watermark.suffix"), folder=downloads_dir())
        filt = "Word (*.docx)" if self.is_docx else "PDF (*.pdf)"
        path, _ = QFileDialog.getSaveFileName(self, tr("watermark.save_as"), str(default), filt)
        if not path:
            return
        output = Path(path)
        if output.suffix.lower() != self.source.suffix.lower():
            # Extension imposée par le format : si ce nom existe déjà, on n'écrase pas
            # un fichier que la boîte « Enregistrer sous » n'a pas signalé.
            output = output.with_suffix(self.source.suffix)
            if output.exists():
                output = suggest_output_name(output, "1")
        if output.resolve() == self.source.resolve():
            show_error(self, AppError("output_is_original", path=str(output)))
            return

        if self.is_docx:
            task = Task(apply_docx_watermark, self.source, output, spec, sections, overwrite=True)
        else:
            task = Task(apply_pdf_watermark, self.source, output, spec, self.selection(), with_progress=True,
                        overwrite=True)
        self.btn_apply.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        run_task(task, self._done, self._failed, self._progress)

    def _progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _done(self, path: Path) -> None:
        self.progress.setVisible(False)
        self.btn_apply.setEnabled(True)
        show_success(self, [Path(path)], title=tr("success.watermark_title"))

    def _failed(self, exc: Exception) -> None:
        self.progress.setVisible(False)
        self.btn_apply.setEnabled(True)
        show_error(self, exc)
