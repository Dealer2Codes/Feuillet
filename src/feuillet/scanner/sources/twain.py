"""Acquisition par TWAIN, via la bibliothèque pytwain.

TWAIN donne accès aux pilotes constructeur (chargeur, recto-verso), mais un
processus 64 bits ne voit que les pilotes TWAIN 64 bits, que certains
constructeurs ne fournissent pas. Dans ce cas, un message explicite propose
WIA. Ce module doit être validé sur le matériel cible (preuve de concept).

Licence : pytwain est sous GPL v2 seule, incompatible avec la diffusion
de Feuillet sous AGPL v3. Il est donc optionnel (extra « twain ») et n'est
pas livré ; sans lui, ``is_available()`` renvoie False et l'interface
l'explique. Pour livrer TWAIN, il faudra une liaison ctypes propre au projet.
"""

from __future__ import annotations

import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

from feuillet.core.errors import ScannerError
from feuillet.scanner.sources.base import ColorMode, DeviceInfo, ScanParams, ScanSource

# Valeurs ICAP_PIXELTYPE de la spécification TWAIN
TWPT_BW, TWPT_GRAY, TWPT_RGB = 0, 1, 2
PIXEL_TYPE = {ColorMode.COLOR: TWPT_RGB, ColorMode.GRAYSCALE: TWPT_GRAY, ColorMode.BLACK_WHITE: TWPT_BW}


def _is_64bit() -> bool:
    return struct.calcsize("P") * 8 == 64


class TwainSource(ScanSource):
    backend = "TWAIN"

    def _module(self):
        if sys.platform != "win32":
            raise ScannerError("scanner_backend_missing", backend="TWAIN")
        try:
            import twain  # pytwain
        except ImportError as exc:
            raise ScannerError("scanner_backend_missing", backend="TWAIN") from exc
        return twain

    def is_available(self) -> bool:
        try:
            self._module()
            return True
        except ScannerError:
            return False

    def list_devices(self) -> list[DeviceInfo]:
        twain = self._module()
        try:
            with twain.SourceManager(0) as manager:
                names = list(manager.source_list)
        except Exception as exc:
            raise ScannerError("scanner_twain_dsm_missing", bits=64 if _is_64bit() else 32) from exc
        if not names and _is_64bit():
            # Cas typique : pilote constructeur disponible uniquement en 32 bits.
            raise ScannerError("scanner_twain_no_64bit_driver")
        return [DeviceInfo("TWAIN", name, name) for name in names]

    def acquire(self, device: DeviceInfo, params: ScanParams) -> list[np.ndarray]:
        from feuillet.scanner.imaging import load_images

        twain = self._module()
        pages: list[np.ndarray] = []
        with tempfile.TemporaryDirectory(prefix="feuillet-twain-") as tmp:
            # pytwain : une page par appel ; avec le chargeur on boucle jusqu'à
            # ce que le pilote ne renvoie plus d'image.
            while True:
                path = Path(tmp) / f"page{len(pages) + 1}.bmp"
                try:
                    result = twain.acquire(
                        str(path),
                        ds_name=device.id.encode("utf-8") if isinstance(device.id, str) else device.id,
                        dpi=params.dpi,
                        pixel_type=PIXEL_TYPE[params.color_mode],
                        show_ui=params.show_driver_ui,
                        parent_window=0,
                    )
                except Exception as exc:
                    if pages:
                        break
                    raise ScannerError("scanner_failed", backend="TWAIN", detail=str(exc)) from exc
                if not result or not path.is_file():
                    break
                pages.extend(load_images(path))
                if not params.use_feeder:
                    break
        if not pages:
            raise ScannerError("scanner_no_image", name=device.name)
        return pages
