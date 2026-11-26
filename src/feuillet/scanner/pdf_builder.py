"""Assemblage des pages traitées en un PDF multipage (une page par image).

- Couleur : JPEG à la qualité choisie ; niveaux de gris : JPEG 8 bits ;
  noir et blanc pur : PNG 1 bit (fichier léger, aucun artefact).
- Les images sont réduites à la résolution de sortie, jamais agrandies.
- Option OCR : couche de texte invisible superposée à chaque page.
- Mode carte d'identité : la carte est posée à taille réelle (85,60 × 53,98 mm).
"""

from __future__ import annotations

import io
import os
from collections.abc import Callable, Sequence
from pathlib import Path

import cv2
import numpy as np
import pymupdf

from feuillet.core.errors import ImageProcessingError
from feuillet.core.files import atomic_write, ensure_new_output, verify_pdf
from feuillet.scanner import ocr
from feuillet.scanner.imaging import bgr_to_pil, is_bilevel
from feuillet.scanner.models import (
    ID1_HEIGHT_MM,
    ID1_WIDTH_MM,
    IdCardLayout,
    OutputOptions,
    PageSize,
)

MM = 72 / 25.4
PAGE_SIZES_PT = {PageSize.A4: (595.28, 841.89), PageSize.LETTER: (612.0, 792.0)}

Progress = Callable[[int, int], None]


def encode_image(img: np.ndarray, quality: int) -> bytes:
    """Encode une page dans le format le plus adapté à son contenu."""
    buf = io.BytesIO()
    if img.ndim == 3 and _is_gray(img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if is_bilevel(img):
        bgr_to_pil(img).convert("1").save(buf, format="PNG", optimize=True)
    else:
        bgr_to_pil(img).save(buf, format="JPEG", quality=int(quality), optimize=True, subsampling=0 if quality >= 90 else 2)
    return buf.getvalue()


def _is_gray(img: np.ndarray) -> bool:
    sample = img[:: max(1, img.shape[0] // 300), :: max(1, img.shape[1] // 300)].astype(np.int16)
    return bool(np.abs(sample[..., 0] - sample[..., 1]).max() <= 2 and np.abs(sample[..., 1] - sample[..., 2]).max() <= 2)


def _fit(img_w: float, img_h: float, box: pymupdf.Rect) -> pymupdf.Rect:
    scale = min(box.width / img_w, box.height / img_h)
    w, h = img_w * scale, img_h * scale
    x0 = box.x0 + (box.width - w) / 2
    y0 = box.y0 + (box.height - h) / 2
    return pymupdf.Rect(x0, y0, x0 + w, y0 + h)


def _downsample(img: np.ndarray, target_w_pt: float, target_h_pt: float, dpi: int) -> np.ndarray:
    """Réduit l'image si elle dépasse la résolution voulue sur sa zone d'affichage."""
    max_w = target_w_pt / 72 * dpi
    max_h = target_h_pt / 72 * dpi
    h, w = img.shape[:2]
    s = min(max_w / w, max_h / h)
    if s >= 1:
        return img
    return cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)


def _place(page: pymupdf.Page, img: np.ndarray, rect: pymupdf.Rect, options: OutputOptions) -> None:
    img = _downsample(img, rect.width, rect.height, options.dpi)
    page.insert_image(rect, stream=encode_image(img, options.jpeg_quality))
    if options.ocr:
        h, w = img.shape[:2]
        effective_dpi = max(1, round(w / (rect.width / 72)))
        layer = pymupdf.open("pdf", ocr.text_layer_pdf(img, effective_dpi, options.ocr_languages))
        try:
            page.show_pdf_page(rect, layer, 0, overlay=True)
        finally:
            layer.close()


def _new_page(doc: pymupdf.Document, img: np.ndarray, options: OutputOptions) -> tuple[pymupdf.Page, pymupdf.Rect]:
    h, w = img.shape[:2]
    if options.page_size is PageSize.ORIGINAL:
        pw, ph = w / options.dpi * 72, h / options.dpi * 72
        page = doc.new_page(width=pw, height=ph)
        return page, page.rect
    pw, ph = PAGE_SIZES_PT[options.page_size]
    if w > h:  # page en paysage pour une image en paysage
        pw, ph = ph, pw
    page = doc.new_page(width=pw, height=ph)
    return page, _fit(w, h, page.rect)


def _save(doc: pymupdf.Document, output: Path, options: OutputOptions) -> Path:
    if options.title:
        doc.set_metadata({"title": options.title, "creator": "Feuillet", "producer": "Feuillet"})
    else:
        doc.set_metadata({"creator": "Feuillet", "producer": "Feuillet"})
    atomic_write(output, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
    verify_pdf(output)
    return output


def build_pdf(images: Sequence[np.ndarray], output: str | os.PathLike, options: OutputOptions,
              originals: Sequence[str | os.PathLike] = (), progress: Progress | None = None,
              overwrite: bool = False) -> Path:
    """Crée un PDF avec une page par image, dans l'ordre donné."""
    if not images:
        raise ImageProcessingError("no_pages")
    out = ensure_new_output(output, *originals, overwrite=overwrite)
    doc = pymupdf.open()
    try:
        for i, img in enumerate(images):
            page, rect = _new_page(doc, img, options)
            _place(page, img, rect, options)
            if progress:
                progress(i + 1, len(images))
        return _save(doc, out, options)
    finally:
        doc.close()


def build_id_card_pdf(front: np.ndarray, back: np.ndarray | None, output: str | os.PathLike,
                      options: OutputOptions, originals: Sequence[str | os.PathLike] = (),
                      overwrite: bool = False) -> Path:
    """Recto (et verso) d'une carte au format ID-1, à taille réelle sur A4/Letter."""
    out = ensure_new_output(output, *originals, overwrite=overwrite)
    size = PAGE_SIZES_PT.get(options.page_size, PAGE_SIZES_PT[PageSize.A4])
    cards = [c for c in (front, back) if c is not None]
    doc = pymupdf.open()
    try:
        if options.id_card_layout is IdCardLayout.ONE_PAGE or len(cards) == 1:
            page = doc.new_page(width=size[0], height=size[1])
            rects = _stack_cards(page.rect, cards)
            for img, rect in zip(cards, rects, strict=True):
                _place(page, img, rect, options)
        else:
            for img in cards:
                page = doc.new_page(width=size[0], height=size[1])
                _place(page, img, _stack_cards(page.rect, [img])[0], options)
        return _save(doc, out, options)
    finally:
        doc.close()


def card_size_pt(img: np.ndarray) -> tuple[float, float]:
    h, w = img.shape[:2]
    if w >= h:
        return ID1_WIDTH_MM * MM, ID1_HEIGHT_MM * MM
    return ID1_HEIGHT_MM * MM, ID1_WIDTH_MM * MM


def _stack_cards(page_rect: pymupdf.Rect, cards: list[np.ndarray]) -> list[pymupdf.Rect]:
    gap = 15 * MM
    sizes = [card_size_pt(c) for c in cards]
    total_h = sum(h for _, h in sizes) + gap * (len(sizes) - 1)
    y = max(20 * MM, (page_rect.height - total_h) / 2) if len(cards) == 1 else 30 * MM
    rects = []
    for w, h in sizes:
        x = (page_rect.width - w) / 2
        rects.append(pymupdf.Rect(x, y, x + w, y + h))
        y += h + gap
    return rects
