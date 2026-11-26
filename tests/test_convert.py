from pathlib import Path

import docx
import pymupdf
import pytest
from conftest import sha256, tesseract_ready
from PIL import Image

from feuillet.convert import TOOLS, office, run_tool, tools_for
from feuillet.convert.base import ConversionError

HAS_LO = office.find_libreoffice() is not None


@pytest.fixture
def out(tmp_path) -> Path:
    d = tmp_path / "sortie"
    d.mkdir()
    return d


@pytest.fixture
def text_pdf(tmp_path) -> Path:
    path = tmp_path / "rapport.pdf"
    doc = pymupdf.open()
    for i in range(5):
        page = doc.new_page()
        page.insert_text((72, 80), f"Rapport annuel page {i + 1}", fontsize=16)
        if i == 0:
            # tableau simple : grille + valeurs
            x0, y0, cw, rh = 72, 120, 120, 24
            data = [["Produit", "Quantité", "Prix"], ["Riz", "12", "1 500,50"], ["Maïs", "7", "900"]]
            for r, row in enumerate(data):
                for c, val in enumerate(row):
                    rect = pymupdf.Rect(x0 + c * cw, y0 + r * rh, x0 + (c + 1) * cw, y0 + (r + 1) * rh)
                    page.draw_rect(rect, color=(0, 0, 0), width=0.8)
                    page.insert_text((rect.x0 + 4, rect.y1 - 7), val, fontsize=11)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def image_files(tmp_path) -> list[Path]:
    rgba = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    for x in range(100, 200):
        for y in range(50, 150):
            rgba.putpixel((x, y), (200, 30, 30, 255))
    png = tmp_path / "logo.png"
    rgba.save(png)
    webp = tmp_path / "photo.webp"
    Image.new("RGB", (400, 300), (20, 120, 200)).save(webp)
    gif = tmp_path / "anim.gif"
    frames = [Image.new("RGB", (50, 50), (i * 80, 0, 0)) for i in range(3)]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return [png, webp, gif]


# ------------------------------------------------------------ catalogue


def test_catalogue_is_consistent():
    assert len({t.id for t in TOOLS}) == len(TOOLS)
    for t in TOOLS:
        assert t.inputs and all(e.startswith(".") and e == e.lower() for e in t.inputs)
        for o in t.options:
            if o.choices:
                assert str(o.default) in o.choices, (t.id, o.name)


def test_tools_for_suggests_relevant_actions(tmp_path):
    ids = {t.id for t in tools_for(Path("x.pdf"))}
    assert {"pdf_to_word", "merge", "compress", "protect"} <= ids
    assert "convert_images" in {t.id for t in tools_for(Path("a.webp"))}
    assert "word_to_pdf" in {t.id for t in tools_for(Path("a.docx"))}


def test_wrong_type_and_missing_file(out, text_pdf, image_files):
    with pytest.raises(ConversionError) as exc:
        run_tool("pdf_to_text", [image_files[0]], out)
    assert exc.value.code == "convert_wrong_type"
    with pytest.raises(ConversionError):
        run_tool("pdf_to_text", [text_pdf.with_name("absent.pdf")], out)
    with pytest.raises(ConversionError) as exc:
        run_tool("merge", [text_pdf], out)
    assert exc.value.code == "convert_not_enough_files"


# ------------------------------------------------------------ images


@pytest.mark.parametrize("fmt", ["jpg", "png", "webp", "bmp", "tiff", "gif", "ico"])
def test_image_formats(out, image_files, fmt):
    before = [sha256(f) for f in image_files]
    results = run_tool("convert_images", image_files, out, {"format": fmt})
    assert len(results) == 3
    for r in results:
        with Image.open(r) as im:
            im.load()
    assert [sha256(f) for f in image_files] == before


def test_png_transparency_to_jpg_uses_background(out, image_files):
    (jpg,) = run_tool("convert_images", [image_files[0]], out, {"format": "jpg", "background": "white"})
    with Image.open(jpg) as im:
        assert im.getpixel((5, 5)) == (255, 255, 255)
        r, g, b = im.getpixel((150, 100))
        assert r > 150 and g < 80


