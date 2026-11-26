"""Filigrane natif dans un document Word (DOCX), sans conversion en PDF.

On insère dans l'en-tête de chaque section la même forme que celle créée par
Word (Création > Filigrane) :
- texte : forme WordArt VML « PowerPlusWaterMarkObject » ;
- image : image VML « WordPictureWatermark », derrière le texte.

Word reconnaît donc le filigrane comme le sien (« Supprimer le filigrane »
fonctionne) et le document reste entièrement modifiable.

Limite : un DOCX n'a pas de pages fixes (la pagination est calculée à
l'affichage). Le filigrane s'applique par section, pas par numéro de page.
"""

from __future__ import annotations

import copy
import io
import itertools
import os
import random
from collections.abc import Iterable
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import docx
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from PIL import Image

from feuillet.core.errors import InputFileError, WatermarkError
from feuillet.core.files import atomic_write, ensure_new_output, verify_docx
from feuillet.watermark.models import Position, WatermarkKind, WatermarkSpec

NS_DECL = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office" '
    'xmlns:w10="urn:schemas-microsoft-com:office:word" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)

# Définitions de formes standard de Word (WordArt « plain text » et image).
SHAPETYPE_TEXT = (
    '<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" '
    'path="m@7,l@8,m@5,21600l@6,21600e"><v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/>'
    '<v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/>'
    '<v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/>'
    '<v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/></v:formulas>'
    '<v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" '
    'o:connectangles="270,180,90,0"/><v:textpath on="t" fitshape="t"/><v:handles>'
    '<v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles>'
    '<o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>'
)
SHAPETYPE_PICTURE = (
    '<v:shapetype id="_x0000_t75" coordsize="21600,21600" o:spt="75" o:preferrelative="t" '
    'path="m@4@5l@4@11@9@11@9@5xe" filled="f" stroked="f"><v:stroke joinstyle="miter"/><v:formulas>'
    '<v:f eqn="if lineDrawn pixelLineWidth 0"/><v:f eqn="sum @0 1 0"/><v:f eqn="sum 0 0 @1"/>'
    '<v:f eqn="prod @2 1 2"/><v:f eqn="prod @3 21600 pixelWidth"/><v:f eqn="prod @3 21600 pixelHeight"/>'
    '<v:f eqn="sum @0 0 1"/><v:f eqn="prod @6 1 2"/><v:f eqn="prod @7 21600 pixelWidth"/>'
    '<v:f eqn="sum @8 21600 0"/><v:f eqn="prod @7 21600 pixelHeight"/><v:f eqn="sum @10 21600 0"/>'
    '</v:formulas><v:path o:extrusionok="f" gradientshapeok="t" o:connecttype="rect"/>'
    '<o:lock v:ext="edit" aspectratio="t"/></v:shapetype>'
)

WATERMARK_ID_PREFIXES = ("PowerPlusWaterMarkObject", "WordPictureWatermark")

_H = {Position.TOP_LEFT: "left", Position.BOTTOM_LEFT: "left", Position.TOP_RIGHT: "right",
      Position.BOTTOM_RIGHT: "right"}
_V = {Position.TOP: "top", Position.TOP_LEFT: "top", Position.TOP_RIGHT: "top", Position.BOTTOM: "bottom",
      Position.BOTTOM_LEFT: "bottom", Position.BOTTOM_RIGHT: "bottom"}

_spid = itertools.count(2049)


def _position_style(spec: WatermarkSpec, width: float, height: float, page_w: float, page_h: float) -> str:
    if spec.position is Position.CUSTOM:
        left = spec.custom_x * page_w - width / 2
        top = spec.custom_y * page_h - height / 2
        return (f"margin-left:{left:.1f}pt;margin-top:{top:.1f}pt;"
                "mso-position-horizontal-relative:page;mso-position-vertical-relative:page")
    return (f"margin-left:0;margin-top:0;mso-position-horizontal:{_H.get(spec.position, 'center')};"
            "mso-position-horizontal-relative:margin;"
            f"mso-position-vertical:{_V.get(spec.position, 'center')};mso-position-vertical-relative:margin")


