"""Outils PDF (PyMuPDF) : organiser, optimiser, sécuriser, convertir depuis/vers PDF."""

from __future__ import annotations

import html
import io
import secrets
from pathlib import Path

import pymupdf

from feuillet.convert.base import ConversionError, Progress, unique_folder, unique_path
from feuillet.core.errors import AppError
from feuillet.core.files import replace_file
from feuillet.watermark.models import parse_page_ranges

# ------------------------------------------------------------------ utilitaires

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 40  # limite du format PDF (PyMuPDF)
# Plafond de pixels d'une page rendue (≈ A4 à 1200 dpi) : un PDF piégé avec une
# page de plusieurs mètres ne peut pas épuiser la mémoire.
MAX_RENDER_PIXELS = 140_000_000


def render_page(page: pymupdf.Page, dpi: int, alpha: bool = False) -> pymupdf.Pixmap:
    """``page.get_pixmap`` avec une résolution réduite si la page est démesurée."""
    rect = page.rect
    zoom = dpi / 72
    pixels = rect.width * zoom * rect.height * zoom
    if pixels > MAX_RENDER_PIXELS:
        zoom *= (MAX_RENDER_PIXELS / pixels) ** 0.5
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=alpha)



def open_pdf(path: Path, password: str = "") -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ConversionError("unreadable_pdf", path=str(path)) from exc
    if not doc.is_pdf:
        doc.close()
        raise ConversionError("unreadable_pdf", path=str(path))
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise ConversionError("convert_wrong_password" if password else "pdf_password_protected", path=path.name)
    return doc