def test_gif_animation_kept_in_webp(out, image_files):
    (webp,) = run_tool("convert_images", [image_files[2]], out, {"format": "webp"})
    with Image.open(webp) as im:
        assert getattr(im, "n_frames", 1) == 3


def test_outputs_never_overwrite(out, image_files):
    a = run_tool("convert_images", [image_files[1]], out, {"format": "png"})[0]
    b = run_tool("convert_images", [image_files[1]], out, {"format": "png"})[0]
    assert a != b and a.exists() and b.exists()


# ------------------------------------------------------------ vers PDF


def test_images_to_pdf(out, image_files):
    (pdf,) = run_tool("images_to_pdf", image_files, out, {"name": "album"})
    assert pdf.name == "album.pdf"
    with pymupdf.open(pdf) as doc:
        assert doc.page_count == 3  # une page par fichier (première image d'un GIF animé)


@pytest.mark.parametrize("name,content,expect", [
    ("notes.txt", "Bonjour Cotonou\nLigne deux é à ç", "Cotonou"),
    ("doc.md", "# Titre principal\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", "Titre principal"),
    ("page.html", "<h1>Facture</h1><p>Total : <b>125 000 FCFA</b></p>", "125 000 FCFA"),
])
def test_text_to_pdf(tmp_path, out, name, content, expect):
    src = tmp_path / name
    src.write_text(content, encoding="utf-8")
    (pdf,) = run_tool("text_to_pdf", [src], out)
    with pymupdf.open(pdf) as doc:
        text = doc[0].get_text()
    assert expect in text
    if name.endswith(".txt"):
        assert "é à ç" in text


@pytest.mark.skipif(not HAS_LO, reason="LibreOffice absent")
def test_word_to_pdf_with_libreoffice(tmp_path, out):
    src = tmp_path / "lettre.docx"
    d = docx.Document()
    d.add_heading("Lettre officielle", 0)
    d.add_paragraph("Objet : demande d'attestation.")
    d.save(src)
    (pdf,) = run_tool("word_to_pdf", [src], out, {"engine": "libreoffice"})
    with pymupdf.open(pdf) as doc:
        assert "Lettre officielle" in doc[0].get_text()


@pytest.mark.skipif(not HAS_LO, reason="LibreOffice absent")
def test_excel_and_powerpoint_to_pdf(tmp_path, out):
    from openpyxl import Workbook
    from pptx import Presentation

    xlsx = tmp_path / "budget.xlsx"
    wb = Workbook()
    wb.active.append(["Poste", "Montant"])
    wb.active.append(["Loyer", 150000])
    wb.save(xlsx)
    pptx_path = tmp_path / "expose.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Exposé Feuillet"
    prs.save(pptx_path)
    (a,) = run_tool("excel_to_pdf", [xlsx], out, {"engine": "libreoffice"})
    (b,) = run_tool("powerpoint_to_pdf", [pptx_path], out, {"engine": "libreoffice"})
    with pymupdf.open(a) as d1, pymupdf.open(b) as d2:
        assert "Loyer" in d1[0].get_text()
        assert "Feuillet" in d2[0].get_text()


@pytest.mark.skipif(not HAS_LO, reason="LibreOffice absent")
def test_office_to_office(tmp_path, out, sample_docx):
    (odt,) = run_tool("office_convert", [sample_docx], out, {"format": "odt", "engine": "libreoffice"})
    assert odt.suffix == ".odt" and odt.stat().st_size > 0
    with pytest.raises(ConversionError) as exc:
        run_tool("office_convert", [sample_docx], out, {"format": "xlsx", "engine": "libreoffice"})
    assert exc.value.code == "convert_incompatible_target"


def test_office_engine_missing_is_explicit(monkeypatch, tmp_path, out, sample_docx):
    monkeypatch.setattr(office, "find_libreoffice", lambda: None)
    monkeypatch.setattr(office, "has_ms_office", lambda app: False)
    with pytest.raises(ConversionError) as exc:
        office.convert_office(sample_docx, "pdf", out)
    assert exc.value.code == "convert_no_office_engine"
    assert "LibreOffice" in exc.value.user_message()


