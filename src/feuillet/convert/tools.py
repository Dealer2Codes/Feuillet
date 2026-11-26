"""Catalogue des outils de conversion (équivalent hors ligne d'iLovePDF)."""

from __future__ import annotations

from pathlib import Path

from feuillet.convert import images, office, pdf_tools
from feuillet.convert.base import (
    Category,
    ConversionError,
    Option,
    OptionKind,
    Progress,
    Tool,
    check_inputs,
)

K = OptionKind
PDF = (".pdf",)
TEXT_EXT = (".txt", ".md", ".html", ".htm")


def _ocr_unavailable() -> str | None:
    from feuillet.scanner import ocr

    return None if ocr.is_available("fra+eng") else "ocr_not_installed"


_ENGINE = Option("engine", K.CHOICE, "auto", ("auto", "msoffice", "libreoffice"))
_PAGES_ALL = Option("pages", K.PAGES, "")  # vide = toutes
_PAGES_REQ = Option("pages", K.PAGES, "", required=True)
_PAGE_SIZE = Option("page_size", K.CHOICE, "A4", ("A4", "Letter"))

TOOLS: tuple[Tool, ...] = (
    # ---------------------------------------------------------------- vers PDF
    Tool("word_to_pdf", Category.TO_PDF, office.WORD_EXT, office.run_office_to_pdf, (_ENGINE,),
         available=office.office_unavailable),
    Tool("excel_to_pdf", Category.TO_PDF, office.EXCEL_EXT, office.run_office_to_pdf, (_ENGINE,),
         available=office.office_unavailable),
    Tool("powerpoint_to_pdf", Category.TO_PDF, office.POWERPOINT_EXT, office.run_office_to_pdf, (_ENGINE,),
         available=office.office_unavailable),
    Tool("images_to_pdf", Category.TO_PDF, images.INPUT_EXTENSIONS, pdf_tools.images_to_pdf, (
        Option("page_size", K.CHOICE, "A4", ("A4", "Letter", "original")),
        Option("dpi", K.CHOICE, "200", ("150", "200", "300")),
        Option("quality", K.INT, 85, minimum=40, maximum=95),
        Option("name", K.TEXT, ""),
    ), combine=True),
    Tool("text_to_pdf", Category.TO_PDF, TEXT_EXT, pdf_tools.text_to_pdf, (_PAGE_SIZE,)),
    # ---------------------------------------------------------------- depuis PDF
    Tool("pdf_to_word", Category.FROM_PDF, PDF, pdf_tools.pdf_to_word),
    Tool("pdf_to_excel", Category.FROM_PDF, PDF, pdf_tools.pdf_to_excel),
    Tool("pdf_to_powerpoint", Category.FROM_PDF, PDF, pdf_tools.pdf_to_powerpoint, (
        Option("dpi", K.CHOICE, "150", ("100", "150", "200")),
    )),
    Tool("pdf_to_images", Category.FROM_PDF, PDF, pdf_tools.pdf_to_images, (
        Option("format", K.CHOICE, "jpg", ("jpg", "png", "webp")),
        Option("dpi", K.CHOICE, "150", ("72", "150", "200", "300")),
        Option("quality", K.INT, 90, minimum=40, maximum=100),
        _PAGES_ALL,
    )),
    Tool("pdf_to_text", Category.FROM_PDF, PDF, pdf_tools.pdf_to_text),
    # ---------------------------------------------------------------- images
    Tool("convert_images", Category.IMAGES, images.INPUT_EXTENSIONS, images.run_convert_images, (
        Option("format", K.CHOICE, "jpg", tuple(images.OUTPUT_FORMATS)),
        Option("quality", K.INT, 90, minimum=40, maximum=100),
        Option("background", K.CHOICE, "white", ("white", "black")),
    )),
    # ---------------------------------------------------------------- bureautique
    Tool("office_convert", Category.OFFICE, office.OFFICE_EXT, office.run_office_convert, (
        Option("format", K.CHOICE, "docx", ("docx", "doc", "odt", "rtf", "txt", "xlsx", "xls", "ods", "csv",
                                             "pptx", "ppt", "odp")),
        _ENGINE,
    ), available=office.office_unavailable),
    # ---------------------------------------------------------------- organiser
    Tool("merge", Category.ORGANIZE, PDF, pdf_tools.merge, (Option("name", K.TEXT, ""),), combine=True,
         min_files=2),
    Tool("split", Category.ORGANIZE, PDF, pdf_tools.split, (
        Option("mode", K.CHOICE, "every_page", ("every_page", "every_n", "ranges")),
        Option("every", K.INT, 2, minimum=1, maximum=500),
        Option("ranges", K.TEXT, ""),
    )),
    Tool("extract_pages", Category.ORGANIZE, PDF, pdf_tools.extract_pages, (_PAGES_REQ,)),
    Tool("delete_pages", Category.ORGANIZE, PDF, pdf_tools.delete_pages, (_PAGES_REQ,)),
    Tool("reorder", Category.ORGANIZE, PDF, pdf_tools.reorder, (
        Option("order", K.TEXT, "", required=True),
        Option("append_rest", K.BOOL, True),
    )),
    Tool("rotate", Category.ORGANIZE, PDF, pdf_tools.rotate, (
        Option("angle", K.CHOICE, "90", ("90", "180", "270")),
        _PAGES_ALL,
    )),
    # ---------------------------------------------------------------- optimiser / sécuriser
    Tool("compress", Category.OPTIMIZE, PDF, pdf_tools.compress, (
        Option("level", K.CHOICE, "medium", ("low", "medium", "high")),
    )),
    Tool("protect", Category.OPTIMIZE, PDF, pdf_tools.protect, (
        Option("password", K.PASSWORD, "", required=True),
        Option("allow_print", K.BOOL, True),
        Option("allow_copy", K.BOOL, False),
    )),
    Tool("unlock", Category.OPTIMIZE, PDF, pdf_tools.unlock, (Option("password", K.PASSWORD, "", required=True),)),
    Tool("page_numbers", Category.OPTIMIZE, PDF, pdf_tools.page_numbers, (
        Option("position", K.CHOICE, "bottom_center", ("bottom_center", "bottom_right", "bottom_left",
                                                       "top_center", "top_right", "top_left")),
        Option("template", K.TEXT, "{n} / {total}"),
        Option("start", K.INT, 1, minimum=0, maximum=9999),
        _PAGES_ALL,
    )),
    Tool("ocr_pdf", Category.OPTIMIZE, PDF, pdf_tools.ocr_pdf, (
        Option("languages", K.CHOICE, "fra+eng", ("fra+eng", "fra", "eng")),
        Option("force", K.BOOL, False),
    ), available=_ocr_unavailable),
    Tool("repair", Category.OPTIMIZE, PDF, pdf_tools.repair),
)

