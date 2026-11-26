# Construit l'exécutable puis l'installateur Windows.
# Prérequis : Python 3.12 64 bits, Inno Setup 6.3+ (ISCC.exe dans le PATH),
# Tesseract copié dans vendor\tesseract (voir README).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install -e . --no-deps
.\.venv\Scripts\python -m pip install "pyinstaller>=6.5,<7"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\pyinstaller installer\feuillet.spec --noconfirm --distpath dist --workpath build
ISCC.exe installer\feuillet.iss
Write-Host "Installateur : dist\installer\"
