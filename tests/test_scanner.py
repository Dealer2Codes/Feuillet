
import cv2
import numpy as np
import pymupdf
import pytest
from conftest import sha256, tesseract_ready
from PIL import Image
from synthetic import PAGE_H, PAGE_W, make_card, make_page, make_photo

from feuillet.core.errors import InputFileError, OutputFileError
from feuillet.scanner import imaging, ocr
from feuillet.scanner.models import (
    ID1_ASPECT,
    DocumentKind,
    EnhanceMode,
    IdCardLayout,
    OutputOptions,
    PageSettings,
    PageSize,
)
from feuillet.scanner.pdf_builder import build_id_card_pdf, build_pdf

# ------------------------------------------------------------ chargement


def test_load_applies_exif_orientation(tmp_path):
    img = Image.new("RGB", (400, 200), "white")
    exif = img.getexif()
    exif[0x0112] = 6  # rotation de 90° demandée par l'appareil photo
    path = tmp_path / "phone.jpg"
    img.save(path, exif=exif)
    (loaded,) = imaging.load_images(path)
    assert loaded.shape[:2] == (400, 200)


def test_load_multipage_tiff(tmp_path):
    frames = [Image.new("RGB", (100, 150), c) for c in ("white", "gray", "black")]
    path = tmp_path / "multi.tiff"
    frames[0].save(path, save_all=True, append_images=frames[1:])
    assert len(imaging.load_images(path)) == 3


@pytest.mark.parametrize("ext", [".png", ".bmp", ".jpg"])
def test_load_formats(tmp_path, ext):
    path = tmp_path / f"page{ext}"
    cv2.imwrite(str(path), make_page())
    assert imaging.load_images(path)[0].shape[:2] == (PAGE_H, PAGE_W)