def _vml_rotation(angle: float) -> float:
    """Notre angle est anti-horaire ; VML compte dans le sens horaire."""
    return round((-angle) % 360, 2)


def _text_shape_xml(spec: WatermarkSpec, page_w: float, page_h: float, avail_w: float) -> str:
    # Taille de la boîte : Word adapte le texte à la boîte (fitshape).
    width = min(len(spec.text) * spec.font_size * 0.62, avail_w * 1.25)
    height = spec.font_size * 1.0
    style = (f"position:absolute;{_position_style(spec, width, height, page_w, page_h)};"
             f"width:{width:.1f}pt;height:{height:.1f}pt;rotation:{_vml_rotation(spec.angle)};"
             "z-index:-251657216")
    shape_id = f"PowerPlusWaterMarkObject{random.randint(10**8, 10**9 - 1)}"  # noqa: S311 - identifiant de forme, sans enjeu
    font = escape(spec.font_name.replace('"', "").replace(";", ""))
    return (
        f'<w:r {NS_DECL}><w:rPr><w:noProof/></w:rPr><w:pict>{SHAPETYPE_TEXT}'
        f'<v:shape id="{shape_id}" o:spid="_x0000_s{next(_spid)}" type="#_x0000_t136" style="{style}" '
        f'o:allowincell="f" fillcolor="#{spec.color_hex}" stroked="f">'
        f'<v:fill opacity="{spec.opacity:.2f}"/>'
        f'<v:textpath style="font-family:&quot;{font}&quot;;font-size:1pt" string={quoteattr(spec.text)}/>'
        '<w10:wrap anchorx="margin" anchory="margin"/></v:shape></w:pict></w:r>'
    )


def _picture_png(spec: WatermarkSpec) -> tuple[bytes, float]:
    """PNG avec l'opacité appliquée au canal alpha (Word la respecte)."""
    try:
        with Image.open(spec.image_path) as im:
            im = im.convert("RGBA")
    except Image.DecompressionBombError as exc:
        raise WatermarkError("image_too_large", path=str(spec.image_path)) from exc
    except (OSError, ValueError, TypeError) as exc:
        raise WatermarkError("image_unreadable", path=str(spec.image_path)) from exc
    im.putalpha(im.getchannel("A").point(lambda a: round(a * spec.opacity)))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue(), im.height / im.width


def _picture_shape_xml(spec: WatermarkSpec, rid: str, ratio: float, page_w: float, page_h: float,
                       avail_w: float) -> str:
    width = spec.image_scale * page_w
    width = min(width, avail_w)
    height = width * ratio
    style = (f"position:absolute;{_position_style(spec, width, height, page_w, page_h)};"
             f"width:{width:.1f}pt;height:{height:.1f}pt;rotation:{_vml_rotation(spec.angle)};"
             "z-index:-251656192")
    shape_id = f"WordPictureWatermark{random.randint(10**8, 10**9 - 1)}"  # noqa: S311 - identifiant de forme, sans enjeu
    return (
        f'<w:r {NS_DECL}><w:rPr><w:noProof/></w:rPr><w:pict>{SHAPETYPE_PICTURE}'
        f'<v:shape id="{shape_id}" o:spid="_x0000_s{next(_spid)}" type="#_x0000_t75" style="{style}" '
        f'o:allowincell="f"><v:imagedata r:id="{rid}" o:title=""/>'
        '<w10:wrap anchorx="margin" anchory="margin"/></v:shape></w:pict></w:r>'
    )


def _headers_of(section, even_and_odd: bool) -> list:
    headers = [section.header]
    if section.different_first_page_header_footer:
        headers.append(section.first_page_header)
    if even_and_odd:
        headers.append(section.even_page_header)
    return headers


def remove_existing_watermarks(doc: docx.document.Document) -> int:
    """Retire les filigranes Word existants (les nôtres et ceux créés par Word)."""
    removed = 0
    for section in doc.sections:
        for header in _headers_of(section, True):
            if header.is_linked_to_previous:
                continue
            for pict in list(header._element.iter(qn("w:pict"))):
                shapes = [el for el in pict.iter() if el.get("id", "").startswith(WATERMARK_ID_PREFIXES)]
                if shapes:
                    run = pict.getparent()
                    run.getparent().remove(run)
                    removed += 1
    return removed


