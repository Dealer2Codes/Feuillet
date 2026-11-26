"""Scanners physiques : WIA en premier, TWAIN en complément."""

from __future__ import annotations

from feuillet.core.errors import ScannerError
from feuillet.scanner.sources.base import ColorMode, DeviceInfo, ScanParams, ScanSource
from feuillet.scanner.sources.twain import TwainSource
from feuillet.scanner.sources.wia import WiaSource

__all__ = ["ColorMode", "DeviceInfo", "ScanParams", "ScanSource", "all_sources", "list_all_devices", "source_for"]


def all_sources() -> list[ScanSource]:
    return [WiaSource(), TwainSource()]


def list_all_devices() -> tuple[list[DeviceInfo], list[ScannerError]]:
    """Interroge chaque technologie ; les erreurs sont rendues, pas avalées.

    L'interface peut ainsi lister les scanners trouvés ET expliquer pourquoi
    une technologie n'a rien donné (pilote 32 bits, composant absent…).
    """
    devices: list[DeviceInfo] = []
    problems: list[ScannerError] = []
    for source in all_sources():
        if not source.is_available():
            # TWAIN est facultatif (pytwain non livré pour raison de licence) :
            # son absence n'est pas un problème à signaler à l'utilisateur.
            if source.backend == "WIA":
                problems.append(ScannerError("scanner_backend_missing", backend=source.backend))
            continue
        try:
            found = source.list_devices()
        except ScannerError as exc:
            problems.append(exc)
            continue
        devices.extend(found)
        if source.backend == "WIA" and not found:
            # Windows lui-même ne connaît aucun scanner : pilote absent,
            # appareil éteint, ou scanner réseau pas encore ajouté à Windows.
            problems.append(ScannerError("scanner_windows_none"))
    return devices, problems


def source_for(device: DeviceInfo) -> ScanSource:
    for source in all_sources():
        if source.backend == device.backend:
            return source
    raise ScannerError("scanner_backend_missing", backend=device.backend)