BY_ID = {t.id: t for t in TOOLS}


def tools_for(path: Path) -> list[Tool]:
    """Outils qui acceptent ce fichier (pour proposer les actions possibles)."""
    return [t for t in TOOLS if t.accepts(path)]


def validate_options(tool: Tool, options: dict) -> dict:
    merged = {**tool.defaults(), **options}
    for opt in tool.options:
        value = merged.get(opt.name)
        if opt.required and (value is None or str(value).strip() == ""):
            raise ConversionError("convert_option_required", option=opt.name)
        if opt.kind is K.CHOICE and str(value) not in opt.choices:
            raise ConversionError("convert_invalid_option", option=opt.name, value=value)
        if opt.kind is K.INT:
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ConversionError("convert_invalid_option", option=opt.name, value=value) from None
            merged[opt.name] = max(opt.minimum, min(opt.maximum, number))
    return merged


def run_tool(tool_id: str, files: list[Path], out_dir: Path, options: dict | None = None,
             progress: Progress | None = None) -> list[Path]:
    """Exécute un outil. Les sources ne sont jamais modifiées ; renvoie les fichiers créés."""
    tool = BY_ID[tool_id]
    files = [Path(f) for f in files]
    out_dir = Path(out_dir)
    missing = tool.available()
    if missing:
        raise ConversionError(missing)
    check_inputs(tool, files)
    if not out_dir.is_dir():
        raise ConversionError("output_dir_missing", path=str(out_dir))
    return tool.run(files, out_dir, validate_options(tool, options or {}), progress)