def apply_docx_watermark(source: str | os.PathLike, output: str | os.PathLike, spec: WatermarkSpec,
                         sections: Iterable[int] | None = None, replace_existing: bool = True,
                         overwrite: bool = False) -> Path:
    """Crée ``output`` = ``source`` + filigrane, dans les sections choisies (base 1).

    ``sections=None`` : toutes les sections, donc toutes les pages.
    """
    spec.validate()
    if spec.tile:
        raise WatermarkError("docx_tile_unsupported")
    out = ensure_new_output(output, source, overwrite=overwrite)
    try:
        doc = docx.Document(str(source))
    except Exception as exc:
        raise InputFileError("unreadable_docx", path=str(source)) from exc

    if replace_existing:
        remove_existing_watermarks(doc)
    settings = doc.settings.element
    even_and_odd = settings.find(qn("w:evenAndOddHeaders")) is not None
    wanted = set(sections) if sections else None
    picture = _picture_png(spec) if spec.kind is WatermarkKind.IMAGE else None

    total = len(doc.sections)
    if wanted and (min(wanted) < 1 or max(wanted) > total):
        raise WatermarkError("section_out_of_range", total=total)

    for number, section in enumerate(doc.sections, 1):
        if wanted is not None and number not in wanted:
            # Une section exclue ne doit pas hériter du filigrane de la précédente.
            for header in _headers_of(section, even_and_odd):
                if header.is_linked_to_previous and number > 1:
                    _unlink_without_watermark(header)
            continue
        page_w = section.page_width.pt if section.page_width else 595.3
        page_h = section.page_height.pt if section.page_height else 841.9
        avail_w = page_w - (section.left_margin.pt if section.left_margin else 72) - (
            section.right_margin.pt if section.right_margin else 72)
        for header in _headers_of(section, even_and_odd):
            if header.is_linked_to_previous and number > 1:
                if wanted is None or number - 1 in wanted:
                    continue  # hérite déjà du filigrane de la section précédente
                # Sinon, écrire ici modifierait l'en-tête partagé de la section
                # précédente (exclue) : on crée d'abord un en-tête propre.
                _unlink_without_watermark(header)
            paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
            if picture:
                rid, _ = header.part.get_or_add_image(io.BytesIO(picture[0]))
                xml = _picture_shape_xml(spec, rid, picture[1], page_w, page_h, avail_w)
            else:
                xml = _text_shape_xml(spec, page_w, page_h, avail_w)
            paragraph._p.append(parse_xml(xml))

    atomic_write(out, lambda tmp: doc.save(str(tmp)))
    verify_docx(out)
    return out


def _unlink_without_watermark(header) -> None:
    """Coupe le lien avec l'en-tête précédent en recopiant son contenu sans filigrane."""
    previous = _previous_definition(header)
    header.is_linked_to_previous = False  # crée une définition vide
    if previous is None:
        return
    target = header._element
    for child in list(target):
        target.remove(child)
    for child in previous:
        clone = copy.deepcopy(child)
        for pict in list(clone.iter(qn("w:pict"))):
            if any(el.get("id", "").startswith(WATERMARK_ID_PREFIXES) for el in pict.iter()):
                run = pict.getparent()
                run.getparent().remove(run)
        target.append(clone)
    # Les images de l'en-tête précédent ne sont pas recopiées (relations
    # différentes) : on retire les références orphelines pour garder un
    # document valide.
    for blip in list(target.iter(qn("a:blip"))):
        drawing = blip
        while drawing is not None and drawing.tag != qn("w:drawing"):
            drawing = drawing.getparent()
        if drawing is not None and drawing.getparent() is not None:
            drawing.getparent().remove(drawing)


def _previous_definition(header):
    """Élément XML de l'en-tête effectivement affiché (celui de la section précédente)."""
    try:
        return header._get_or_add_definition()._element  # lit sans créer si lié
    except Exception:
        return None


def count_sections(path: str | os.PathLike) -> int:
    try:
        return len(docx.Document(str(path)).sections)
    except Exception as exc:
        raise InputFileError("unreadable_docx", path=str(path)) from exc
