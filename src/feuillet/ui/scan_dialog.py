"""Boîte de dialogue « Numériser depuis un scanner » (WIA / TWAIN)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from feuillet.core.i18n import tr
from feuillet.scanner import sources
from feuillet.scanner.sources import ColorMode, ScanParams
from feuillet.ui.common import Task, error_text, localize_buttons, run_task, show_error


class ScanDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("scan.title"))
        self.setMinimumWidth(460)
        self.images: list = []
        self._devices: list = []

        self.device = QComboBox()
        self.refresh = QPushButton(tr("scan.refresh"))
        self.dpi = QComboBox()
        for dpi in (150, 200, 300, 600):
            self.dpi.addItem(f"{dpi} DPI", dpi)
        self.dpi.setCurrentIndex(2)
        self.color = QComboBox()
        self.color.addItem(tr("mode.color"), ColorMode.COLOR)
        self.color.addItem(tr("mode.grayscale"), ColorMode.GRAYSCALE)
        self.color.addItem(tr("mode.black_white"), ColorMode.BLACK_WHITE)
        self.feeder = QCheckBox(tr("scan.feeder"))
        self.driver_ui = QCheckBox(tr("scan.driver_ui"))
        self.status = QLabel()
        self.status.setWordWrap(True)

        form = QFormLayout()
        form.addRow(tr("scan.device"), self.device)
        form.addRow("", self.refresh)
        form.addRow(tr("scan.resolution"), self.dpi)
        form.addRow(tr("scan.color_mode"), self.color)
        form.addRow("", self.feeder)
        form.addRow("", self.driver_ui)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        localize_buttons(self.buttons)
        self.scan_button = self.buttons.addButton(tr("scan.start"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.rejected.connect(self.reject)
        self.scan_button.clicked.connect(self._scan)
        self.refresh.clicked.connect(self._load_devices)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)
        self._load_devices()

    def _busy(self, busy: bool, message: str = "") -> None:
        for w in (self.device, self.refresh, self.dpi, self.color, self.feeder, self.driver_ui, self.scan_button):
            w.setEnabled(not busy)
        if message:
            self.status.setText(message)

    def _load_devices(self) -> None:
        self._busy(True, tr("scan.searching"))
        run_task(Task(sources.list_all_devices), self._devices_loaded, self._failed)

    def _devices_loaded(self, result) -> None:
        devices, problems = result
        self._devices = devices
        self.device.clear()
        for d in devices:
            self.device.addItem(f"{d.name} ({d.backend})", d)
        self._busy(False)
        lines = [] if devices else [tr("scan.none_found")]
        lines += [f"• {error_text(p)}" for p in problems]
        self.status.setText("\n".join(lines))
        self.scan_button.setEnabled(bool(devices))

    def _scan(self) -> None:
        device = self.device.currentData()
        if device is None:
            return
        params = ScanParams(dpi=self.dpi.currentData(), color_mode=self.color.currentData(),
                            use_feeder=self.feeder.isChecked(), show_driver_ui=self.driver_ui.isChecked())
        self._busy(True, tr("scan.in_progress"))
        source = sources.source_for(device)
        run_task(Task(source.acquire, device, params), self._scanned, self._failed)

    def _scanned(self, images) -> None:
        self.images = images
        self._busy(False)
        self.accept()

    def _failed(self, exc: Exception) -> None:
        self._busy(False, error_text(exc))
        self.scan_button.setEnabled(bool(self._devices))
        show_error(self, exc)
