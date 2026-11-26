"""Filigrane sur PDF (PyMuPDF).

Le filigrane est d'abord dessiné sur une page « tampon » de même taille que
la page cible, puis superposé. Le même tampon sert à l'aperçu en temps réel
et à l'application définitive : ce que l'utilisateur voit est ce qu'il obtient.

Rappel : un filigrane est un marquage visuel. Ce n'est ni un chiffrement ni
une protection contre la copie ou la suppression.
"""

from __future__ import annotations

import io
import math
import os
from collections.abc import Callable
from pathlib import Path

import pymupdf
from PIL import Image

from feuillet.core.errors import InputFileError, WatermarkError
from feuillet.core.files import atomic_write, ensure_new_output, verify_pdf
from feuillet.watermark.fonts import font_by_family
from feuillet.watermark.models import (
    PageSelection,
    Position,
    WatermarkKind,
    WatermarkSpec,
)

Progress = Callable[[int, int], None]


# ------------------------------------------------------------------ géométrie


def rotated_size(w: float, h: float, angle: float) -> tuple[float, float]:
    a = math.radians(angle)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    return w * c + h * s, w * s + h * c


def centers(spec: WatermarkSpec, page_w: float, page_h: float, bw: float, bh: float) -> list[tuple[float, float]]:
    """Centres des filigranes sur la page (repère PDF, y vers le bas)."""
    if spec.tile:
        step_x, step_y = bw + spec.tile_gap, bh + spec.tile_gap
        pts = []
        row = 0
        y = step_y / 2 - step_y / 2
        while y <= page_h + step_y:
            offset = (step_x / 2) if row % 2 else 0.0
            x = -offset
            while x <= page_w + step_x:
                pts.append((x, y))
                x += step_x
            y += step_y
            row += 1
        return pts
    m = spec.margin
    left, right = m + bw / 2, page_w - m - bw / 2
    top, bottom = m + bh / 2, page_h - m - bh / 2
    cx, cy = page_w / 2, page_h / 2
    return [{
        Position.CENTER: (cx, cy),
        Position.TOP: (cx, top),
        Position.BOTTOM: (cx, bottom),
        Position.TOP_LEFT: (left, top),
        Position.TOP_RIGHT: (right, top),
        Position.BOTTOM_LEFT: (left, bottom),
        Position.BOTTOM_RIGHT: (right, bottom),
        Position.CUSTOM: (spec.custom_x * page_w, spec.custom_y * page_h),
    }[spec.position]]


# ------------------------------------------------------------------ dessin


def _font(spec: WatermarkSpec) -> pymupdf.Font:
    if spec.font_file:
        return pymupdf.Font(fontfile=str(spec.font_file))
    choice = font_by_family(spec.font_name)
    if choice.file:
        return pymupdf.Font(fontfile=str(choice.file))
    return pymupdf.Font(choice.pdf_name or "helv")


def _fit_font_size(spec: WatermarkSpec, font: pymupdf.Font, page_w: float, page_h: float) -> float:
    """Réduit la taille si le texte pivoté dépasse la page (jamais d'agrandissement)."""
    size = spec.font_size
    text_w = font.text_length(spec.text, size)
    text_h = size * (font.ascender - font.descender)
    bw, bh = rotated_size(text_w, text_h, spec.angle)
    avail_w, avail_h = page_w - 2 * spec.margin, page_h - 2 * spec.margin
    factor = min(1.0, avail_w / bw if bw else 1.0, avail_h / bh if bh else 1.0)
    return max(4.0, size * factor)


def _draw_text(page: pymupdf.Page, spec: WatermarkSpec) -> None:
    font = _font(spec)
    # Vérifie que la police contient tous les caractères demandés.
    missing = [ch for ch in spec.text if not ch.isspace() and not font.has_glyph(ord(ch))]
    if missing:
        raise WatermarkError("font_missing_glyphs", chars="".join(sorted(set(missing))))
    size = spec.font_size if spec.tile else _fit_font_size(spec, font, page.rect.width, page.rect.height)
    text_w = font.text_length(spec.text, size)
    asc, desc = font.ascender * size, font.descender * size
    bw, bh = rotated_size(text_w, asc - desc, spec.angle)
    color = tuple(c / 255 for c in spec.color)
    for cx, cy in centers(spec, page.rect.width, page.rect.height, bw, bh):
        writer = pymupdf.TextWriter(page.rect, opacity=spec.opacity, color=color)
        baseline = cy + (asc + desc) / 2
        writer.append((cx - text_w / 2, baseline), spec.text, font=font, fontsize=size)
        # Matrix(angle) donne une rotation anti-horaire à l'écran
        # (texte montant de gauche à droite pour 45°), comme Word.
        writer.write_text(page, morph=(pymupdf.Point(cx, cy), pymupdf.Matrix(spec.angle)))


def prepared_image(spec: WatermarkSpec) -> tuple[bytes, float]:
    """PNG pivoté avec l'opacité appliquée ; renvoie aussi son ratio hauteur/largeur
    *avant* rotation (pour dimensionner)."""
    if not spec.image_path:
        raise WatermarkError("image_missing", path="")
    try:
        with Image.open(spec.image_path) as im:
            im = im.convert("RGBA")
    except Image.DecompressionBombError as exc:
        raise WatermarkError("image_too_large", path=str(spec.image_path)) from exc
    except (OSError, ValueError) as exc:
        raise WatermarkError("image_unreadable", path=str(spec.image_path)) from exc
    ratio = im.height / im.width
    alpha = im.getchannel("A").point(lambda a: round(a * spec.opacity))
    im.putalpha(alpha)
    if spec.angle % 360:
        im = im.rotate(spec.angle, expand=True, resample=Image.BICUBIC)  # PIL : anti-horaire
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), ratio


