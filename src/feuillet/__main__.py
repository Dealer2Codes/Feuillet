"""Point d'entrée : ``python -m feuillet`` ou l'exécutable ``Feuillet.exe``."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _setup_logging() -> None:
    from PySide6.QtCore import QStandardPaths

    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    folder.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        # Journal limité à 3 × 1 Mo : il ne grossit jamais indéfiniment.
        handlers=[RotatingFileHandler(folder / "feuillet.log", maxBytes=1_000_000, backupCount=2,
                                      encoding="utf-8")],
    )


def main() -> int:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox

    from feuillet.core.i18n import (
        SUPPORTED_LANGUAGES,
        detect_system_language,
        set_language,
        tr,
    )
    from feuillet.core.platform_check import check_current_platform

    if sys.platform == "win32":
        # Identifiant propre : Windows groupe et affiche l'icône de Feuillet dans
        # la barre des tâches, au lieu de celle de python.exe.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Feuillet.Feuillet")

    app = QApplication(sys.argv)
    app.setOrganizationName("Feuillet")
    app.setApplicationName("Feuillet")
    _setup_logging()

    from feuillet.ui.common import app_icon
    from feuillet.ui.theme import apply_theme

    apply_theme(app)
    app.setWindowIcon(app_icon())

    lang = QSettings().value("language", detect_system_language())
    set_language(lang if lang in SUPPORTED_LANGUAGES else "fr")

    # Seconde barrière après l'installateur : Windows 10 ou 11 uniquement.
    status = check_current_platform()
    if not status.supported:
        QMessageBox.critical(None, tr("app.title"), tr(status.reason_key or "error.platform_not_windows",
                                                       name=status.name))
        return 1

    from feuillet.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
