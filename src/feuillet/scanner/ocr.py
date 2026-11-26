"""Reconnaissance de texte (OCR) avec Tesseract, hors ligne et facultative.

Tesseract est un programme séparé, appelé en sous-processus. Il est cherché,
dans l'ordre : variable ``FEUILLET_TESSERACT``, dossier ``tesseract`` livré
avec l'application, installations Windows habituelles, puis le PATH.

L'OCR ne modifie jamais l'image : il produit une couche de texte invisible
qui est superposée à la page dans le PDF (cahier des charges, 15.E).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np

from feuillet.core.errors import OcrUnavailableError
from feuillet.core.files import safe_which
from feuillet.scanner.imaging import bgr_to_pil

_TIMEOUT_S = 180


def _candidates() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("FEUILLET_TESSERACT")
    if env:
        paths.append(Path(env))
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    exe = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    paths += [base / "tesseract" / exe, Path(sys.executable).parent / "tesseract" / exe]
    if sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
            if root:
                paths.append(Path(root) / "Tesseract-OCR" / exe)
                paths.append(Path(root) / "Programs" / "Tesseract-OCR" / exe)
    found = safe_which("tesseract")
    if found:
        paths.append(found)
    return paths


@lru_cache(maxsize=1)
def find_tesseract() -> Path | None:
    for p in _candidates():
        if p.is_file():
            return p
    return None


def _run(args: list[str]) -> subprocess.CompletedProcess:
    exe = find_tesseract()
    if exe is None:
        raise OcrUnavailableError("ocr_not_installed")
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW : pas de console
    env = dict(os.environ)
    tessdata = exe.parent / "tessdata"
    if tessdata.is_dir() and "TESSDATA_PREFIX" not in env:
        env["TESSDATA_PREFIX"] = str(tessdata)
    env["OMP_THREAD_LIMIT"] = "1"
    try:
        return subprocess.run([str(exe), *args], capture_output=True, timeout=_TIMEOUT_S,
                              creationflags=flags, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise OcrUnavailableError("ocr_timeout") from exc
    except OSError as exc:
        raise OcrUnavailableError("ocr_failed", detail=str(exc)) from exc


@lru_cache(maxsize=1)
def available_languages() -> tuple[str, ...]:
    if find_tesseract() is None:
        return ()
    result = _run(["--list-langs"])
    text = (result.stdout or b"").decode("utf-8", "replace")
    return tuple(line.strip() for line in text.splitlines()[1:] if line.strip())


def is_available(languages: str = "fra+eng") -> bool:
    langs = set(available_languages())
    return bool(langs) and all(lang in langs for lang in languages.split("+"))


def _write_png(img: np.ndarray, folder: Path, dpi: int) -> Path:
    path = folder / "page.png"
    bgr_to_pil(img).save(path, dpi=(dpi, dpi))
    return path


def text_layer_pdf(img: np.ndarray, dpi: int, languages: str = "fra+eng") -> bytes:
    """PDF d'une page contenant uniquement le texte reconnu, invisible.

    La page mesure ``largeur_px / dpi`` pouces : elle se superpose exactement à
    l'image placée à la même résolution.
    """
    if not is_available(languages):
        raise OcrUnavailableError("ocr_language_missing", languages=languages)
    with tempfile.TemporaryDirectory(prefix="feuillet-ocr-") as tmp:
        folder = Path(tmp)
        src = _write_png(img, folder, dpi)
        out_base = folder / "out"
        result = _run([str(src), str(out_base), "-l", languages, "--dpi", str(dpi),
                       "-c", "textonly_pdf=1", "pdf"])
        pdf = out_base.with_suffix(".pdf")
        if result.returncode != 0 or not pdf.is_file():
            raise OcrUnavailableError("ocr_failed", detail=(result.stderr or b"").decode("utf-8", "replace")[-300:])
        return pdf.read_bytes()


def extract_text(img: np.ndarray, languages: str = "fra+eng", dpi: int = 300) -> str:
    if not is_available(languages):
        raise OcrUnavailableError("ocr_language_missing", languages=languages)
    with tempfile.TemporaryDirectory(prefix="feuillet-ocr-") as tmp:
        src = _write_png(img, Path(tmp), dpi)
        result = _run([str(src), "stdout", "-l", languages, "--dpi", str(dpi)])
        if result.returncode != 0:
            raise OcrUnavailableError("ocr_failed", detail=(result.stderr or b"").decode("utf-8", "replace")[-300:])
        return result.stdout.decode("utf-8", "replace")


def detect_rotation(img: np.ndarray) -> int:
    """Rotation horaire (0/90/180/270) à appliquer pour remettre le texte droit.

    Renvoie 0 si l'OSD n'est pas installé ou si la détection est peu sûre.
    """
    if "osd" not in available_languages():
        return 0
    with tempfile.TemporaryDirectory(prefix="feuillet-osd-") as tmp:
        src = _write_png(img, Path(tmp), 300)
        result = _run([str(src), "stdout", "--psm", "0", "-l", "osd"])
    text = (result.stdout or b"").decode("utf-8", "replace")
    rotate = re.search(r"Rotate:\s*(\d+)", text)
    confidence = re.search(r"Orientation confidence:\s*([\d.]+)", text)
    if result.returncode != 0 or not rotate:
        return 0
    if confidence and float(confidence.group(1)) < 2.0:
        return 0
    return int(rotate.group(1)) % 360
