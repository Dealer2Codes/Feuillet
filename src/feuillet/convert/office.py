"""Conversions bureautiques hors ligne : Microsoft Office si présent, sinon LibreOffice.

- Microsoft Office (Word, Excel, PowerPoint) est piloté par COM, dans une
  instance séparée (DispatchEx) : les documents déjà ouverts par l'utilisateur
  ne sont pas touchés, et l'instance est fermée après usage.
- LibreOffice est appelé en ligne de commande (``soffice --headless``) avec
  un profil temporaire, pour ne pas entrer en conflit avec une fenêtre ouverte.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from functools import cache, lru_cache
from pathlib import Path

from feuillet.convert.base import ConversionError, Progress, unique_path
from feuillet.core.files import safe_which

WORD_EXT = (".doc", ".docx", ".odt", ".rtf", ".dot", ".dotx")
EXCEL_EXT = (".xls", ".xlsx", ".ods", ".csv", ".xlsm")
POWERPOINT_EXT = (".ppt", ".pptx", ".odp", ".pps", ".ppsx")
OFFICE_EXT = WORD_EXT + EXCEL_EXT + POWERPOINT_EXT

# Formats de sortie proposés pour chaque famille de documents.
TARGETS = {
    "word": ("pdf", "docx", "doc", "odt", "rtf", "txt"),
    "excel": ("pdf", "xlsx", "xls", "ods", "csv"),
    "powerpoint": ("pdf", "pptx", "ppt", "odp"),
}

# Codes FileFormat de Microsoft Office (énumérations WdSaveFormat, XlFileFormat, PpSaveAsFileType).
_WORD_FORMATS = {"pdf": 17, "docx": 16, "doc": 0, "odt": 23, "rtf": 6, "txt": 7}
_EXCEL_FORMATS = {"xlsx": 51, "xls": 56, "ods": 60, "csv": 62}
_PPT_FORMATS = {"pdf": 32, "pptx": 24, "ppt": 1, "odp": 35}

_TIMEOUT_S = 300
_CREATE_NO_WINDOW = 0x08000000
# msoAutomationSecurityForceDisable : aucune macro (AutoOpen, Workbook_Open…) ne s'exécute
# à l'ouverture d'un document par automatisation. Réglage limité à cette instance.
_FORCE_DISABLE_MACROS = 3
# Mot de passe factice : un document protégé échoue immédiatement au lieu d'ouvrir
# une boîte de dialogue invisible qui bloquerait Office indéfiniment.
_NO_PASSWORD = "feuillet-no-password-7f3c"  # noqa: S105 - leurre volontairement faux


def family(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in WORD_EXT:
        return "word"
    if ext in EXCEL_EXT:
        return "excel"
    if ext in POWERPOINT_EXT:
        return "powerpoint"
    raise ConversionError("convert_wrong_type", path=path.name, types=", ".join(OFFICE_EXT))


# ------------------------------------------------------------------ détection


@lru_cache(maxsize=1)
def find_libreoffice() -> Path | None:
    env = os.environ.get("FEUILLET_SOFFICE")
    candidates = [Path(env)] if env else []
    if sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.environ.get("LOCALAPPDATA")):
            if root:
                candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
                candidates.append(Path(root) / "Programs" / "LibreOffice" / "program" / "soffice.exe")
        try:
            import winreg

            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\LibreOffice\UNO\InstallPath") as key:
                        candidates.append(Path(winreg.QueryValueEx(key, "")[0]) / "soffice.exe")
                except OSError:
                    pass
        except ImportError:
            pass
    for name in ("soffice", "libreoffice"):
        found = safe_which(name)
        if found:
            candidates.append(found)
    return next((c for c in candidates if c.is_file()), None)


@cache
def has_ms_office(app: str) -> bool:
    """``app`` : "Word", "Excel" ou "PowerPoint". Lecture du registre, sans lancer l'application."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{app}.Application\\CLSID"):
            return True
    except OSError:
        return False


_APP = {"word": "Word", "excel": "Excel", "powerpoint": "PowerPoint"}


def engine_for(fam: str, preference: str = "auto") -> str:
    """Renvoie "msoffice" ou "libreoffice", ou lève une erreur explicite."""
    ms = has_ms_office(_APP[fam])
    lo = find_libreoffice() is not None
    if preference == "msoffice" and ms:
        return "msoffice"
    if preference == "libreoffice" and lo:
        return "libreoffice"
    if preference == "auto":
        if ms:
            return "msoffice"
        if lo:
            return "libreoffice"
    raise ConversionError("convert_no_office_engine", app=_APP[fam])


def office_unavailable() -> str | None:
    if find_libreoffice() or any(has_ms_office(a) for a in _APP.values()):
        return None
    return "convert_no_office_engine_any"


# ------------------------------------------------------------------ LibreOffice


def _libreoffice(source: Path, target: str, out_dir: Path) -> Path:
    soffice = find_libreoffice()
    if soffice is None:
        raise ConversionError("convert_no_office_engine", app="LibreOffice")
    with tempfile.TemporaryDirectory(prefix="feuillet-lo-") as tmp:
        tmp_path = Path(tmp)
        profile = (tmp_path / "profile").as_uri()
        filt = target
        if target == "txt":
            filt = "txt:Text (encoded):UTF8"
        elif target == "csv":
            filt = "csv:Text - txt - csv (StarCalc):44,34,76"
        cmd = [str(soffice), f"-env:UserInstallation={profile}", "--headless", "--norestore", "--nologo",
               "--nodefault", "--nolockcheck", "--convert-to", filt, "--outdir", str(tmp_path / "out"),
               str(source.resolve())]  # chemin absolu : ne peut pas être pris pour une option « -… »
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_S, check=False,
                                    creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError("convert_timeout", path=source.name) from exc
        produced = list((tmp_path / "out").glob(f"*.{target}")) if (tmp_path / "out").is_dir() else []
        if result.returncode != 0 or not produced:
            detail = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()[-300:]
            raise ConversionError("convert_failed", path=source.name, detail=detail or "LibreOffice")
        out = unique_path(out_dir, source.stem, f".{target}")
        shutil.move(str(produced[0]), out)
        return out


