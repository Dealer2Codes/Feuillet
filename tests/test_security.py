"""Tests de régression de l'audit de sécurité."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from feuillet.convert import run_tool
from feuillet.convert.base import ConversionError, unique_path
from feuillet.core.files import safe_filename, safe_which


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "source.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Bonjour")
    doc.save(path)
    doc.close()
    return path


# ---------------------------------------------------------------- noms de fichiers
@pytest.mark.parametrize("name", ["..\\..\\Windows\\evil", "../../etc/passwd", "C:\\Windows\\x", "/abs/x",
                                  "CON", "nul.txt", "a<b>c:d|e?*", "   ...   ", ""])
def test_user_names_never_leave_output_folder(tmp_path, name):
    out = unique_path(tmp_path, name, ".pdf")
    assert out.parent == tmp_path
    stem = out.stem.split(".")[0].upper()
    assert stem not in {"CON", "NUL", "PRN", "AUX"}
    assert not any(ch in out.name for ch in '<>:"/\\|?*')


def test_merge_name_option_is_sanitized(tmp_path, text_pdf):
    out = tmp_path / "out"
    out.mkdir()
    (result,) = run_tool("merge", [text_pdf, text_pdf], out, {"name": "..\\..\\piege"})
    assert result.parent == out


def test_safe_filename_keeps_normal_names():
    assert safe_filename("Contrat 2026 – version finale") == "Contrat 2026 – version finale"


# ---------------------------------------------------------------- recherche des programmes
def test_safe_which_ignores_current_directory(tmp_path, monkeypatch):
    fake = tmp_path / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
    fake.write_text("piège")
    fake.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", "relatif"]))
    assert safe_which("tesseract") is None


def test_safe_which_finds_absolute_path_entries(tmp_path, monkeypatch):
    exe = tmp_path / ("outil.exe" if sys.platform == "win32" else "outil")
    exe.write_text("")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert safe_which("outil") == exe


# ---------------------------------------------------------------- protection PDF
def test_protect_permissions_are_enforced(tmp_path, text_pdf):
    """Le mot de passe d'ouverture ne donne pas les droits du propriétaire."""
    out = tmp_path / "out"
    out.mkdir()
    (locked,) = run_tool("protect", [text_pdf], out, {"password": "secret123", "allow_print": False,
                                                       "allow_copy": False})
    with pymupdf.open(locked) as doc:
        assert doc.needs_pass
        assert doc.authenticate("secret123") == 2  # 2 = utilisateur, pas propriétaire (4)
        assert not doc.permissions & pymupdf.PDF_PERM_PRINT
        assert not doc.permissions & pymupdf.PDF_PERM_COPY


@pytest.mark.parametrize(("password", "code"), [("abc", "convert_password_too_short"),
                                                 ("x" * 41, "convert_password_too_long")])
def test_protect_password_length(tmp_path, text_pdf, password, code):
    with pytest.raises(ConversionError) as exc:
        run_tool("protect", [text_pdf], tmp_path, {"password": password})
    assert exc.value.code == code


# ---------------------------------------------------------------- PDF -> Excel
def test_pdf_to_excel_never_creates_formulas(tmp_path):
    from openpyxl import load_workbook

    src = tmp_path / "piege.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), '=HYPERLINK("http://example.invalid","clic")')
    page.insert_text((72, 100), "@SUM(1+1)")
    doc.save(src)
    doc.close()
    (xlsx,) = run_tool("pdf_to_excel", [src], tmp_path, {})
    ws = load_workbook(xlsx).active
    values = [c for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    assert values and all(c.data_type == "s" for c in values)
    assert any(c.value.startswith("=HYPERLINK") for c in values)


def test_pdf_to_text_leaves_no_empty_file(tmp_path):
    src = tmp_path / "vide.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(src)
    doc.close()
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ConversionError):
        run_tool("pdf_to_text", [src], out, {})
    assert list(out.iterdir()) == []


# ---------------------------------------------------------------- PDF/images démesurés
def test_huge_pdf_page_rendering_is_capped(tmp_path):
    from feuillet.convert.pdf_tools import MAX_RENDER_PIXELS, render_page

    doc = pymupdf.open()
    page = doc.new_page(width=14400, height=14400)  # 5 m × 5 m (maximum PDF)
    pix = render_page(page, 600)
    assert pix.width * pix.height <= MAX_RENDER_PIXELS * 1.01


def test_decompression_bomb_is_refused(tmp_path, monkeypatch):
    from feuillet.core.errors import InputFileError
    from feuillet.scanner import imaging

    path = tmp_path / "bombe.png"
    Image.new("L", (400, 400)).save(path)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # 400×400 > 2 × 1000
    with pytest.raises(InputFileError) as exc:
        imaging.load_images(path)
    assert exc.value.code == "image_too_large"
    with pytest.raises(ConversionError) as exc2:
        run_tool("convert_images", [path], tmp_path, {"format": "jpg", "quality": 80, "background": "white"})
    assert exc2.value.code == "image_too_large"