def test_load_rejects_unknown(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("x")
    with pytest.raises(InputFileError):
        imaging.load_images(bad)
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    with pytest.raises(InputFileError):
        imaging.load_images(broken)


# ------------------------------------------------------------ géométrie


def test_detect_document_finds_corners():
    photo, truth = make_photo()
    corners = imaging.detect_document(photo)
    assert corners is not None
    assert np.abs(corners - truth).max() < 20  # pixels, sur une photo de 2000 × 2600


def test_detect_returns_none_without_document():
    noise = np.random.default_rng(1).integers(0, 255, (800, 600, 3), dtype=np.uint8)
    assert imaging.detect_document(noise) is None


def test_warp_keeps_proportions():
    photo, truth = make_photo()
    out = imaging.warp_document(photo, truth)
    h, w = out.shape[:2]
    assert abs(h / w - PAGE_H / PAGE_W) < 0.05  # pas d'étirement


def test_warp_id_card_aspect():
    photo, truth = make_photo(page=cv2.resize(make_card(), (PAGE_W, int(PAGE_W / ID1_ASPECT))))
    out = imaging.warp_document(photo, truth, aspect=ID1_ASPECT)
    h, w = out.shape[:2]
    ratio = max(h, w) / min(h, w)
    assert abs(ratio - ID1_ASPECT) < 0.01


@pytest.mark.parametrize("angle", [-9.0, -3.0, 2.0, 7.5])
def test_skew_estimation(angle):
    rotated = imaging.rotate_free(make_page(), angle)
    assert abs(imaging.estimate_skew(rotated) - angle) < 0.5


def test_deskew_straightens():
    rotated = imaging.rotate_free(make_page(), 5.0)
    settings = PageSettings(auto_detect=False, mode=EnhanceMode.ORIGINAL)
    out = imaging.geometry(rotated, settings)
    assert abs(imaging.estimate_skew(out)) < 0.5


@pytest.mark.parametrize("deg", [90, 180, 270])
def test_quarter_rotation_is_lossless(deg):
    page = make_page()
    back = imaging.rotate_quarter(imaging.rotate_quarter(page, deg), 360 - deg)
    assert np.array_equal(back, page)


# ------------------------------------------------------------ amélioration


def _stamp_and_signature_kept(img):
    """Le tampon rouge (400, 1450) et la signature bleue (~900, 1450) restent colorés."""
    assert img.ndim == 3
    page = cv2.resize(img, (PAGE_W, PAGE_H))
    hsv = cv2.cvtColor(page, cv2.COLOR_BGR2HSV)
    stamp = hsv[1340:1560, 290:510]
    sign = hsv[1400:1500, 800:1030]
    red = ((stamp[..., 1] > 80) & ((stamp[..., 0] < 10) | (stamp[..., 0] > 170))).sum()
    blue = ((sign[..., 1] > 80) & (sign[..., 0] > 90) & (sign[..., 0] < 130)).sum()
    return red > 300 and blue > 150


@pytest.mark.parametrize("mode", [EnhanceMode.AUTO, EnhanceMode.COLOR, EnhanceMode.BLACK_WHITE])
def test_signatures_and_stamps_survive(mode):
    out = imaging.enhance(make_page(), PageSettings(mode=mode))
    assert _stamp_and_signature_kept(out)


def test_auto_mode_never_binarizes():
    plain = make_page(with_marks=False)
    out = imaging.enhance(plain, PageSettings(mode=EnhanceMode.AUTO))
    assert out.ndim == 2  # niveaux de gris pour un document sans couleur
    assert not imaging.is_bilevel(out)


def test_black_white_is_bilevel_without_color():
    out = imaging.enhance(make_page(with_marks=False), PageSettings(mode=EnhanceMode.BLACK_WHITE))
    assert imaging.is_bilevel(out)


def test_shadow_removal_flattens_background():
    page = make_page(with_marks=False)
    h, w = page.shape[:2]
    gradient = np.linspace(0.45, 1.0, w)[None, :, None]
    shaded = (page * gradient).astype(np.uint8)
    flat = imaging.remove_shadows(shaded)
    left, right = flat[:, 20:60].mean(), flat[:, -60:-20].mean()
    assert abs(left - right) < 12  # contre plus de 100 avant correction


def test_original_mode_is_untouched():
    page = make_page()
    out = imaging.enhance(page, PageSettings(mode=EnhanceMode.ORIGINAL))
    assert np.array_equal(out, page)


def test_brightness_contrast():
    gray = np.full((10, 10), 100, np.uint8)
    assert imaging.adjust_brightness_contrast(gray, 50, 0).mean() > 100
    assert imaging.adjust_brightness_contrast(gray, 0, 0) is gray


def test_page_original_is_read_only():
    from feuillet.scanner.models import ScanPage

    page = ScanPage(make_page())
    with pytest.raises(ValueError):
        page.original[0, 0] = 0


# ------------------------------------------------------------ PDF


def test_build_pdf_one_page_per_image(tmp_path):
    images = [make_page(), imaging.rotate_quarter(make_page(), 90), make_page(with_marks=False)]
    out = build_pdf(images, tmp_path / "out.pdf", OutputOptions(page_size=PageSize.A4, dpi=150))
    with pymupdf.open(out) as doc:
        assert doc.page_count == 3
        assert round(doc[0].rect.width) == 595 and round(doc[0].rect.height) == 842
        assert doc[1].rect.width > doc[1].rect.height  # page paysage pour l'image paysage


def test_bilevel_pages_are_small(tmp_path):
    bw = imaging.enhance(make_page(with_marks=False), PageSettings(mode=EnhanceMode.BLACK_WHITE))
    color = make_page()
    a = build_pdf([bw], tmp_path / "bw.pdf", OutputOptions(dpi=200))
    b = build_pdf([color], tmp_path / "color.pdf", OutputOptions(dpi=200))
    assert a.stat().st_size < b.stat().st_size


def test_build_pdf_never_overwrites_original(tmp_path):
    src = tmp_path / "page.png"
    cv2.imwrite(str(src), make_page())
    before = sha256(src)
    with pytest.raises(OutputFileError):
        build_pdf([make_page()], src, OutputOptions(), originals=[src], overwrite=True)
    assert sha256(src) == before


def test_original_page_size_option(tmp_path):
    out = build_pdf([make_page()], tmp_path / "o.pdf", OutputOptions(page_size=PageSize.ORIGINAL, dpi=150))
    with pymupdf.open(out) as doc:
        assert abs(doc[0].rect.width - PAGE_W / 150 * 72) < 1


@pytest.mark.parametrize("layout,pages", [(IdCardLayout.ONE_PAGE, 1), (IdCardLayout.TWO_PAGES, 2)])
def test_id_card_real_size(tmp_path, layout, pages):
    card = make_card()
    out = build_id_card_pdf(card, card, tmp_path / "id.pdf", OutputOptions(id_card_layout=layout))
    with pymupdf.open(out) as doc:
        assert doc.page_count == pages
        info = doc[0].get_image_info()
        assert info
        bbox = pymupdf.Rect(info[0]["bbox"])
        assert abs(bbox.width / 72 * 25.4 - 85.6) < 0.3
        assert abs(bbox.height / 72 * 25.4 - 53.98) < 0.3


# ------------------------------------------------------------ OCR


@pytest.mark.skipif(not tesseract_ready(), reason="Tesseract fra+eng absent")
def test_ocr_makes_pdf_searchable(tmp_path):
    out = build_pdf([make_page()], tmp_path / "ocr.pdf", OutputOptions(ocr=True, dpi=200))
    with pymupdf.open(out) as doc:
        page = doc[0]
        assert page.search_for("ATTESTATION")
        hit = page.search_for("Cotonou")[0]
        assert page.rect.contains(hit)
        # couche invisible : l'image reste la seule chose dessinée
        assert len(page.get_images()) == 1


@pytest.mark.skipif(not tesseract_ready("osd"), reason="Tesseract osd absent")
def test_osd_detects_upside_down():
    upside = imaging.rotate_quarter(make_page(), 180)
    assert ocr.detect_rotation(upside) == 180


def test_ocr_missing_language_is_explicit():
    from feuillet.core.errors import OcrUnavailableError

    with pytest.raises(OcrUnavailableError):
        ocr.text_layer_pdf(make_page(), 150, "xyz")


# ------------------------------------------------------------ bout en bout


@pytest.mark.skipif(not tesseract_ready(), reason="Tesseract fra+eng absent")
def test_photo_to_searchable_pdf(tmp_path):
    photo, _ = make_photo()
    src = tmp_path / "photo.jpg"
    cv2.imwrite(str(src), photo)
    before = sha256(src)
    (img,) = imaging.load_images(src)
    processed = imaging.process(img, PageSettings(mode=EnhanceMode.AUTO))
    out = build_pdf([processed], tmp_path / "scan.pdf", OutputOptions(ocr=True), originals=[src])
    with pymupdf.open(out) as doc:
        text = doc[0].get_text()
    assert "ATTESTATION" in text and "Cotonou" in text
    assert sha256(src) == before


def test_shadow_removal_keeps_id_photo():
    """Régression : la grande zone sombre (photo d'identité) ne doit pas être blanchie."""
    card = cv2.resize(make_card(), (PAGE_W, int(PAGE_W / ID1_ASPECT)))
    photo, _ = make_photo(page=card, size=(2600, 2000))
    out = imaging.process(photo, PageSettings(mode=EnhanceMode.COLOR), DocumentKind.ID_CARD)
    h, w = out.shape[:2]
    # La photo occupe x ∈ [40, 260] / 856 et y ∈ [120, 420] / 540 de la carte.
    region = out[int(h * 0.30):int(h * 0.70), int(w * 0.08):int(w * 0.26)]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    assert np.median(gray) < 170  # reste nettement plus sombre que le papier (~250)
