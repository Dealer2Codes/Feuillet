# -*- mode: python ; coding: utf-8 -*-
# Spécification PyInstaller (mode « onedir », sans console).
# Utilisation : pyinstaller installer/feuillet.spec --noconfirm
#
# Tesseract : copiez l'installation (tesseract.exe, ses DLL et tessdata avec
# fra, eng, osd) dans vendor/tesseract/ avant la construction. Elle est
# livrée dans le sous-dossier « tesseract » de l'application.

from pathlib import Path

root = Path(SPECPATH).parent
datas = [(str(root / "src" / "feuillet" / "locales"), "feuillet/locales"),
         (str(root / "src" / "feuillet" / "resources"), "feuillet/resources")]
tesseract = root / "vendor" / "tesseract"
if tesseract.is_dir():
    datas.append((str(tesseract), "tesseract"))

a = Analysis(
    [str(root / "src" / "feuillet" / "__main__.py")],
    pathex=[str(root / "src")],
    datas=datas,
    hiddenimports=["win32com.client", "pythoncom"],
    # pytwain (GPL v2 seule) est volontairement exclu : incompatible avec l'AGPL v3.
    excludes=["tkinter", "twain", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Feuillet",
    console=False,
    icon=str(root / "src" / "feuillet" / "resources" / "feuillet.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Feuillet")
