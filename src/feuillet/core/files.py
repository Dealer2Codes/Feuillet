"""Écriture sûre des fichiers produits.

Règles du cahier des charges :
- le fichier original n'est jamais modifié ;
- chaque export crée un nouveau fichier ;
- le fichier produit est relu pour vérifier qu'il est exploitable.
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

from feuillet.core.errors import OutputFileError

_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_FORBIDDEN = set('<>:"/\\|?*') | {chr(c) for c in range(32)}


def safe_filename(name: str, fallback: str = "document", max_len: int = 150) -> str:
    """Nom de fichier sûr sous Windows : jamais de dossier (``..``, ``C:\\…``), de caractère interdit
    ni de nom réservé (CON, NUL…). Sert pour les noms saisis par l'utilisateur."""
    cleaned = "".join("_" if ch in _FORBIDDEN else ch for ch in str(name))
    cleaned = cleaned.strip().strip(".").strip()
    cleaned = cleaned[:max_len].rstrip(". ")
    if not cleaned or set(cleaned) <= {"_"}:
        cleaned = fallback
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def safe_which(name: str) -> Path | None:
    """Comme ``shutil.which``, mais ne cherche jamais dans le dossier courant.

    Sous Windows, ``shutil.which`` regarde d'abord le dossier courant : un
    ``tesseract.exe`` ou ``soffice.exe`` déposé à côté d'un document pourrait
    être exécuté à la place du vrai programme.
    """
    exts = [""]
    if sys.platform == "win32":
        exts = [e.lower() for e in os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";") if e] or [".exe"]
        exts = [e for e in exts if e in (".exe", ".com")]  # jamais de script .bat/.cmd
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        folder = folder.strip().strip('"')
        if not folder or not os.path.isabs(folder):
            continue  # « . », entrées relatives : ignorées
        for ext in exts:
            candidate = Path(folder) / f"{name}{ext}"
            if candidate.is_file() and (sys.platform == "win32" or os.access(candidate, os.X_OK)):
                return candidate
    return None


def ensure_new_output(output: str | os.PathLike, *originals: str | os.PathLike, overwrite: bool = False) -> Path:
    """Contrôle la destination avant toute écriture."""
    out = Path(output).resolve()
    for original in originals:
        if original and Path(original).resolve() == out:
            raise OutputFileError("output_is_original", path=str(out))
    if not out.parent.is_dir():
        raise OutputFileError("output_dir_missing", path=str(out.parent))
    if out.exists() and not overwrite:
        raise OutputFileError("output_exists", path=str(out))
    return out


def replace_file(source: Path, target: Path, attempts: int = 20, delay: float = 0.1) -> None:
    """``os.replace`` tolérant aux verrous temporaires de Windows.

    Juste après l'écriture d'un fichier, l'antivirus (Windows Defender) ou
    l'indexation peuvent l'ouvrir quelques instants : le renommage échoue alors
    avec « fichier utilisé par un autre processus » (WinError 32). On réessaie
    pendant environ deux secondes avant d'abandonner.
    """
    import time

    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


def atomic_write(output: Path, writer: Callable[[Path], None]) -> Path:
    """Écrit dans un fichier temporaire du même dossier puis le renomme.

    Un export interrompu ne laisse donc jamais de fichier à moitié écrit.
    """
    fd, tmp_name = tempfile.mkstemp(prefix=".feuillet-", suffix=output.suffix, dir=output.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        writer(tmp)
        replace_file(tmp, output)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return output


def _windows_downloads() -> Path | None:
    """Chemin réel du dossier Téléchargements (il peut avoir été déplacé, ex. vers D:)."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")  # FOLDERID_Downloads
        guid = GUID(u.fields[0], u.fields[1], u.fields[2],
                    (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
        out = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value) if out.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)  # type: ignore[attr-defined]
    except Exception:
        return None


def downloads_dir() -> Path:
    """Dossier de dépôt par défaut des fichiers traités : Téléchargements de l'utilisateur."""
    override = os.environ.get("FEUILLET_OUTPUT_DIR")
    candidates = [Path(override)] if override else []
    if sys.platform == "win32":
        win = _windows_downloads()
        if win:
            candidates.append(win)
    candidates += [Path.home() / "Downloads", Path.home() / "Téléchargements"]
    for c in candidates:
        if c.is_dir():
            return c
    return Path.home()


def suggest_output_name(source: str | os.PathLike, suffix: str, extension: str | None = None,
                        folder: str | os.PathLike | None = None) -> Path:
    """``contrat.pdf`` -> ``contrat_filigrane.pdf`` (puis ``_2``, ``_3``… si besoin).

    ``folder`` : dossier de destination (par défaut, celui du fichier source).
    """
    src = Path(source)
    ext = extension or src.suffix
    base = Path(folder) if folder else src.parent
    candidate = base / f"{src.stem}_{suffix}{ext}"
    n = 2
    while candidate.exists():
        candidate = base / f"{src.stem}_{suffix}_{n}{ext}"
        n += 1
    return candidate


def verify_pdf(path: Path) -> int:
    """Rouvre le PDF produit ; renvoie son nombre de pages."""
    import pymupdf

    try:
        with pymupdf.open(path) as doc:
            if doc.page_count == 0:
                raise OutputFileError("output_invalid", path=str(path))
            doc.load_page(0)
            return doc.page_count
    except OutputFileError:
        raise
    except Exception as exc:
        raise OutputFileError("output_invalid", path=str(path)) from exc


def verify_docx(path: Path) -> None:
    """Rouvre le DOCX produit avec python-docx et contrôle l'archive."""
    import docx

    try:
        with zipfile.ZipFile(path) as zf:
            if zf.testzip() is not None:
                raise OutputFileError("output_invalid", path=str(path))
        docx.Document(str(path))
    except OutputFileError:
        raise
    except Exception as exc:
        raise OutputFileError("output_invalid", path=str(path)) from exc
