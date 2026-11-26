"""Paramètres d'un filigrane et sélection des pages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from feuillet.core.errors import WatermarkError

PRESET_TEXTS = ("CONFIDENTIEL", "DOCUMENT ORIGINAL", "COPIE", "BROUILLON", "NE PAS DIFFUSER")


class WatermarkKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"


class Position(str, Enum):
    CENTER = "center"
    TOP = "top"
    BOTTOM = "bottom"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CUSTOM = "custom"


@dataclass
class WatermarkSpec:
    kind: WatermarkKind = WatermarkKind.TEXT
    text: str = "CONFIDENTIEL"
    font_name: str = "Helvetica"  # nom de police standard ou chemin d'un fichier .ttf/.otf
    font_file: Path | None = None
    font_size: float = 60.0  # points
    color: tuple[int, int, int] = (200, 30, 30)  # RVB 0-255
    opacity: float = 0.25  # 0 (invisible) à 1 (opaque)
    angle: float = 45.0  # degrés, sens anti-horaire
    position: Position = Position.CENTER
    custom_x: float = 0.5  # position personnalisée : fraction de la largeur (centre du filigrane)
    custom_y: float = 0.5  # fraction de la hauteur, depuis le haut
    margin: float = 36.0  # points, pour les positions sur les bords
    image_path: Path | None = None
    image_scale: float = 0.4  # largeur de l'image en fraction de la largeur de page
    tile: bool = False  # répétition sur toute la page
    tile_gap: float = 60.0  # espace entre répétitions, en points

    def validate(self) -> None:
        if self.kind is WatermarkKind.TEXT and not self.text.strip():
            raise WatermarkError("empty_text")
        if self.kind is WatermarkKind.IMAGE and (not self.image_path or not Path(self.image_path).is_file()):
            raise WatermarkError("image_missing", path=str(self.image_path or ""))
        if not 0 < self.opacity <= 1:
            raise WatermarkError("invalid_opacity")
        if not 4 <= self.font_size <= 400:
            raise WatermarkError("invalid_font_size")
        if self.font_file and not Path(self.font_file).is_file():
            raise WatermarkError("font_missing", path=str(self.font_file))

    @property
    def color_hex(self) -> str:
        return "{:02X}{:02X}{:02X}".format(*self.color)


class SelectionMode(str, Enum):
    ALL = "all"
    ONLY = "only"  # uniquement les pages listées
    EXCEPT = "except"  # toutes sauf les pages listées


_RANGE = re.compile(r"^\s*(\d*)\s*(-\s*(\d*))?\s*$")


def parse_page_ranges(spec: str, total: int) -> list[int]:
    """« 1-3, 5, 8- » -> numéros 1 à n (triés, sans doublon).

    ``8-`` va jusqu'à la dernière page, ``-3`` part de la première.
    """
    pages: set[int] = set()
    if not spec.strip():
        return []
    for part in spec.replace(";", ",").split(","):
        if not part.strip():
            continue
        m = _RANGE.match(part)
        if not m or (not m.group(1) and not m.group(3) and not m.group(2)):
            raise WatermarkError("invalid_page_range", value=part.strip())
        start = int(m.group(1)) if m.group(1) else 1
        end = (int(m.group(3)) if m.group(3) else total) if m.group(2) else start
        if start < 1 or end < start:
            raise WatermarkError("invalid_page_range", value=part.strip())
        if start > total:
            raise WatermarkError("page_out_of_range", value=part.strip(), total=total)
        pages.update(range(start, min(end, total) + 1))
    return sorted(pages)


@dataclass
class PageSelection:
    mode: SelectionMode = SelectionMode.ALL
    ranges: str = ""

    def resolve(self, total: int) -> list[int]:
        """Indices de pages (base 0) à filigraner."""
        if self.mode is SelectionMode.ALL:
            return list(range(total))
        listed = {p - 1 for p in parse_page_ranges(self.ranges, total)}
        if not listed:
            raise WatermarkError("empty_page_selection")
        if self.mode is SelectionMode.ONLY:
            return sorted(listed)
        result = [i for i in range(total) if i not in listed]
        if not result:
            raise WatermarkError("empty_page_selection")
        return result
