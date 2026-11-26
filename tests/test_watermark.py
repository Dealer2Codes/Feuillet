import shutil
import subprocess
import zipfile

import docx
import pymupdf
import pytest
from conftest import sha256

from feuillet.core.errors import InputFileError, OutputFileError, WatermarkError
from feuillet.watermark.docx_watermark import (
    apply_docx_watermark,
    remove_existing_watermarks,
)
from feuillet.watermark.models import (
    PageSelection,
    Position,
    SelectionMode,
    WatermarkKind,
    WatermarkSpec,
    parse_page_ranges,
)
from feuillet.watermark.pdf_watermark import (
    apply_pdf_watermark,
    render_blank_preview,
    render_preview,
)

# ------------------------------------------------------------ sélection de pages


@pytest.mark.parametrize("spec,expected", [
    ("1-3, 5", [1, 2, 3, 5]),
    ("8-", [8, 9, 10]),
    ("-2", [1, 2]),
    ("2;2;4", [2, 4]),
    ("", []),
])
def test_parse_ranges(spec, expected):
    assert parse_page_ranges(spec, 10) == expected


@pytest.mark.parametrize("bad", ["a", "3-1", "0", "11", "1--2"])
def test_parse_ranges_errors(bad):
    with pytest.raises(WatermarkError):
        parse_page_ranges(bad, 10)


def test_selection_modes():
    assert PageSelection().resolve(3) == [0, 1, 2]
    assert PageSelection(SelectionMode.ONLY, "2").resolve(3) == [1]
    assert PageSelection(SelectionMode.EXCEPT, "1,3").resolve(3) == [1]
    with pytest.raises(WatermarkError):
        PageSelection(SelectionMode.EXCEPT, "1-3").resolve(3)


# ------------------------------------------------------------ PDF


def _text_by_page(path):
    with pymupdf.open(path) as doc:
        return [p.get_text() for p in doc]


def test_pdf_text_watermark_all_pages(sample_pdf, tmp_path):
    before = sha256(sample_pdf)
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", WatermarkSpec(text="CONFIDENTIEL"))
    texts = _text_by_page(out)
    assert len(texts) == 4
    assert all("CONFIDENTIEL" in t for t in texts)
    assert sha256(sample_pdf) == before  # original intact


def test_pdf_page_selection(sample_pdf, tmp_path):
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", WatermarkSpec(text="COPIE"),
                              PageSelection(SelectionMode.EXCEPT, "2-3"))
    assert ["COPIE" in t for t in _text_by_page(out)] == [True, False, False, True]


def test_pdf_watermark_is_upright_on_rotated_page(sample_pdf, tmp_path):
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf",
                              WatermarkSpec(text="COPIE", angle=0, position=Position.BOTTOM_RIGHT))
    with pymupdf.open(out) as doc:
        page = doc[2]  # page pivotée de 90°
        hit = page.search_for("COPIE")[0] * page.rotation_matrix  # en coordonnées affichées
        shown = page.rect
        assert hit.x0 > shown.width / 2 and hit.y0 > shown.height / 2  # bien en bas à droite
        assert hit.width > hit.height  # texte horizontal à l'écran


@pytest.mark.parametrize("position", list(Position))
def test_pdf_positions_stay_on_page(sample_pdf, tmp_path, position):
    spec = WatermarkSpec(text="BROUILLON", position=position, custom_x=0.3, custom_y=0.7, angle=30)
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", spec, PageSelection(SelectionMode.ONLY, "1"))
    with pymupdf.open(out) as doc:
        page = doc[0]
        for hit in page.search_for("BROUILLON"):
            assert page.rect.contains(hit)


def test_pdf_tile(sample_pdf, tmp_path):
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", WatermarkSpec(text="COPIE", tile=True, font_size=30))
    assert _text_by_page(out)[0].count("COPIE") >= 10


def test_pdf_image_watermark(sample_pdf, tmp_path, logo_png):
    spec = WatermarkSpec(kind=WatermarkKind.IMAGE, image_path=logo_png, opacity=0.3, angle=20)
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", spec)
    with pymupdf.open(out) as doc:
        assert all(page.get_images() for page in doc)


def test_pdf_opacity_is_applied(sample_pdf, tmp_path):
    spec = WatermarkSpec(text="X", font_size=200, opacity=0.2, color=(0, 0, 0), angle=0)
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", spec, PageSelection(SelectionMode.ONLY, "1"))
    with pymupdf.open(out) as doc:
        page = doc[0]
        pix = page.get_pixmap()
        hit = page.search_for("X")[0]
        darkest = min(pix.pixel(int(x), int(y))[0] for x in range(int(hit.x0), int(hit.x1), 2)
                      for y in range(int(hit.y0), int(hit.y1), 2))
    assert 170 < darkest < 230  # gris clair, pas noir


def test_pdf_refuses_password_protected(tmp_path, sample_pdf):
    locked = tmp_path / "locked.pdf"
    with pymupdf.open(sample_pdf) as doc:
        doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    with pytest.raises(InputFileError) as exc:
        apply_pdf_watermark(locked, tmp_path / "out.pdf", WatermarkSpec())
    assert exc.value.code == "pdf_password_protected"