# ------------------------------------------------------------------ Microsoft Office


def _ms_office(source: Path, target: str, out_dir: Path) -> Path:
    import pythoncom
    import win32com.client

    fam = family(source)
    out = unique_path(out_dir, source.stem, f".{target}")
    src, dst = str(source.resolve()), str(out.resolve())
    pythoncom.CoInitialize()
    app = None
    try:
        if fam == "word":
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            app.AutomationSecurity = _FORCE_DISABLE_MACROS
            doc = app.Documents.Open(src, ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False,
                                     Visible=False, PasswordDocument=_NO_PASSWORD, NoEncodingDialog=True)
            try:
                if target == "pdf":
                    doc.ExportAsFixedFormat(dst, 17, OpenAfterExport=False, OptimizeFor=0,
                                            CreateBookmarks=1, DocStructureTags=True)
                else:
                    doc.SaveAs2(dst, FileFormat=_WORD_FORMATS[target], AddToRecentFiles=False)
            finally:
                doc.Close(SaveChanges=False)
        elif fam == "excel":
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            app.AutomationSecurity = _FORCE_DISABLE_MACROS
            app.EnableEvents = False
            wb = app.Workbooks.Open(src, UpdateLinks=0, ReadOnly=True, AddToMru=False,
                                    Password=_NO_PASSWORD, IgnoreReadOnlyRecommended=True, Notify=False)
            try:
                if target == "pdf":
                    wb.ExportAsFixedFormat(0, dst, Quality=0, IncludeDocProperties=True,
                                           IgnorePrintAreas=False, OpenAfterPublish=False)
                else:
                    wb.SaveAs(dst, FileFormat=_EXCEL_FORMATS[target], AddToMru=False)
            finally:
                wb.Close(SaveChanges=False)
        else:
            app = win32com.client.DispatchEx("PowerPoint.Application")
            app.AutomationSecurity = _FORCE_DISABLE_MACROS
            app.DisplayAlerts = 1  # ppAlertsNone
            pres = app.Presentations.Open(src, ReadOnly=True, Untitled=False, WithWindow=False)
            try:
                pres.SaveAs(dst, _PPT_FORMATS[target])
            finally:
                pres.Close()
    except ConversionError:
        raise
    except Exception as exc:
        out.unlink(missing_ok=True)
        raise ConversionError("convert_failed", path=source.name, detail=str(exc)[-300:]) from exc
    finally:
        if app is not None:
            with contextlib.suppress(Exception):
                app.Quit()
        pythoncom.CoUninitialize()
    if not out.is_file():
        raise ConversionError("convert_failed", path=source.name, detail="Microsoft Office")
    return out


# ------------------------------------------------------------------ API


_ZIP_EXT = {".docx", ".dotx", ".xlsx", ".xlsm", ".pptx", ".ppsx", ".odt", ".ods", ".odp"}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # .doc/.xls/.ppt, et OOXML chiffré


def check_office_content(source: Path) -> None:
    """Refuse un fichier dont le contenu ne correspond manifestement pas à son extension.

    Sans ce contrôle, LibreOffice ouvre n'importe quel fichier comme du texte brut et
    produit un PDF rempli de caractères illisibles au lieu de signaler l'erreur.
    """
    with open(source, "rb") as fh:
        head = fh.read(4096)
    ext = source.suffix.lower()
    if head.startswith(_OLE_MAGIC):
        ok = ext not in (".rtf", ".csv")
    elif ext in _ZIP_EXT:
        ok = head.startswith(b"PK\x03\x04")
    elif ext == ".rtf":
        ok = head.lstrip().startswith(b"{\\rtf")
    else:
        # .doc/.xls/.ppt/.csv peuvent légitimement être du RTF, du HTML ou du texte ;
        # seul un contenu binaire inconnu (octets nuls) est refusé.
        ok = b"\x00" not in head
    if not ok:
        raise ConversionError("convert_not_document", path=source.name)


def convert_office(source: Path, target: str, out_dir: Path, preference: str = "auto") -> Path:
    fam = family(source)
    check_office_content(source)
    if target not in TARGETS[fam]:
        raise ConversionError("convert_unsupported_format", fmt=target)
    if source.suffix.lower().lstrip(".") == target:
        raise ConversionError("convert_same_format", fmt=target)
    engine = engine_for(fam, preference)
    ms_formats = {"word": _WORD_FORMATS, "excel": {**_EXCEL_FORMATS, "pdf": 0}, "powerpoint": _PPT_FORMATS}[fam]
    if engine == "msoffice" and target in ms_formats:
        return _ms_office(source, target, out_dir)
    return _libreoffice(source, target, out_dir)


def run_office_to_pdf(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    results = []
    for i, f in enumerate(files, 1):
        results.append(convert_office(f, "pdf", out_dir, options.get("engine", "auto")))
        if progress:
            progress(i, len(files))
    return results


def run_office_convert(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """Conversion entre formats bureautiques ; ``options["format"]`` doit convenir à la famille."""
    results = []
    for i, f in enumerate(files, 1):
        target = options["format"]
        fam = family(f)
        if target not in TARGETS[fam]:
            raise ConversionError("convert_incompatible_target", path=f.name, fmt=target)
        results.append(convert_office(f, target, out_dir, options.get("engine", "auto")))
        if progress:
            progress(i, len(files))
    return results
