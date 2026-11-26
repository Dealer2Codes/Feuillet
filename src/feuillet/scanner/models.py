"""Modèle de données du module Scanner.

Une page = l'image d'origine (jamais modifiée) + des réglages. L'aperçu et
l'export rejouent les réglages sur l'original : tout est réversible.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np

# Format ID-1 (cartes d'identité, cartes bancaires) : ISO/IEC 7810.
ID1_WIDTH_MM = 85.60
ID1_HEIGHT_MM = 53.98
ID1_ASPECT = ID1_WIDTH_MM / ID1_HEIGHT_MM


class EnhanceMode(str, Enum):
    ORIGINAL = "original"
    COLOR = "color"
    GRAYSCALE = "grayscale"
    BLACK_WHITE = "black_white"
    AUTO = "auto"


class DocumentKind(str, Enum):
    DOCUMENT = "document"
    ID_CARD = "id_card"


class PageSize(str, Enum):
    A4 = "A4"
    LETTER = "Letter"
    ORIGINAL = "original"  # taille de l'image à la résolution choisie


class IdCardLayout(str, Enum):
    ONE_PAGE = "one_page"
    TWO_PAGES = "two_pages"


Corners = np.ndarray  # tableau float32 (4, 2) : haut-gauche, haut-droit, bas-droit, bas-gauche


@dataclass
class PageSettings:
    rotation: int = 0  # 0, 90, 180 ou 270 (sens horaire)
    auto_detect: bool = True  # détection automatique des bords du document
    corners: Corners | None = None  # cadre manuel, coordonnées de l'image pivotée
    auto_orientation: bool = False  # orientation du texte par Tesseract (OSD)
    deskew: bool = True
    mode: EnhanceMode = EnhanceMode.AUTO
    remove_shadows: bool = True
    denoise: bool = True
    sharpen: bool = True
    preserve_color_marks: bool = True  # signatures, tampons en noir et blanc
    brightness: int = 0  # -100 .. 100
    contrast: int = 0  # -100 .. 100

    def rotate_by(self, degrees: int) -> None:
        self.rotation = (self.rotation + degrees) % 360
        self.corners = None  # le cadre manuel ne correspond plus à l'image


_ids = itertools.count(1)


@dataclass(eq=False)  # égalité par identité : une page contient une image
class ScanPage:
    original: np.ndarray  # image BGR uint8, jamais modifiée
    source: Path | None = None
    label: str = ""
    settings: PageSettings = field(default_factory=PageSettings)
    id: int = field(default_factory=lambda: next(_ids))

    def __post_init__(self) -> None:
        self.original.setflags(write=False)
        if not self.label:
            self.label = self.source.name if self.source else f"Page {self.id}"


@dataclass
class OutputOptions:
    page_size: PageSize = PageSize.A4
    dpi: int = 200
    jpeg_quality: int = 85
    ocr: bool = False
    ocr_languages: str = "fra+eng"
    document_kind: DocumentKind = DocumentKind.DOCUMENT
    id_card_layout: IdCardLayout = IdCardLayout.ONE_PAGE
    title: str = ""
