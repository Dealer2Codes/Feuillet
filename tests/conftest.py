import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    import pymupdf

    path = tmp_path / "source.pdf"
    doc = pymupdf.open()
    for i, (w, h, rot) in enumerate([(595, 842, 0), (842, 595, 0), (595, 842, 90), (595, 842, 0)]):
        page = doc.new_page(width=w, height=h)
        page.insert_text((72, 100), f"Page {i + 1}", fontsize=18)
        page.set_rotation(rot)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    import docx
    from docx.enum.section import WD_SECTION

    path = tmp_path / "source.docx"
    d = docx.Document()
    d.sections[0].header.paragraphs[0].text = "En-tête société"
    d.add_paragraph("Premier paragraphe. " * 40)
    d.add_section(WD_SECTION.NEW_PAGE)
    d.add_paragraph("Deuxième section. " * 40)
    d.add_section(WD_SECTION.NEW_PAGE)
    d.add_paragraph("Troisième section. " * 40)
    d.save(path)
    return path


@pytest.fixture
def logo_png(tmp_path: Path) -> Path:
    import cv2
    import numpy as np

    img = np.zeros((200, 300, 4), np.uint8)
    cv2.circle(img, (150, 100), 80, (30, 30, 200, 255), -1)
    path = tmp_path / "logo.png"
    cv2.imwrite(str(path), img)
    return path


def tesseract_ready(langs: str = "fra+eng") -> bool:
    from feuillet.scanner import ocr

    return ocr.is_available(langs)
