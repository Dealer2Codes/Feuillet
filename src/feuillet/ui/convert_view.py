"""Onglet Convertir : outils de conversion et de traitement PDF, à la manière d'iLovePDF."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from feuillet.convert import BY_ID, TOOLS, run_tool
from feuillet.convert.base import Category, OptionKind, Tool
from feuillet.core.files import downloads_dir
from feuillet.core.i18n import has_key, tr
from feuillet.ui import theme
from feuillet.ui.common import Task, error_text, message, run_task
from feuillet.ui.icons import icon
from feuillet.ui.success_dialog import human_size, show_success
from feuillet.ui.widgets import add_password_toggle, relax_widths

# Icône de chaque catégorie dans l'arbre des outils.
CATEGORY_ICONS = {
    "to_pdf": "pdf", "from_pdf": "convert", "images": "image", "office": "doc",
    "organize": "merge", "optimize": "compress",
}

# Icône du bouton principal : par outil, sinon par catégorie.
RUN_ICONS = {
    "compress": "compress", "protect": "lock", "unlock": "lock", "merge": "merge", "split": "merge",
    "to_pdf": "pdf", "from_pdf": "convert", "images": "image", "office": "convert",
    "organize": "check", "optimize": "check",
}


def _page_header(title: str, subtitle: str) -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(2, 0, 0, 0)
    v.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("PageTitle")
    s = QLabel(subtitle)
    s.setObjectName("PageSub")
    v.addWidget(t)
    v.addWidget(s)
    return box


class FileList(QListWidget):
    """Liste de fichiers : glisser-déposer depuis l'Explorateur et réordonnancement."""

    filesDropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.filesDropped.emit([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])
            return
        super().dropEvent(event)

    def paths(self) -> list[Path]:
        return [Path(self.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.count())]


def _run_batch(tool: Tool, files: list[Path], out_dir: Path, options: dict, progress) -> tuple[list[Path], list[str]]:
    """Fusion : un seul appel. Sinon fichier par fichier, sans s'arrêter au premier échec."""
    if tool.combine:
        return run_tool(tool.id, files, out_dir, options, progress), []
    results: list[Path] = []
    errors: list[str] = []
    for i, f in enumerate(files):
        try:
            results += run_tool(tool.id, [f], out_dir, options)
        except Exception as exc:
            errors.append(f"{f.name} : {error_text(exc)}")
        progress(i + 1, len(files))
    return results, errors


