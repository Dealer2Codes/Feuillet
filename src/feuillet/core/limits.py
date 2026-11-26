"""Limites de sécurité appliquées aux fichiers ouverts.

Un fichier piégé (image « bombe de décompression » de 50 000 × 50 000 pixels,
GIF de dizaines de milliers d'images, PDF à page démesurée) ne doit pas pouvoir
épuiser la mémoire du poste : au-delà de ces limites, Feuillet refuse le fichier
avec un message clair.
"""

from __future__ import annotations

from PIL import Image

# Pillow refuse les images de plus de 2 × cette valeur (≈ 120 mégapixels, soit
# une photo de 12 000 × 10 000) et avertit au-delà de cette valeur.
MAX_IMAGE_PIXELS = 60_000_000
# Nombre maximal d'images lues dans un TIFF multipage ou un GIF/WebP animé.
MAX_FRAMES = 500


def apply() -> None:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


apply()
