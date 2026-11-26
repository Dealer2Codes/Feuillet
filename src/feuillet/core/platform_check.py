"""Vérification du système : l'application ne prend en charge que Windows 10 et 11.

Windows 10 et Windows 11 annoncent tous deux la version 10.0 ; on les
distingue par le numéro de build (Windows 11 commence au build 22000).
Le même contrôle est fait par l'installateur (``installer/feuillet.iss``).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

WIN10_FIRST_BUILD = 10240
WIN11_FIRST_BUILD = 22000

#: Variable d'environnement réservée au développement sur Linux/macOS.
DEV_OVERRIDE_ENV = "FEUILLET_ALLOW_UNSUPPORTED_OS"


@dataclass(frozen=True)
class PlatformStatus:
    supported: bool
    name: str
    reason_key: str | None = None


def evaluate(platform: str, major: int = 0, minor: int = 0, build: int = 0) -> PlatformStatus:
    """Fonction pure, testable sur tout système."""
    if platform != "win32":
        return PlatformStatus(False, platform, "error.platform_not_windows")
    if major < 10 or (major == 10 and build < WIN10_FIRST_BUILD):
        return PlatformStatus(False, f"Windows {major}.{minor} (build {build})", "error.platform_windows_too_old")
    name = "Windows 11" if build >= WIN11_FIRST_BUILD else "Windows 10"
    return PlatformStatus(True, f"{name} (build {build})")


def check_current_platform() -> PlatformStatus:
    if sys.platform == "win32":
        v = sys.getwindowsversion()
        status = evaluate("win32", v.major, v.minor, v.build)
    else:
        status = evaluate(sys.platform)
    if not status.supported and os.environ.get(DEV_OVERRIDE_ENV) == "1":
        return PlatformStatus(True, f"{status.name} (mode développement)")
    return status