# ------------------------------------------------------------ depuis PDF


def test_pdf_to_word(out, text_pdf):
    (docx_path,) = run_tool("pdf_to_word", [text_pdf], out)
    text = "\n".join(p.text for p in docx.Document(str(docx_path)).paragraphs)
    tables = docx.Document(str(docx_path)).tables
    assert "Rapport annuel page 1" in text
    assert tables and tables[0].cell(1, 0).text.strip() == "Riz"


def test_pdf_to_word_refuses_scanned(tmp_path, out):
    scanned = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
    pix.clear_with(200)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(scanned)
    with pytest.raises(ConversionError) as exc:
        run_tool("pdf_to_word", [scanned], out)
    assert exc.value.code == "convert_scanned_pdf"


def test_pdf_to_excel_reads_tables_and_numbers(out, text_pdf):
    from openpyxl import load_workbook

    (xlsx,) = run_tool("pdf_to_excel", [text_pdf], out)
    ws = load_workbook(xlsx).worksheets[0]
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0] == ["Produit", "Quantité", "Prix"]
    assert rows[1] == ["Riz", 12, 1500.5]


def test_pdf_to_powerpoint(out, text_pdf):
    from pptx import Presentation

    (pptx_path,) = run_tool("pdf_to_powerpoint", [text_pdf], out)
    prs = Presentation(str(pptx_path))
    assert len(prs.slides) == 5
    assert "Rapport annuel page 2" in prs.slides[1].notes_slide.notes_text_frame.text


@pytest.mark.parametrize("fmt", ["jpg", "png", "webp"])
def test_pdf_to_images(out, text_pdf, fmt):
    results = run_tool("pdf_to_images", [text_pdf], out, {"format": fmt, "dpi": "72", "pages": "1-2"})
    assert len(results) == 2 and all(r.suffix == f".{fmt}" for r in results)
    with Image.open(results[0]) as im:
        assert im.width == 595  # A4 à 72 DPI


def test_pdf_to_text(out, text_pdf):
    (txt,) = run_tool("pdf_to_text", [text_pdf], out)
    content = txt.read_text("utf-8-sig")
    assert content.count("Rapport annuel") == 5 and content.count("\f") == 4


# ------------------------------------------------------------ organiser


def test_merge_keeps_order(tmp_path, out, text_pdf, sample_pdf):
    before = sha256(text_pdf)
    (merged,) = run_tool("merge", [sample_pdf, text_pdf], out, {"name": "dossier"})
    with pymupdf.open(merged) as doc:
        assert doc.page_count == 9
        assert "Page 1" in doc[0].get_text() and "Rapport annuel page 1" in doc[4].get_text()
    assert sha256(text_pdf) == before


@pytest.mark.parametrize("options,expected", [
    ({"mode": "every_page"}, [1, 1, 1, 1, 1]),
    ({"mode": "every_n", "every": 2}, [2, 2, 1]),
    ({"mode": "ranges", "ranges": "1-2, 3-5"}, [2, 3]),
])
def test_split(out, text_pdf, options, expected):
    results = run_tool("split", [text_pdf], out, options)
    counts = []
    for r in results:
        with pymupdf.open(r) as d:
            counts.append(d.page_count)
    assert counts == expected


def test_extract_delete_reorder_rotate(out, text_pdf):
    (ex,) = run_tool("extract_pages", [text_pdf], out, {"pages": "2,4"})
    (de,) = run_tool("delete_pages", [text_pdf], out, {"pages": "1"})
    (re_,) = run_tool("reorder", [text_pdf], out, {"order": "5, 1", "append_rest": True})
    (ro,) = run_tool("rotate", [text_pdf], out, {"angle": "90", "pages": "1"})
    with pymupdf.open(ex) as d:
        assert d.page_count == 2 and "page 4" in d[1].get_text()
    with pymupdf.open(de) as d:
        assert d.page_count == 4 and "page 2" in d[0].get_text()
    with pymupdf.open(re_) as d:
        firsts = [p.get_text().splitlines()[0] for p in d]
        assert [f[-1] for f in firsts] == ["5", "1", "2", "3", "4"]
    with pymupdf.open(ro) as d:
        assert d[0].rotation == 90 and d[1].rotation == 0
    with pytest.raises(ConversionError):
        run_tool("delete_pages", [text_pdf], out, {"pages": "1-5"})
    with pytest.raises(ConversionError):
        run_tool("extract_pages", [text_pdf], out, {"pages": ""})


