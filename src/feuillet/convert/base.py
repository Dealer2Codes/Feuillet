"""Socle du module de conversion : description des outils et des options.

Chaque outil déclare les extensions qu'il accepte, ses options (l'interface
les affiche automatiquement) et une fonction qui produit de nouveaux fichiers
dans un dossier de sortie. Les fichiers sources ne sont jamais modifiés.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from feuillet.core.errors import AppError
from feuillet.core.files import safe_filename

Progress = Callable[[int, int], None]


class ConversionError(AppError):
    pass


class Category(str, Enum):
    TO_PDF = "to_pdf"
    FROM_PDF = "from_pdf"
    IMAGES = "images"
    OFFICE = "office"
    ORGANIZE = "organize"
    OPTIMIZE = "optimize"


class OptionKind(str, Enum):
    CHOICE = "choice"
    INT = "int"
    TEXT = "text"
    PASSWORD = "password"  # noqa: S105 - type d'option, pas un mot de passe
    BOOL = "bool"
    PAGES = "pages"  # plage de pages « 1-3, 5, 8- »


@dataclass(frozen=True)
class Option:
    name: str
    kind: OptionKind
    default: Any
    choices: tuple[str, ...] = ()  # valeurs ; libellé = tr(f"convert.opt.{name}.{valeur}")
    minimum: int = 0
    maximum: int = 100
    required: bool = False


@dataclass(frozen=True)
class Tool:
    id: str
    category: Category
    inputs: tuple[str, ...]  # extensions acceptées, en minuscules avec le point
    run: Callable[..., list[Path]]
    options: tuple[Option, ...] = ()
    combine: bool = False  # True : tous les fichiers donnent un seul résultat (fusion…)
    min_files: int = 1
    available: Callable[[], str | None] = field(default=lambda: None)  # clé d'erreur si indisponible

    def accepts(self, path: Path) -> bool:
        return path.suffix.lower() in self.inputs

    def defaults(self) -> dict[str, Any]:
        return {o.name: o.default for o in self.options}


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    """Chemin libre dans ``folder`` : ``nom.ext``, puis ``nom (2).ext``…"""
    ext = ext if ext.startswith(".") else f".{ext}"
    stem = safe_filename(stem)  # un nom saisi ne peut pas sortir du dossier choisi
    candidate = folder / f"{stem}{ext}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({n}){ext}"
        n += 1
    return candidate


def unique_folder(folder: Path, name: str) -> Path:
    name = safe_filename(name)
    candidate = folder / name
    n = 2
    while candidate.exists():
        candidate = folder / f"{name} ({n})"
        n += 1
    candidate.mkdir(parents=True)
    return candidate


def check_inputs(tool: Tool, files: list[Path]) -> None:
    if len(files) < tool.min_files:
        raise ConversionError("convert_not_enough_files", n=tool.min_files)
    for f in files:
        if not f.is_file():
            raise ConversionError("convert_file_missing", path=str(f))
        if not tool.accepts(f):
            raise ConversionError("convert_wrong_type", path=f.name, types=", ".join(tool.inputs))
        if f.stat().st_size == 0:
            raise ConversionError("convert_empty_file", path=f.name)
