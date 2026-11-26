"""Diagnostic de mise en page : liste les éléments trop larges pour leur colonne.

Usage (dans le dossier du projet) :
    .\\.venv\\Scripts\\python.exe tools\\diagnostic_layout.py

Copiez-collez le résultat : il indique précisément quel élément déborde
avec les polices et la mise à l'échelle de votre Windows.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("FEUILLET_ALLOW_UNSUPPORTED_OS", "1")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget  # noqa: E402


def describe(w: QWidget) -> str:
    text = w.text()[:45] if hasattr(w, "text") and callable(w.text) else ""
    return f"{type(w).__name__} {w.objectName()!r} {text!r}"


def culprits(root: QWidget, limit: int, depth: int = 0) -> None:
    for child in root.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        if not child.isVisible():
            continue
        m = child.minimumSizeHint().width()
        if m > limit and depth < 8:
            print(f"      {'  ' * depth}{m:4d}px  {describe(child)}")
            culprits(child, limit, depth + 1)


def main() -> None:
    app = QApplication(sys.argv)
    from feuillet.ui.main_window import MainWindow
    from feuillet.ui.theme import apply_theme

    apply_theme(app)
    f = app.font()
    screen = app.primaryScreen()
    print(f"Police : {f.family()} {f.pointSizeF()} pt / {f.pixelSize()} px ; "
          f"échelle écran : {screen.devicePixelRatio()} ; DPI logique : {screen.logicalDotsPerInch()}")
    for size in [(1024, 560), (1366, 700), (1920, 1000)]:
        window = MainWindow()
        window.resize(*size)
        window.show()
        app.processEvents()
        print(f"\n=== Fenêtre {size[0]}×{size[1]}")
        for i, name in enumerate(("Scanner", "Filigrane", "Convertir")):
            window.pages.setCurrentIndex(i)
            app.processEvents()
            page = window.page_widget(i)
            hint, room = page.minimumSizeHint(), window.pages.size()
            flag = "TROP LARGE" if hint.width() > room.width() or hint.height() > room.height() else "ok"
            print(f"  {name} : minimum {hint.width()}×{hint.height()} / place {room.width()}×{room.height()} {flag}")
            if flag != "ok":
                culprits(page, room.width() - 300)
            for scroll in page.findChildren(QScrollArea):
                inner = scroll.widget()
                if scroll.isVisible() and inner is not None:
                    need, have = inner.minimumSizeHint().width(), scroll.viewport().width()
                    if need > have + 1:
                        print(f"    colonne défilante : besoin {need}px, place {have}px")
                        culprits(inner, have - 60)
        window.close()


if __name__ == "__main__":
    main()