class ConvertTab(QWidget):
    toolChanged = Signal(str)  # identifiant de l'outil affiché

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tool: Tool | None = None
        self._inputs: dict[str, QWidget] = {}
        self._results: list[Path] = []
        self._ran_tool, self._ran_inputs = "", []
        self._build()
        self._select_first()

    # ================================================================ construction
    def _build(self) -> None:
        self.tree = QTreeWidget()
        self.tree.setObjectName("ToolTree")
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(200)
        self.tree.setMaximumWidth(340)
        # Sous-menus nettement décalés sous leur catégorie.
        self.tree.setIndentation(32)
        self.tree.setIconSize(QSize(18, 18))
        bold = QFont()
        bold.setBold(True)
        cat_bg = QBrush(QColor(theme.PRIMARY_SOFT))
        cat_fg = QBrush(QColor(theme.NAVY_2))
        tool_fg = QBrush(QColor(theme.MUTED))
        for category in Category:
            parent = QTreeWidgetItem([tr(f"convert.cat.{category.value}")])
            parent.setFont(0, bold)
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
            parent.setBackground(0, cat_bg)
            parent.setForeground(0, cat_fg)
            parent.setIcon(0, icon(CATEGORY_ICONS[category.value], theme.PRIMARY, 18))
            parent.setSizeHint(0, QSize(0, 34))
            self.tree.addTopLevelItem(parent)
            for tool in (t for t in TOOLS if t.category is category):
                item = QTreeWidgetItem([tr(f"convert.tool.{tool.id}")])
                item.setData(0, Qt.ItemDataRole.UserRole, tool.id)
                item.setForeground(0, tool_fg)
                item.setIcon(0, icon("dot", theme.PRIMARY, 18))
                item.setSizeHint(0, QSize(0, 28))
                missing = tool.available()
                if missing:
                    item.setForeground(0, self.palette().placeholderText())
                    item.setIcon(0, icon("dot", "#CBD5E1", 18))
                    item.setToolTip(0, tr(f"error.{missing}"))
                parent.addChild(item)
            parent.setExpanded(True)
        self.tree.currentItemChanged.connect(lambda cur, _prev: self._select(cur))

        self.title = QLabel()
        self.title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.unavailable = QLabel()
        self.unavailable.setWordWrap(True)
        self.unavailable.setStyleSheet("color: #b45309;")

        self.files = FileList()
        self.files.filesDropped.connect(self.add_files)
        self.files_hint = QLabel()
        self.files_hint.setWordWrap(True)
        self.files_hint.setStyleSheet("color: palette(mid);")
        # Boutons icône seule, côte à côte ; le libellé reste en infobulle et pour les lecteurs d'écran.
        btn_add = QPushButton(icon("add_file", theme.PRIMARY, 22), "")
        btn_remove = QPushButton(icon("remove_file", theme.DANGER, 22), "")
        btn_clear = QPushButton(icon("clear", theme.TEXT, 22), "")
        btn_add.clicked.connect(self._choose_files)
        btn_remove.clicked.connect(self._remove_selected)
        btn_clear.clicked.connect(self.files.clear)
        self.files_buttons = row = QHBoxLayout()
        row.setSpacing(8)
        for b, key in ((btn_add, "convert.add_files"), (btn_remove, "convert.remove"), (btn_clear, "convert.clear")):
            b.setToolTip(tr(key))
            b.setAccessibleName(tr(key))
            b.setObjectName("IconAction")
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(48, 40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        self.files.setMinimumHeight(110)
        files_box = QGroupBox(tr("convert.files"))
        fl = QVBoxLayout(files_box)
        fl.addWidget(self.files, 1)
        fl.addWidget(self.files_hint)
        fl.addLayout(row)

        self.options_box = QGroupBox(tr("convert.options"))
        self.options_form = QFormLayout(self.options_box)

        self.out_dir = QLineEdit(str(downloads_dir()))
        self.out_dir.setPlaceholderText(tr("convert.same_folder"))
        btn_out = QPushButton(icon("folder", theme.TEXT, 18), tr("convert.choose_folder"))
        btn_out.clicked.connect(self._choose_folder)
        out_row = QHBoxLayout()
        out_row.addWidget(self.out_dir, 1)
        out_row.addWidget(btn_out)
        out_box = QGroupBox(tr("convert.output_folder"))
        out_box.setLayout(out_row)

        self.btn_run = QPushButton()
        self.btn_run.setObjectName("Primary")
        self.btn_run.setMinimumHeight(46)
        self.btn_run.setStyleSheet("font-size: 16px;")
        self.btn_run.clicked.connect(self._run)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.ItemDataRole.UserRole))))
        self.btn_open_folder = QPushButton(icon("folder", theme.TEXT, 18), tr("convert.open_folder"))
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.btn_open_folder.setEnabled(False)
        res_box = QGroupBox(tr("convert.results"))
        rl = QVBoxLayout(res_box)
        rl.addWidget(self.results, 1)
        hint = QLabel(tr("convert.results_hint"))
        hint.setWordWrap(True)
        rl.addWidget(hint)
        rl.addWidget(self.btn_open_folder)

        self.title.setWordWrap(True)
        res_box.setMinimumWidth(220)
        self.res_box = res_box
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 10, 0)
        center.addWidget(self.title)
        center.addWidget(self.description)
        center.addWidget(self.unavailable)
        center.addWidget(files_box, 2)
        center.addWidget(self.options_box)
        center.addWidget(out_box)
        center.addWidget(self.progress)
        center.addWidget(self.btn_run)
        self.center_layout = center
        center_w = QWidget()
        center_w.setLayout(center)
        # Colonne centrale défilante : sur un petit écran, rien n'est écrasé.
        self.center_scroll = QScrollArea()
        self.center_scroll.setWidget(center_w)
        self.center_scroll.setWidgetResizable(True)
        self.center_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.center_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # filet : défilement plutôt que texte coupé
        self.center_scroll.setMinimumWidth(300)
        self.center_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")

        self.split = split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.tree)
        split.addWidget(self.center_scroll)
        split.addWidget(res_box)
        split.setChildrenCollapsible(False)
        split.setStretchFactor(1, 1)
        split.setSizes([285, 620, 300])
        split.setHandleWidth(14)
        self._results_inline = False
        relax_widths(center_w)
        relax_widths(res_box)
        page = QVBoxLayout(self)
        page.setContentsMargins(20, 18, 20, 18)
        page.setSpacing(14)
        page.addWidget(_page_header(tr("convert.page_title"), tr("convert.page_sub")))
        page.addWidget(split, 1)

    # ================================================================ adaptation à la taille
    NARROW = 980  # en dessous : « Fichiers créés » passe sous le bouton principal

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit(self.width())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit(self.width())

    def _fit(self, width: int) -> None:
        inline = width < self.NARROW
        if inline != self._results_inline:
            self._results_inline = inline
            if inline:
                self.res_box.setMinimumWidth(0)
                self.center_layout.addWidget(self.res_box)
                self.res_box.setMinimumHeight(220)
            else:
                self.res_box.setMinimumHeight(0)
                self.res_box.setMinimumWidth(220)
                self.split.addWidget(self.res_box)
                self.split.setSizes([285, max(300, width - 285 - 300), 300])

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(190 + 300 + 14 + 40, 420)

    def select_tool(self, tool_id: str) -> None:
        """Sélectionne un outil par son identifiant (raccourcis de la barre latérale)."""
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                if top.child(j).data(0, Qt.ItemDataRole.UserRole) == tool_id:
                    self.tree.setCurrentItem(top.child(j))
                    return

    def _select_first(self) -> None:
        first = self.tree.topLevelItem(0).child(0)
        self.tree.setCurrentItem(first)

    # ================================================================ outil
    def _select(self, item: QTreeWidgetItem | None) -> None:
        tool_id = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if not tool_id:
            return
        self.tool = BY_ID[tool_id]
        self.toolChanged.emit(tool_id)
        self.title.setText(tr(f"convert.tool.{tool_id}"))
        self.description.setText(tr(f"convert.desc.{tool_id}"))
        missing = self.tool.available()
        self.unavailable.setText(tr(f"error.{missing}") if missing else "")
        self.unavailable.setVisible(bool(missing))
        self.files_hint.setText(tr("convert.accepted", types=" ".join(self.tool.inputs)))
        key = f"convert.run.{tool_id}"
        self.btn_run.setText(tr(key) if has_key(key) else tr(f"convert.run.{self.tool.category.value}"))
        self.btn_run.setIcon(icon(RUN_ICONS.get(tool_id, RUN_ICONS.get(self.tool.category.value, "play")),
                                  "#FFFFFF", 20))
        self.btn_run.setIconSize(QSize(20, 20))
        self._build_options()
        relax_widths(self.options_box)
        # Retire les fichiers qui ne conviennent pas au nouvel outil.
        for i in reversed(range(self.files.count())):
            if not self.tool.accepts(Path(self.files.item(i).data(Qt.ItemDataRole.UserRole))):
                self.files.takeItem(i)
        self._update_run()

    def _build_options(self) -> None:
        while self.options_form.rowCount():
            self.options_form.removeRow(0)
        self._inputs.clear()
        assert self.tool is not None
        for opt in self.tool.options:
            label = tr(f"convert.opt.{opt.name}")
            if opt.kind is OptionKind.CHOICE:
                w = QComboBox()
                for value in opt.choices:
                    w.addItem(tr(f"convert.opt.{opt.name}.{value}"), value)
                w.setCurrentIndex(opt.choices.index(str(opt.default)))
            elif opt.kind is OptionKind.INT:
                w = QSpinBox()
                w.setRange(opt.minimum, opt.maximum)
                w.setValue(int(opt.default))
            elif opt.kind is OptionKind.BOOL:
                w = QCheckBox(label)
                w.setChecked(bool(opt.default))
                label = ""
            else:
                w = QLineEdit(str(opt.default))
                if opt.kind is OptionKind.PASSWORD:
                    add_password_toggle(w)
                if opt.kind is OptionKind.PAGES:
                    w.setPlaceholderText(tr("convert.pages_hint_required" if opt.required else "convert.pages_hint"))
                else:
                    w.setPlaceholderText(tr(f"convert.opt.{opt.name}.hint"))
                w.textChanged.connect(self._update_run)
            if label:
                self.options_form.addRow(label + (" *" if opt.required else ""), w)
            else:
                self.options_form.addRow(w)
            self._inputs[opt.name] = w
        self.options_box.setVisible(bool(self.tool.options))

    def _options(self) -> dict:
        values = {}
        for name, w in self._inputs.items():
            if isinstance(w, QComboBox):
                values[name] = w.currentData()
            elif isinstance(w, QSpinBox):
                values[name] = w.value()
            elif isinstance(w, QCheckBox):
                values[name] = w.isChecked()
            else:
                values[name] = w.text()
        return values

    # ================================================================ fichiers
    def _choose_files(self) -> None:
        if not self.tool:
            return
        pattern = " ".join(f"*{e}" for e in self.tool.inputs)
        files, _ = QFileDialog.getOpenFileNames(self, tr("convert.add_files"), "",
                                                f"{tr('convert.files')} ({pattern})")
        self.add_files([Path(f) for f in files])

    def add_files(self, paths: list[Path]) -> None:
        if not self.tool:
            return
        present = set(self.files.paths())
        rejected = []
        for p in paths:
            if p.is_dir():
                continue
            if not self.tool.accepts(p):
                rejected.append(p.name)
                continue
            if p in present:
                continue
            item = QListWidgetItem(p.name)
            item.setToolTip(str(p))
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.files.addItem(item)
        if rejected:
            message(self, "info", tr("convert.files"), tr("convert.rejected", names=", ".join(rejected),
                                                                   types=" ".join(self.tool.inputs)))
        self._update_run()

    def _remove_selected(self) -> None:
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))
        self._update_run()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("convert.output_folder"), self.out_dir.text())
        if folder:
            self.out_dir.setText(folder)

    def _update_run(self) -> None:
        ok = bool(self.tool) and not self.tool.available() and self.files.count() >= self.tool.min_files
        if ok:
            for opt in self.tool.options:
                w = self._inputs.get(opt.name)
                if opt.required and isinstance(w, QLineEdit) and not w.text().strip():
                    ok = False
        self.btn_run.setEnabled(ok)

    # ================================================================ exécution
    def _run(self) -> None:
        if not self.tool:
            return
        files = self.files.paths()
        out_dir = Path(self.out_dir.text()) if self.out_dir.text().strip() else files[0].parent
        if not out_dir.is_dir():
            message(self, "warning", tr("convert.output_folder"), tr("error.output_dir_missing", path=str(out_dir)))
            return
        self.btn_run.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._last_dir = out_dir
        self._ran_tool, self._ran_inputs = self.tool.id, list(files)
        task = Task(_run_batch, self.tool, files, out_dir, self._options(), with_progress=True)
        run_task(task, self._done, self._failed, self._progress)

    def _progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)

    def _done(self, outcome) -> None:
        results, errors = outcome
        self.progress.setVisible(False)
        self._update_run()
        for path in reversed(results):  # le plus récent lot en haut, dans l'ordre
            item = QListWidgetItem(Path(path).name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.results.insertItem(0, item)
        self.btn_open_folder.setEnabled(bool(results) or self.btn_open_folder.isEnabled())
        if errors:
            message(self, "warning", tr("convert.partial_title"),
                    tr("convert.partial", ok=len(results)) + "\n\n" + "\n".join(errors))
        elif results:
            show_success(self, [Path(r) for r in results], self._success_detail(results),
                         tr("success.convert_title", tool=tr(f"convert.tool.{self._ran_tool}")))

    def _success_detail(self, results) -> str:
        """Pour la compression : gain de taille obtenu."""
        if self._ran_tool != "compress":
            return ""
        try:
            before = sum(Path(f).stat().st_size for f in self._ran_inputs)
            after = sum(Path(r).stat().st_size for r in results)
        except OSError:
            return ""
        if before <= 0 or after >= before:
            return tr("success.compressed_none", after=human_size(after))
        percent = round(100 * (before - after) / before)
        return tr("success.compressed", percent=percent, before=human_size(before), after=human_size(after))

    def _failed(self, exc: Exception) -> None:
        self.progress.setVisible(False)
        self._update_run()
        message(self, "error", tr("app.error_title"), error_text(exc))

    def _open_folder(self) -> None:
        item = self.results.item(0)
        folder = Path(item.data(Qt.ItemDataRole.UserRole)).parent if item else getattr(self, "_last_dir", None)
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
