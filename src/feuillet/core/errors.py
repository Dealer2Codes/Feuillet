"""Erreurs typées de l'application.

Chaque erreur porte un code stable (clé de traduction) et des paramètres.
L'interface affiche le message traduit ; les journaux gardent le code.
"""

from __future__ import annotations


class AppError(Exception):
    """Erreur métier affichable à l'utilisateur."""

    def __init__(self, code: str, **params: object) -> None:
        self.code = code
        self.params = params
        super().__init__(f"{code} {params}" if params else code)

    def user_message(self) -> str:
        from feuillet.core.i18n import tr

        return tr(f"error.{self.code}", **self.params)


class UnsupportedPlatformError(AppError):
    pass


class InputFileError(AppError):
    pass


class OutputFileError(AppError):
    pass


class ImageProcessingError(AppError):
    pass


class OcrUnavailableError(AppError):
    pass


class ScannerError(AppError):
    pass


class WatermarkError(AppError):
    pass