def _save(doc: pymupdf.Document, out: Path, **kwargs) -> Path:
    tmp = out.with_name(f".{out.name}.tmp")
    try:
        doc.save(tmp, garbage=3, deflate=True, **kwargs)
        replace_file(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    with pymupdf.open(out) as check:  # relecture
        if check.page_count == 0 and not check.needs_pass:
            raise ConversionError("output_invalid", path=str(out))
    return out


def pages_from(spec: str, total: int) -> list[int]:
    """Plage « 1-3, 5 » -> indices base 0 ; vide = toutes les pages."""
    if not spec.strip():
        return list(range(total))
    try:
        return [p - 1 for p in parse_page_ranges(spec, total)]
    except AppError as exc:
        raise ConversionError(exc.code, **exc.params) from exc


def _tick(progress: Progress | None, done: int, total: int) -> None:
    if progress:
        progress(done, total)


# ------------------------------------------------------------------ organiser


def merge(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    out = unique_path(out_dir, options.get("name") or f"{files[0].stem}_fusion", ".pdf")
    result = pymupdf.open()
    try:
        for i, f in enumerate(files, 1):
            with open_pdf(f) as src:
                result.insert_pdf(src)
            _tick(progress, i, len(files))
        return [_save(result, out)]
    finally:
        result.close()


def split(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    results: list[Path] = []
    for f in files:
        with open_pdf(f) as doc:
            total = doc.page_count
            mode = options["mode"]
            if mode == "every_page":
                groups = [[i] for i in range(total)]
            elif mode == "every_n":
                n = max(1, int(options["every"]))
                groups = [list(range(i, min(i + n, total))) for i in range(0, total, n)]
            else:  # ranges : chaque plage séparée par une virgule devient un fichier
                groups = [pages_from(part, total) for part in options["ranges"].split(",") if part.strip()]
                if not groups:
                    raise ConversionError("empty_page_selection")
            folder = unique_folder(out_dir, f"{f.stem}_parties")
            for k, group in enumerate(groups, 1):
                part = pymupdf.open()
                try:
                    for p in group:
                        part.insert_pdf(doc, from_page=p, to_page=p)
                    label = f"{group[0] + 1}" if len(group) == 1 else f"{group[0] + 1}-{group[-1] + 1}"
                    results.append(_save(part, unique_path(folder, f"{f.stem}_p{label}", ".pdf")))
                finally:
                    part.close()
                _tick(progress, k, len(groups))
    return results


def _select(files: list[Path], out_dir: Path, options: dict, suffix: str, keep: bool,
            progress: Progress | None) -> list[Path]:
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            chosen = pages_from(options["pages"], doc.page_count)
            if not options["pages"].strip():
                raise ConversionError("empty_page_selection")
            keep_pages = chosen if keep else [p for p in range(doc.page_count) if p not in set(chosen)]
            if not keep_pages:
                raise ConversionError("empty_page_selection")
            doc.select(keep_pages)
            results.append(_save(doc, unique_path(out_dir, f"{f.stem}_{suffix}", ".pdf")))
        _tick(progress, i, len(files))
    return results


def extract_pages(files, out_dir, options, progress=None):
    return _select(files, out_dir, options, "extrait", True, progress)


def delete_pages(files, out_dir, options, progress=None):
    return _select(files, out_dir, options, "pages_supprimees", False, progress)


def reorder(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """Nouvel ordre : « 3, 1, 2, 4- » (les pages non citées sont ajoutées à la fin si demandé)."""
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            order: list[int] = []
            for part in options["order"].split(","):
                if part.strip():
                    order += [p for p in pages_from(part, doc.page_count) if p not in order]
            if not order:
                raise ConversionError("empty_page_selection")
            if options["append_rest"]:
                order += [p for p in range(doc.page_count) if p not in order]
            doc.select(order)
            results.append(_save(doc, unique_path(out_dir, f"{f.stem}_reordonne", ".pdf")))
        _tick(progress, i, len(files))
    return results


def rotate(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    angle = int(options["angle"])
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            for p in pages_from(options["pages"], doc.page_count):
                page = doc[p]
                page.set_rotation((page.rotation + angle) % 360)
            results.append(_save(doc, unique_path(out_dir, f"{f.stem}_pivote", ".pdf")))
        _tick(progress, i, len(files))
    return results


# ------------------------------------------------------------------ optimiser / sécuriser

_COMPRESSION = {  # niveau -> (seuil DPI, DPI cible, qualité JPEG)
    "low": (300, 200, 85),
    "medium": (200, 150, 70),
    "high": (150, 96, 55),
}


def compress(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    threshold, target, quality = _COMPRESSION[options["level"]]
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            doc.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality,
                               lossy=True, lossless=True, bitonal=False, color=True, gray=True)
            doc.subset_fonts()
            doc.scrub(metadata=False, xml_metadata=False, thumbnails=True, reset_fields=False,
                      reset_responses=False, attached_files=False, embedded_files=False, javascript=False,
                      hidden_text=False, redactions=False, redact_images=0, remove_links=False, clean_pages=True)
            out = unique_path(out_dir, f"{f.stem}_compresse", ".pdf")
            _save_compressed(doc, out)
        # Ne jamais rendre un fichier plus gros que l'original.
        if out.stat().st_size >= f.stat().st_size:
            out.write_bytes(f.read_bytes())
        results.append(out)
        _tick(progress, i, len(files))
    return results


def _save_compressed(doc: pymupdf.Document, out: Path) -> Path:
    tmp = out.with_name(f".{out.name}.tmp")
    try:
        doc.save(tmp, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True, use_objstms=1)
        replace_file(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


def protect(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    password = options["password"]
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ConversionError("convert_password_too_short", n=MIN_PASSWORD_LENGTH)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ConversionError("convert_password_too_long", n=MAX_PASSWORD_LENGTH)
    # Mot de passe propriétaire distinct et aléatoire : sinon, quiconque connaît le
    # mot de passe d'ouverture a aussi les droits du propriétaire, et les
    # interdictions (impression, copie) ne servent à rien.
    owner_password = secrets.token_urlsafe(24)  # 32 caractères (PDF : 40 au plus)
    perms = pymupdf.PDF_PERM_ACCESSIBILITY
    if options["allow_print"]:
        perms |= pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
    if options["allow_copy"]:
        perms |= pymupdf.PDF_PERM_COPY
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            out = unique_path(out_dir, f"{f.stem}_protege", ".pdf")
            tmp = out.with_name(f".{out.name}.tmp")
            doc.save(tmp, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                     user_pw=password, owner_pw=owner_password, permissions=perms)
            replace_file(tmp, out)
        results.append(out)
        _tick(progress, i, len(files))
    return results


def unlock(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f, options["password"]) as doc:
            out = unique_path(out_dir, f"{f.stem}_deverrouille", ".pdf")
            results.append(_save(doc, out, encryption=pymupdf.PDF_ENCRYPT_NONE))
        _tick(progress, i, len(files))
    return results


def page_numbers(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    template = options["template"] or "{n}"
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            total = doc.page_count
            for idx in pages_from(options["pages"], total):
                page = doc[idx]
                n = idx + int(options["start"])
                text = template.replace("{n}", str(n)).replace("{total}", str(total + int(options["start"]) - 1))
                size = 10
                width = pymupdf.get_text_length(text, "helv", size)
                rect = page.rect  # zone visible
                margin = 28
                x = {"left": margin, "center": (rect.width - width) / 2, "right": rect.width - margin - width}[
                    options["position"].split("_")[1]]
                y = margin + size if options["position"].startswith("top") else rect.height - margin
                point = pymupdf.Point(x, y) * page.derotation_matrix
                page.insert_text(point, text, fontsize=size, fontname="helv", color=(0.2, 0.2, 0.2),
                                 rotate=page.rotation)
            results.append(_save(doc, unique_path(out_dir, f"{f.stem}_numerote", ".pdf")))
        _tick(progress, i, len(files))
    return results


def repair(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """MuPDF reconstruit la table des objets à l'ouverture ; on réécrit un fichier propre."""
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            results.append(_save(doc, unique_path(out_dir, f"{f.stem}_repare", ".pdf"), clean=True))
        _tick(progress, i, len(files))
    return results


def ocr_pdf(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """Ajoute une couche de texte aux pages qui n'en ont pas (PDF scanné)."""
    import numpy as np

    from feuillet.scanner import ocr

    dpi = 300
    results = []
    for f in files:
        with open_pdf(f) as doc:
            total = doc.page_count
            for idx in range(total):
                page = doc[idx]
                if page.get_text().strip() and not options["force"]:
                    _tick(progress, idx + 1, total)
                    continue
                pix = render_page(page, dpi)
                img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., ::-1].copy()
                layer = pymupdf.open("pdf", ocr.text_layer_pdf(img, dpi, options["languages"]))
                try:
                    target = page.rect * page.derotation_matrix
                    target.normalize()
                    page.show_pdf_page(target, layer, 0, overlay=True, rotate=page.rotation)
                finally:
                    layer.close()
                _tick(progress, idx + 1, total)
            results.append(_save(doc, unique_path(out_dir, f"{f.stem}_ocr", ".pdf")))
    return results


# ------------------------------------------------------------------ depuis PDF


def pdf_to_images(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    fmt = options["format"]
    ext = {"jpg": ".jpg", "png": ".png", "webp": ".webp"}[fmt]
    dpi = int(options["dpi"])
    results = []
    for f in files:
        with open_pdf(f) as doc:
            pages = pages_from(options["pages"], doc.page_count)
            folder = out_dir if len(pages) == 1 else unique_folder(out_dir, f"{f.stem}_images")
            for k, idx in enumerate(pages, 1):
                pix = render_page(doc[idx], dpi)
                out = unique_path(folder, f"{f.stem}_p{idx + 1:03d}", ext)
                if fmt == "png":
                    pix.save(out)
                else:
                    pil = pix.pil_image()
                    pil.save(out, format="JPEG" if fmt == "jpg" else "WEBP", quality=int(options["quality"]))
                results.append(out)
                _tick(progress, k, len(pages))
    return results


def pdf_to_text(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            parts = [page.get_text("text", sort=True) for page in doc]
            if not "".join(parts).strip():  # vérifié avant d'écrire : pas de fichier vide laissé
                raise ConversionError("convert_no_text", path=f.name)
            out = unique_path(out_dir, f.stem, ".txt")
            out.write_text("\f".join(parts), encoding="utf-8-sig")  # \f = saut de page
            results.append(out)
        _tick(progress, i, len(files))
    return results


def pdf_to_word(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """Conversion éditable avec pdf2docx (texte, tableaux, images, mise en page)."""
    import logging

    from pdf2docx import Converter

    logging.getLogger("pdf2docx").setLevel(logging.WARNING)
    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            has_text = any(page.get_text().strip() for page in doc)
        if not has_text:
            # PDF scanné : sans couche de texte, le Word ne contiendrait que des
            # images. L'utilisateur doit d'abord passer l'outil « OCR ».
            raise ConversionError("convert_scanned_pdf", path=f.name)
        out = unique_path(out_dir, f.stem, ".docx")
        converter = Converter(str(f))
        try:
            converter.convert(str(out), multi_processing=False)
        except Exception as exc:
            out.unlink(missing_ok=True)
            raise ConversionError("convert_failed", path=f.name, detail=str(exc)) from exc
        finally:
            converter.close()
        results.append(out)
        _tick(progress, i, len(files))
    return results


def pdf_to_excel(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """Les tableaux détectés deviennent des feuilles Excel ; sinon, le texte ligne par ligne."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    results = []
    for i, f in enumerate(files, 1):
        wb = Workbook()
        wb.remove(wb.active)
        found = 0
        with open_pdf(f) as doc:
            for idx, page in enumerate(doc, 1):
                try:
                    tables = page.find_tables().tables
                except Exception:
                    tables = []
                for k, table in enumerate(tables, 1):
                    rows = table.extract()
                    if not rows:
                        continue
                    found += 1
                    ws = wb.create_sheet(f"P{idx} T{k}"[:31])
                    for row in rows:
                        _append_row(ws, [_cell(v) for v in row])
                    for col in range(1, ws.max_column + 1):
                        width = max((len(str(c.value or "")) for c in ws[get_column_letter(col)]), default=8)
                        ws.column_dimensions[get_column_letter(col)].width = min(60, max(8, width + 2))
            if not found:
                ws = wb.create_sheet("Texte")
                for idx, page in enumerate(doc, 1):
                    for line in page.get_text("text", sort=True).splitlines():
                        if line.strip():
                            _append_row(ws, [idx, _cell_text(line)])
        out = unique_path(out_dir, f.stem, ".xlsx")
        wb.save(out)
        results.append(out)
        _tick(progress, i, len(files))
    return results


def _cell_text(text: str) -> str:
    """Texte sans caractères de contrôle (refusés par le format XLSX)."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    return ILLEGAL_CHARACTERS_RE.sub("", text)


def _append_row(ws, values: list) -> None:
    """Ajoute une ligne en forçant le type texte : un PDF piégé contenant
    « =HYPERLINK(…) » ou « =cmd|… » ne devient jamais une formule Excel."""
    ws.append(values)
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def _cell(value):
    """Nombre si la cellule en contient un (format français accepté), sinon texte."""
    if value is None:
        return None
    text = _cell_text(str(value).replace("\n", " ").strip())
    candidate = text.replace(" ", "").replace("\xa0", "").replace(" ", "")
    if candidate.count(",") == 1 and "." not in candidate:
        candidate = candidate.replace(",", ".")
    try:
        number = float(candidate)
        return int(number) if number.is_integer() and "." not in candidate else number
    except ValueError:
        return text


def pdf_to_powerpoint(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """Une diapositive par page (image de la page, texte en notes)."""
    from pptx import Presentation
    from pptx.util import Emu

    results = []
    for i, f in enumerate(files, 1):
        with open_pdf(f) as doc:
            prs = Presentation()
            first = doc[0].rect
            prs.slide_width = Emu(int(first.width * 12700))
            prs.slide_height = Emu(int(first.height * 12700))
            blank = prs.slide_layouts[6]
            for page in doc:
                slide = prs.slides.add_slide(blank)
                pix = render_page(page, int(options["dpi"]))
                stream = io.BytesIO(pix.tobytes("png"))
                slide.shapes.add_picture(stream, 0, 0, prs.slide_width, prs.slide_height)
                text = page.get_text("text", sort=True).strip()
                if text:
                    slide.notes_slide.notes_text_frame.text = text
            out = unique_path(out_dir, f.stem, ".pptx")
            prs.save(out)
            results.append(out)
        _tick(progress, i, len(files))
    return results


# ------------------------------------------------------------------ vers PDF


_CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.4; }
h1 { font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }
pre, code { font-family: monospace; font-size: 9.5pt; }
table { border-collapse: collapse; } td, th { border: 1px solid #999; padding: 3px; }
"""


def _html_to_pdf(content: str, out: Path, base: Path, page_size: str) -> Path:
    archive = pymupdf.Archive(str(base))
    story = pymupdf.Story(html=content, user_css=_CSS, archive=archive)
    mediabox = pymupdf.paper_rect("a4" if page_size == "A4" else "letter")
    where = mediabox + (50, 50, -50, -50)
    # Écriture en mémoire : sous Windows, DocumentWriter garde le fichier ouvert
    # jusqu'au ramasse-miettes, ce qui empêche ensuite de le renommer.
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    del writer, story
    # ``out`` est un chemin neuf (unique_path) : écriture directe, sans renommage.
    out.write_bytes(buffer.getvalue())
    return out


def text_to_pdf(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    results = []
    for i, f in enumerate(files, 1):
        raw = f.read_bytes()
        if b"\x00" in raw[:8192]:
            raise ConversionError("convert_not_text_file", path=f.name)
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        ext = f.suffix.lower()
        if ext in (".html", ".htm"):
            content = text
        elif ext == ".md":
            import markdown

            content = markdown.markdown(text, extensions=["tables", "fenced_code"])
        else:
            content = "<pre style='white-space: pre-wrap; font-family: monospace'>" + html.escape(text) + "</pre>"
        out = unique_path(out_dir, f.stem, ".pdf")
        results.append(_html_to_pdf(content, out, f.parent, options["page_size"]))
        _tick(progress, i, len(files))
    return results


def images_to_pdf(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    """Une page par image, dans l'ordre de la liste, sans retouche."""
    from feuillet.scanner import imaging
    from feuillet.scanner.models import OutputOptions, PageSize
    from feuillet.scanner.pdf_builder import build_pdf

    images = []
    for f in files:
        try:
            images.extend(imaging.load_images(f))
        except AppError as exc:
            raise ConversionError(exc.code, **exc.params) from exc
    size = {"A4": PageSize.A4, "Letter": PageSize.LETTER, "original": PageSize.ORIGINAL}[options["page_size"]]
    out = unique_path(out_dir, options.get("name") or files[0].stem, ".pdf")
    return [build_pdf(images, out, OutputOptions(page_size=size, dpi=int(options["dpi"]),
                                                  jpeg_quality=int(options["quality"])), progress=progress)]
