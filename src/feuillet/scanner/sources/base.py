"""Interface commune des scanners physiques (WIA, TWAIN).

Le module scanner ne produit que des images : elles rejoignent la galerie du
module Scanner d'images, qui reste seul responsable de l'assemblage du PDF.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import numpy as np


class ColorMode(str, Enum):
    COLOR = "color"
    GRAYSCALE = "grayscale"
    BLACK_WHITE = "black_white"


@dataclass(frozen=True)
class DeviceInfo:
    backend: str  # "WIA" ou "TWAIN"
    id: str
    name: str


@dataclass(frozen=True)
class ScanParams:
    dpi: int = 300
    color_mode: ColorMode = ColorMode.COLOR
    use_feeder: bool = False  # chargeur automatique : plusieurs pages d'un coup
    show_driver_ui: bool = False


class ScanSource(ABC):
    backend: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Le composant système nécessaire est-il présent ?"""

    @abstractmethod
    def list_devices(self) -> list[DeviceInfo]:
        """Périphériques détectés ; lève ``ScannerError`` en cas de problème."""

    @abstractmethod
    def acquire(self, device: DeviceInfo, params: ScanParams) -> list[np.ndarray]:
        """Numérise une ou plusieurs pages ; images BGR uint8."""
