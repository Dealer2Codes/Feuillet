"""Conversions d'images (Pillow) : JPG, PNG, WebP, BMP, TIFF, GIF, ICO, AVIF."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageSequence, features

from feuillet.convert.base import ConversionError, Progress, unique_path
from feuillet.core.limits import MAX_FRAMES

# format de sortie -> (nom Pillow, extension)
OUTPUT_FORMATS: dict[str, tuple[str, str]] = {
    "jpg": ("JPEG", ".jpg"),
    "png": ("PNG", ".png"),
    "webp": ("WEBP", ".webp"),
    "bmp": ("BMP", ".bmp"),
    "tiff": ("TIFF", ".tiff"),
    "gif": ("GIF", ".gif"),
    "ico": ("ICO", ".ico"),
}
if features.check("avif"):
    OUTPUT_FORMATS["avif"] = ("AVIF", ".avif")

INPUT_EXTENSIONS = (".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".ico")
if features.check("avif"):
    INPUT_EXTENSIONS += (".avif",)

# Formats sans transparence : le fond transparent est remplacé par cette couleur.
_NO_ALPHA = {"JPEG", "BMP"}
_BACKGROUNDS = {"white": (255, 255, 255), "black": (0, 0, 0)}


def _prepare(im: Image.Image, pil_format: str, background: str) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if pil_format in _NO_ALPHA:
        if has_alpha:
            rgba = im.convert("RGBA")
            base = Image.new("RGB", rgba.size, _BACKGROUNDS.get(background, (255, 255, 255)))
            base.paste(rgba, mask=rgba.getchannel("A"))
            return base
        return im.convert("RGB") if im.mode not in ("RGB", "L") else im
    if pil_format == "ICO":
        return im.convert("RGBA")
    if pil_format in ("WEBP", "AVIF") and im.mode not in ("RGB", "RGBA", "L"):
        return im.convert("RGBA" if has_alpha else "RGB")
    if pil_format == "PNG" and im.mode == "CMYK":
        return im.convert("RGB")
    return im


def convert_image(source: Path, out_dir: Path, fmt: str, quality: int = 90, background: str = "white") -> Path:
    if fmt not in OUTPUT_FORMATS:
        raise ConversionError("convert_unsupported_format", fmt=fmt)
    pil_format, ext = OUTPUT_FORMATS[fmt]
    try:
        with Image.open(source) as im:
            frames = []
            for f in ImageSequence.Iterator(im):
                frames.append(f.copy())
                if len(frames) >= MAX_FRAMES:
                    break
            info_duration = im.info.get("duration")
    except Image.DecompressionBombError as exc:
        raise ConversionError("image_too_large", path=str(source)) from exc
    except (OSError, ValueError) as exc:
        raise ConversionError("unreadable_image", path=str(source)) from exc
    out = unique_path(out_dir, source.stem, ext)
    first = _prepare(frames[0], pil_format, background)
    params: dict = {}
    if pil_format in ("JPEG", "WEBP", "AVIF"):
        params["quality"] = int(quality)
    if pil_format == "JPEG":
        params.update(optimize=True, progressive=True)
    if pil_format == "PNG":
        params["optimize"] = True
    if pil_format == "ICO":
        size = min(256, max(first.size))
        params["sizes"] = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= size]
    exif = frames[0].getexif()
    if exif and pil_format in ("JPEG", "WEBP", "PNG", "TIFF"):
        exif.pop(0x0112, None)  # orientation déjà appliquée
        # Confidentialité : la position GPS d'une photo de téléphone n'est pas recopiée.
        exif.pop(0x8825, None)
        params["exif"] = exif.tobytes()
    # Animation conservée quand le format cible la gère (GIF, WebP, TIFF multipage).
    if len(frames) > 1 and pil_format in ("GIF", "WEBP", "TIFF", "AVIF"):
        rest = [_prepare(f, pil_format, background) for f in frames[1:]]
        params.update(save_all=True, append_images=rest)
        if info_duration and pil_format != "TIFF":
            params.update(duration=info_duration, loop=0)
    first.save(out, format=pil_format, **params)
    return out


def run_convert_images(files: list[Path], out_dir: Path, options: dict, progress: Progress | None = None) -> list[Path]:
    results = []
    for i, f in enumerate(files, 1):
        results.append(convert_image(f, out_dir, options["format"], options["quality"], options["background"]))
        if progress:
            progress(i, len(files))
    return results