def _draw_image(page: pymupdf.Page, spec: WatermarkSpec, png: bytes, ratio: float) -> None:
    w = spec.image_scale * page.rect.width
    h = w * ratio
    bw, bh = rotated_size(w, h, spec.angle)
    if not spec.tile:  # ne jamais dépasser la page
        factor = min(1.0, (page.rect.width - 2 * spec.margin) / bw, (page.rect.height - 2 * spec.margin) / bh)
        bw, bh = bw * factor, bh * factor
    xref = 0
    for cx, cy in centers(spec, page.rect.width, page.rect.height, bw, bh):
        rect = pymupdf.Rect(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
        if xref:
            page.insert_image(rect, xref=xref, overlay=True)
        else:
            xref = page.insert_image(rect, stream=png, overlay=True)


class StampFactory:
    """Crée (et garde en cache) une page tampon par taille de page."""

    def __init__(self, spec: WatermarkSpec) -> None:
        spec.validate()
        self.spec = spec
        self.doc = pymupdf.open()
        self._index: dict[tuple[int, int], int] = {}
        self._image = prepared_image(spec) if spec.kind is WatermarkKind.IMAGE else None

    def page_for(self, width: float, height: float) -> int:
        key = (round(width * 10), round(height * 10))
        if key not in self._index:
            page = self.doc.new_page(width=width, height=height)
            if self.spec.kind is WatermarkKind.TEXT:
                _draw_text(page, self.spec)
            else:
                _draw_image(page, self.spec, *self._image)
            self._index[key] = page.number
            # Recharge le tampon depuis sa forme sérialisée : MuPDF ne sait pas
            # greffer des objets d'un document neuf jamais enregistré.
            data = self.doc.tobytes(garbage=1)
            self.doc.close()
            self.doc = pymupdf.open("pdf", data)
        return self._index[key]

    def apply(self, page: pymupdf.Page) -> None:
        """Superpose le filigrane à la page, dans son sens d'affichage.

        ``page.rect`` est la zone visible (rotation /Rotate comprise) ; le
        tampon est dessiné dans ce sens puis contre-pivoté pour suivre la page.
        """
        visible = page.rect
        number = self.page_for(visible.width, visible.height)
        # show_pdf_page travaille dans le repère non pivoté de la page.
        target = page.rect * page.derotation_matrix
        target.normalize()
        page.show_pdf_page(target, self.doc, number, overlay=True, rotate=page.rotation)

    def close(self) -> None:
        self.doc.close()


# ------------------------------------------------------------------ API publique


def open_pdf(path: str | os.PathLike) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise InputFileError("unreadable_pdf", path=str(path)) from exc
    if not doc.is_pdf:
        doc.close()
        raise InputFileError("unreadable_pdf", path=str(path))
    if doc.needs_pass:
        doc.close()
        raise InputFileError("pdf_password_protected", path=str(path))
    return doc


def apply_pdf_watermark(source: str | os.PathLike, output: str | os.PathLike, spec: WatermarkSpec,
                        selection: PageSelection | None = None, progress: Progress | None = None,
                        overwrite: bool = False) -> Path:
    """Crée ``output`` = ``source`` + filigrane ; ``source`` n'est pas modifié."""
    out = ensure_new_output(output, source, overwrite=overwrite)
    selection = selection or PageSelection()
    doc = open_pdf(source)
    factory = StampFactory(spec)
    try:
        pages = selection.resolve(doc.page_count)
        for n, index in enumerate(pages, 1):
            factory.apply(doc[index])
            if progress:
                progress(n, len(pages))
        atomic_write(out, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
    finally:
        factory.close()
        doc.close()
    verify_pdf(out)
    return out


def render_preview(doc: pymupdf.Document, page_index: int, spec: WatermarkSpec | None,
                   max_side: int = 1000) -> pymupdf.Pixmap:
    """Image d'une page avec le filigrane, sans toucher au document ouvert."""
    tmp = pymupdf.open()
    try:
        tmp.insert_pdf(doc, from_page=page_index, to_page=page_index)
        page = tmp[0]
        if spec is not None:
            factory = StampFactory(spec)
            try:
                factory.apply(page)
            finally:
                factory.close()
        zoom = max_side / max(page.rect.width, page.rect.height)
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    finally:
        tmp.close()


def render_blank_preview(spec: WatermarkSpec, width: float = 595.28, height: float = 841.89,
                         max_side: int = 1000) -> pymupdf.Pixmap:
    """Simulation sur une page type (utilisée pour l'aperçu des documents Word)."""
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=width, height=height)
        grey = (0.8, 0.8, 0.8)
        y = 90
        while y < height - 80:
            page.draw_line((72, y), (width - 72 - (y * 7 % 120), y), color=grey, width=3)
            y += 22
        return render_preview(doc, 0, spec, max_side)
    finally:
        doc.close()