# ------------------------------------------------------------ optimiser / sécuriser


def test_compress_reduces_image_pdf(tmp_path, out):
    import numpy as np

    big = tmp_path / "photos.pdf"
    doc = pymupdf.open()
    rng = np.random.default_rng(0)
    for _ in range(2):
        arr = (rng.random((2400, 1700, 3)) * 40 + np.linspace(0, 200, 1700)[None, :, None]).astype("uint8")
        path = tmp_path / "p.png"
        Image.fromarray(arr).save(path)
        page = doc.new_page()
        page.insert_image(page.rect, filename=str(path))
    doc.save(big)
    (small,) = run_tool("compress", [big], out, {"level": "medium"})
    assert small.stat().st_size < big.stat().st_size * 0.6
    with pymupdf.open(small) as d:
        assert d.page_count == 2


def test_compress_never_grows(out, text_pdf):
    (res,) = run_tool("compress", [text_pdf], out, {"level": "high"})
    assert res.stat().st_size <= text_pdf.stat().st_size


def test_protect_and_unlock(out, text_pdf):
    (locked,) = run_tool("protect", [text_pdf], out, {"password": "secret123", "allow_copy": False})
    with pymupdf.open(locked) as d:
        assert d.needs_pass
    with pytest.raises(ConversionError) as exc:
        run_tool("unlock", [locked], out, {"password": "faux"})
    assert exc.value.code == "convert_wrong_password"
    (opened,) = run_tool("unlock", [locked], out, {"password": "secret123"})
    with pymupdf.open(opened) as d:
        assert not d.needs_pass and d.page_count == 5
    with pytest.raises(ConversionError):
        run_tool("protect", [text_pdf], out, {"password": "ab"})


def test_page_numbers(out, sample_pdf):
    (res,) = run_tool("page_numbers", [sample_pdf], out, {"template": "Page {n} sur {total}"})
    with pymupdf.open(res) as d:
        assert "Page 3 sur 4" in d[2].get_text()  # page 3 pivotée de 90°
        hit = d[2].search_for("Page 3 sur 4")[0] * d[2].rotation_matrix
        assert hit.y0 > d[2].rect.height / 2  # en bas de la page affichée


def test_repair(out, text_pdf):
    (res,) = run_tool("repair", [text_pdf], out)
    with pymupdf.open(res) as d:
        assert d.page_count == 5


@pytest.mark.skipif(not tesseract_ready(), reason="Tesseract fra+eng absent")
def test_ocr_pdf_makes_scan_searchable(tmp_path, out):
    import cv2
    from synthetic import make_page

    img = tmp_path / "page.png"
    cv2.imwrite(str(img), make_page())
    (scan,) = run_tool("images_to_pdf", [img], out)
    (res,) = run_tool("ocr_pdf", [scan], out)
    with pymupdf.open(res) as d:
        assert d[0].search_for("ATTESTATION")


def test_every_tool_has_translations():
    from feuillet.core.i18n import tr

    for t in TOOLS:
        assert tr(f"convert.tool.{t.id}") != f"convert.tool.{t.id}", t.id
        assert tr(f"convert.desc.{t.id}") != f"convert.desc.{t.id}", t.id
        for o in t.options:
            assert tr(f"convert.opt.{o.name}") != f"convert.opt.{o.name}", (t.id, o.name)
            for c in o.choices:
                key = f"convert.opt.{o.name}.{c}"
                assert tr(key) != key, key