def test_pdf_refuses_overwriting_original(sample_pdf):
    with pytest.raises(OutputFileError):
        apply_pdf_watermark(sample_pdf, sample_pdf, WatermarkSpec(), overwrite=True)


def test_spec_validation(logo_png):
    with pytest.raises(WatermarkError):
        WatermarkSpec(text="  ").validate()
    with pytest.raises(WatermarkError):
        WatermarkSpec(kind=WatermarkKind.IMAGE, image_path=None).validate()
    with pytest.raises(WatermarkError):
        WatermarkSpec(opacity=0).validate()
    WatermarkSpec(kind=WatermarkKind.IMAGE, image_path=logo_png).validate()


def test_missing_glyphs_reported(sample_pdf, tmp_path):
    with pytest.raises(WatermarkError) as exc:
        apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", WatermarkSpec(text="機密"))
    assert exc.value.code == "font_missing_glyphs"


def test_french_accents_supported(sample_pdf, tmp_path):
    out = apply_pdf_watermark(sample_pdf, tmp_path / "out.pdf", WatermarkSpec(text="DOCUMENT CERTIFIÉ"))
    assert "CERTIFIÉ" in _text_by_page(out)[0]


def test_previews(sample_pdf):
    with pymupdf.open(sample_pdf) as doc:
        assert render_preview(doc, 0, WatermarkSpec(), max_side=400).width > 0
        assert doc.page_count == 4  # le document ouvert n'est pas modifié
        assert "CONFIDENTIEL" not in doc[0].get_text()
    assert render_blank_preview(WatermarkSpec(), max_side=300).height == 300


# ------------------------------------------------------------ Word


def _header_xml(path, section):
    d = docx.Document(str(path))
    return d.sections[section].header._element.xml


def test_docx_text_watermark(sample_docx, tmp_path):
    before = sha256(sample_docx)
    out = apply_docx_watermark(sample_docx, tmp_path / "out.docx", WatermarkSpec(text="CONFIDENTIEL", angle=45))
    xml = _header_xml(out, 0)
    assert "PowerPlusWaterMarkObject" in xml and 'string="CONFIDENTIEL"' in xml
    assert "rotation:315" in xml  # 45° anti-horaire = 315° en VML
    assert "En-tête société" in xml  # en-tête existant conservé
    assert sha256(sample_docx) == before
    # les sections suivantes héritent de l'en-tête (pas de doublon)
    d = docx.Document(str(out))
    assert d.sections[1].header.is_linked_to_previous


def test_docx_section_selection(sample_docx, tmp_path):
    out = apply_docx_watermark(sample_docx, tmp_path / "out.docx", WatermarkSpec(text="COPIE"), sections=[2])
    d = docx.Document(str(out))
    has = [("PowerPlusWaterMarkObject" in s.header._element.xml) for s in d.sections]
    assert has == [False, True, False]
    assert all("En-tête société" in s.header._element.xml for s in d.sections)


def test_docx_image_watermark(sample_docx, tmp_path, logo_png):
    spec = WatermarkSpec(kind=WatermarkKind.IMAGE, image_path=logo_png, opacity=0.5)
    out = apply_docx_watermark(sample_docx, tmp_path / "out.docx", spec)
    assert "WordPictureWatermark" in _header_xml(out, 0)
    with zipfile.ZipFile(out) as zf:
        assert any(n.startswith("word/media/") for n in zf.namelist())


def test_docx_replaces_previous_watermark(sample_docx, tmp_path):
    first = apply_docx_watermark(sample_docx, tmp_path / "a.docx", WatermarkSpec(text="BROUILLON"))
    second = apply_docx_watermark(first, tmp_path / "b.docx", WatermarkSpec(text="ORIGINAL"))
    xml = _header_xml(second, 0)
    assert "ORIGINAL" in xml and "BROUILLON" not in xml
    assert remove_existing_watermarks(docx.Document(str(second))) == 1


def test_docx_errors(sample_docx, tmp_path):
    with pytest.raises(WatermarkError):
        apply_docx_watermark(sample_docx, tmp_path / "t.docx", WatermarkSpec(tile=True))
    with pytest.raises(WatermarkError):
        apply_docx_watermark(sample_docx, tmp_path / "s.docx", WatermarkSpec(), sections=[9])
    bad = tmp_path / "bad.docx"
    bad.write_text("pas un docx")
    with pytest.raises(InputFileError):
        apply_docx_watermark(bad, tmp_path / "o.docx", WatermarkSpec())


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice absent")
def test_docx_opens_in_libreoffice(sample_docx, tmp_path):
    out = apply_docx_watermark(sample_docx, tmp_path / "wm.docx", WatermarkSpec(text="CONFIDENTIEL"))
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(out)],
                   check=True, capture_output=True, timeout=180)
    with pymupdf.open(tmp_path / "wm.pdf") as doc:
        assert doc.page_count >= 3
        assert "Premier paragraphe" in doc[0].get_text()
