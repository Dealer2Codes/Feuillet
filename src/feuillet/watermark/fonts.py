"""Polices proposées pour les filigranes.

- Trois polices standard PDF, toujours disponibles (Helvetica, Times, Courier).
- Les polices TrueType courantes de Windows, si elles sont installées : elles
  sont incorporées au PDF et leur nom de famille est utilisé dans Word.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class FontChoice:
    family: str  # nom affiché, et nom de famille utilisé dans Word
    pdf_name: str | None = None  # police standard PDF (pas de fichier)
    file: Path | None = None  # police TrueType à incorporer


BUILTIN = (
    FontChoice("Helvetica", pdf_name="helv"),
    FontChoice("Times New Roman", pdf_name="tiro"),
    FontChoice("Courier New", pdf_name="cour"),
)

# Nom de famille -> fichiers possibles (Windows puis Linux pour le développement)
_SYSTEM_FONTS = {
    "Arial": ["arial.ttf", "LiberationSans-Regular.ttf"],
    "Arial Black": ["ariblk.ttf"],
    "Calibri": ["calibri.ttf", "Carlito-Regular.ttf"],
    "Cambria": ["cambria.ttc"],
    "Georgia": ["georgia.ttf"],
    "Segoe UI": ["segoeui.ttf"],
    "Tahoma": ["tahoma.ttf"],
    "Verdana": ["verdana.ttf", "DejaVuSans.ttf"],
    "Impact": ["impact.ttf"],
}


def _font_dirs() -> list[Path]:
    dirs = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    else:
        dirs += [Path("/usr/share/fonts"), Path.home() / ".fonts"]
    return [d for d in dirs if d.is_dir()]


def _find(filename: str) -> Path | None:
    for d in _font_dirs():
        direct = d / filename
        if direct.is_file():
            return direct
        if sys.platform != "win32":
            for hit in d.rglob(filename):
                return hit
    return None


@lru_cache(maxsize=1)
def available_fonts() -> tuple[FontChoice, ...]:
    found = []
    for family, files in _SYSTEM_FONTS.items():
        for name in files:
            path = _find(name)
            if path:
                found.append(FontChoice(family, file=path))
                break
    return (*BUILTIN, *found)


def font_by_family(family: str) -> FontChoice:
    for choice in available_fonts():
        if choice.family == family:
            return choice
    return BUILTIN[0]