def test_limits_are_active():
    import feuillet  # noqa: F401 - l'import du paquet applique les limites
    from feuillet.core.limits import MAX_IMAGE_PIXELS

    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS


def test_gps_position_is_removed_from_converted_photos(tmp_path):
    src = tmp_path / "photo.jpg"
    im = Image.new("RGB", (40, 30), "blue")
    exif = Image.Exif()
    exif[0x010F] = "Fabricant"
    exif[0x8825] = {1: "N", 2: (6.0, 22.0, 0.0)}
    im.save(src, exif=exif)
    (out,) = run_tool("convert_images", [src], tmp_path, {"format": "png", "quality": 90, "background": "white"})
    with Image.open(out) as res:
        kept = res.getexif()
    assert 0x8825 not in kept


# ---------------------------------------------------------------- filigrane Word
def test_docx_font_name_cannot_inject_xml():
    from feuillet.watermark.docx_watermark import _text_shape_xml
    from feuillet.watermark.models import WatermarkSpec

    spec = WatermarkSpec(text='<b>"&</b>', font_name='Arial"/><evil x="')
    xml = _text_shape_xml(spec, 595, 842, 500)
    from lxml import etree

    etree.fromstring(xml.encode())  # XML bien formé : aucune injection
    assert "<evil" not in xml


# ---------------------------------------------------------------- Office
def test_office_automation_disables_macros():
    source = Path(__file__).resolve().parents[1] / "src" / "feuillet" / "convert" / "office.py"
    code = source.read_text(encoding="utf-8")
    assert code.count("AutomationSecurity = _FORCE_DISABLE_MACROS") == 3
    assert "_FORCE_DISABLE_MACROS = 3" in code


# ---------------------------------------------------------------- fichiers incohérents (vérification approfondie)
def test_empty_file_is_refused(tmp_path):
    empty = tmp_path / "vide.pdf"
    empty.write_bytes(b"")
    with pytest.raises(ConversionError) as exc:
        run_tool("compress", [empty], tmp_path, {})
    assert exc.value.code == "convert_empty_file"


@pytest.mark.parametrize(("name", "data"), [
    ("faux.docx", b"ceci n'est pas un zip"),
    ("faux.xlsx", b"\x00\x01\x02" * 50),
    ("faux.doc", bytes(range(256)) * 4),
    ("faux.rtf", b"pas du RTF"),
])
def test_office_content_mismatch_is_refused(tmp_path, name, data):
    from feuillet.convert.office import check_office_content

    src = tmp_path / name
    src.write_bytes(data)
    with pytest.raises(ConversionError) as exc:
        check_office_content(src)
    assert exc.value.code == "convert_not_document"


@pytest.mark.parametrize(("name", "data"), [
    ("ok.docx", b"PK\x03\x04reste"),
    ("chiffre.docx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 50),  # OOXML protégé
    ("ancien.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 50),
    ("html.doc", b"<html><body>Word en HTML</body></html>"),
    ("ok.rtf", b"{\\rtf1\\ansi texte}"),
    ("ok.csv", "nom;âge\nAda;36\n".encode("cp1252")),
])
def test_office_content_valid_files_are_accepted(tmp_path, name, data):
    from feuillet.convert.office import check_office_content

    src = tmp_path / name
    src.write_bytes(data)
    check_office_content(src)


def test_binary_file_is_not_converted_as_text(tmp_path):
    src = tmp_path / "binaire.txt"
    src.write_bytes(b"\x00\x01\x02\xff" * 100)
    with pytest.raises(ConversionError) as exc:
        run_tool("text_to_pdf", [src], tmp_path, {})
    assert exc.value.code == "convert_not_text_file"


def test_invalid_integer_option_gives_clear_error(tmp_path, text_pdf):
    with pytest.raises(ConversionError) as exc:
        run_tool("pdf_to_images", [text_pdf], tmp_path, {"quality": "abc"})
    assert exc.value.code == "convert_invalid_option"


@pytest.fixture
def app():
    qt = pytest.importorskip("PySide6.QtWidgets")
    return qt.QApplication.instance() or qt.QApplication([])


def test_watermark_tab_does_not_shadow_qwidget_methods(app):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QFont

    from feuillet.ui.watermark_view import WatermarkTab

    tab = WatermarkTab()
    assert isinstance(tab.size(), QSize)
    assert isinstance(tab.font(), QFont)


def test_translations_are_complete_and_consistent():
    import json
    import string

    root = Path(__file__).resolve().parents[1] / "src" / "feuillet" / "locales"
    fr = json.loads((root / "fr.json").read_text(encoding="utf-8"))
    en = json.loads((root / "en.json").read_text(encoding="utf-8"))
    assert set(fr) == set(en)
    fields = lambda text: {f for _, f, _, _ in string.Formatter().parse(text) if f}  # noqa: E731
    assert [k for k in fr if fields(fr[k]) != fields(en[k])] == []
