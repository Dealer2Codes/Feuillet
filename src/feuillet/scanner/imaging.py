"""Traitement d'image des documents photographiés ou numérisés (OpenCV).

Principe de prudence (cahier des charges, 15.B) : aucun traitement ne doit
effacer une signature, un tampon, une photo ou de petits caractères.
- Le mode Automatique n'applique jamais de binarisation pure.
- Le mode Noir et blanc conserve en couleur les marques colorées.
- En cas de doute sur la détection des bords, l'image entière est gardée.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageSequence

from feuillet.core.errors import ImageProcessingError, InputFileError
from feuillet.core.limits import MAX_FRAMES
from feuillet.scanner.models import (
    ID1_ASPECT,
    Corners,
    DocumentKind,
    EnhanceMode,
    PageSettings,
)

SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif")

# Taille de travail pour la détection (rapide et assez précise).
_DETECT_MAX_SIDE = 1000
# Le document détecté doit couvrir au moins cette part de l'image.
_MIN_DOC_AREA_RATIO = 0.20


# --------------------------------------------------------------------------- E/S


def load_images(path: str | Path) -> list[np.ndarray]:
    """Charge une image (ou chaque page d'un TIFF multipage) en BGR uint8.

    L'orientation EXIF des photos de téléphone est appliquée.
    """
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise InputFileError("unsupported_image", path=str(path))
    try:
        with Image.open(path) as im:
            frames = []
            for frame in ImageSequence.Iterator(im):
                frame = ImageOps.exif_transpose(frame)
                frames.append(pil_to_bgr(frame))
                if path.suffix.lower() not in (".tif", ".tiff") or len(frames) >= MAX_FRAMES:
                    break
    except Image.DecompressionBombError as exc:
        raise InputFileError("image_too_large", path=str(path)) from exc
    except (OSError, ValueError) as exc:
        raise InputFileError("unreadable_image", path=str(path)) from exc
    if not frames:
        raise InputFileError("unreadable_image", path=str(path))
    return frames


def pil_to_bgr(im: Image.Image) -> np.ndarray:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        background = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(background, im)
    im = im.convert("RGB")
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def bgr_to_pil(img: np.ndarray) -> Image.Image:
    if img.ndim == 2:
        return Image.fromarray(img)
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


# ---------------------------------------------------------------- géométrie


def rotate_quarter(img: np.ndarray, degrees: int) -> np.ndarray:
    """Rotation exacte de 90/180/270° dans le sens horaire, sans perte."""
    degrees %= 360
    if degrees == 0:
        return img
    code = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(degrees)
    if code is None:
        raise ImageProcessingError("invalid_rotation", degrees=degrees)
    return cv2.rotate(img, code)


def order_corners(pts: np.ndarray) -> Corners:
    """Range 4 points : haut-gauche, haut-droit, bas-droit, bas-gauche."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def full_frame(img: np.ndarray) -> Corners:
    h, w = img.shape[:2]
    return np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)


def detect_document(img: np.ndarray) -> Corners | None:
    """Cherche le contour du document (plus grand quadrilatère convexe).

    Renvoie ``None`` si aucun contour fiable n'est trouvé : l'appelant garde
    alors l'image entière plutôt que de risquer un mauvais recadrage.
    """
    h, w = img.shape[:2]
    scale = _DETECT_MAX_SIDE / max(h, w) if max(h, w) > _DETECT_MAX_SIDE else 1.0
    small = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    min_area = _MIN_DOC_AREA_RATIO * small.shape[0] * small.shape[1]

    candidates: list[np.ndarray] = []
    # 1) contours par gradient (Canny), 2) séparation fond / papier (Otsu)
    median = float(np.median(gray))
    edges = cv2.Canny(gray, int(max(0, 0.66 * median)), int(min(255, 1.33 * median)))
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu = cv2.morphologyEx(otsu, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))

    for mask in (edges, otsu, cv2.bitwise_not(otsu)):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            if cv2.contourArea(c) < min_area:
                break
            hull = cv2.convexHull(c)
            peri = cv2.arcLength(hull, True)
            for eps in (0.02, 0.03, 0.05):
                approx = cv2.approxPolyDP(hull, eps * peri, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    candidates.append(approx.reshape(4, 2).astype(np.float32))
                    break

    best = None
    best_area = 0.0
    frame_area = small.shape[0] * small.shape[1]
    for quad in candidates:
        area = cv2.contourArea(quad)
        # Un quadrilatère qui touche tout le cadre n'apporte rien (c'est l'image).
        if area >= 0.985 * frame_area or area < min_area:
            continue
        if not _plausible_quad(quad):
            continue
        if area > best_area:
            best, best_area = quad, area
    if best is None:
        return None
    quad = order_corners(best / scale)
    # Léger retrait vers l'intérieur : les contours détectés incluent souvent
    # le liseré sombre de la table.
    centre = quad.mean(axis=0)
    inset = 0.004 * float(np.hypot(h, w))
    vectors = centre - quad
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
    return (quad + vectors * inset).astype(np.float32)


def _plausible_quad(quad: np.ndarray) -> bool:
    """Rejette les quadrilatères trop déformés (angles < 45° ou > 135°)."""
    q = order_corners(quad)
    for i in range(4):
        a, b, c = q[i - 1], q[i], q[(i + 1) % 4]
        v1, v2 = a - b, c - b
        cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
        if not 45 <= angle <= 135:
            return False
    return True


def estimate_aspect(corners: Corners, image_size: tuple[int, int]) -> float | None:
    """Rapport largeur/hauteur réel d'un rectangle photographié en perspective.

    Méthode de Zhang et He (« Whiteboard scanning and image enhancement »,
    2007) : on estime la focale à partir du quadrilatère, en supposant le
    centre optique au centre de l'image, puis on en déduit les vraies
    proportions. Sans cela, mesurer les bords sur la photo étire le document.
    Renvoie ``None`` si le calcul est instable (l'appelant garde la mesure simple).
    """
    w, h = image_size
    u0, v0 = w / 2.0, h / 2.0
    tl, tr, br, bl = order_corners(corners)
    m1, m2, m3, m4 = (np.array([p[0], p[1], 1.0]) for p in (tl, tr, bl, br))
    try:
        k2 = np.dot(np.cross(m1, m4), m3) / np.dot(np.cross(m2, m4), m3)
        k3 = np.dot(np.cross(m1, m4), m2) / np.dot(np.cross(m3, m4), m2)
    except FloatingPointError:
        return None
    n2 = k2 * m2 - m1
    n3 = k3 * m3 - m1
    if abs(n2[2] * n3[2]) < 1e-9:
        # Côtés parallèles sur la photo : pas de fuyante, la mesure directe suffit.
        return float(np.hypot(n2[0], n2[1]) / np.hypot(n3[0], n3[1]))
    f2 = -((n2[0] * n3[0] - (n2[0] * n3[2] + n2[2] * n3[0]) * u0 + n2[2] * n3[2] * u0 * u0)
           + (n2[1] * n3[1] - (n2[1] * n3[2] + n2[2] * n3[1]) * v0 + n2[2] * n3[2] * v0 * v0)) / (n2[2] * n3[2])
    if not np.isfinite(f2) or f2 <= 0:
        return None
    f = math.sqrt(f2)
    a = np.array([[f, 0, u0], [0, f, v0], [0, 0, 1.0]])
    a_inv = np.linalg.inv(a)
    q = a_inv.T @ a_inv
    ratio2 = (n2 @ q @ n2) / (n3 @ q @ n3)
    if not np.isfinite(ratio2) or ratio2 <= 0:
        return None
    ratio = math.sqrt(ratio2)
    # Garde-fou : une focale absurde donne des proportions extrêmes.
    return ratio if 0.2 < ratio < 5 else None


def warp_document(img: np.ndarray, corners: Corners, aspect: float | None = None) -> np.ndarray:
    """Corrige la perspective sans étirer le document.

    Les proportions réelles sont estimées à partir de la perspective
    (``estimate_aspect``) ; à défaut, on suit les longueurs mesurées des
    bords. Avec ``aspect`` (ex. format ID-1), le rapport est imposé, dans le
    sens (portrait ou paysage) mesuré sur la photo.
    """
    tl, tr, br, bl = order_corners(corners)
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    if width < 10 or height < 10:
        raise ImageProcessingError("frame_too_small")
    if not aspect:
        measured = estimate_aspect(corners, (img.shape[1], img.shape[0]))
        if measured:
            # On garde la plus grande dimension mesurée et on ajuste l'autre.
            if width >= height * measured:
                height = width / measured
            else:
                width = height * measured
    elif aspect:
        if width >= height:
            height = width / aspect
        else:
            height = width * aspect
    w, h = int(round(width)), int(round(height))
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype=np.float32), dst)
    return cv2.warpPerspective(img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def estimate_skew(img: np.ndarray, max_angle: float = 15.0) -> float:
    """Angle d'inclinaison des lignes de texte, en degrés (positif = sens anti-horaire).

    Renvoie 0 si le texte est insuffisant pour une mesure fiable.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = gray.shape
    scale = 1200 / max(h, w) if max(h, w) > 1200 else 1.0
    if scale < 1:
        gray = cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    # Relie les lettres d'une même ligne pour obtenir des traits horizontaux.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, gray.shape[1] // 40), 3))
    lines_img = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(lines_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles, weights = [], []
    for c in contours:
        rect = cv2.minAreaRect(c)
        (rw, rh) = rect[1]
        long_side, short_side = max(rw, rh), min(rw, rh)
        if long_side < gray.shape[1] * 0.08 or short_side == 0 or long_side / short_side < 4:
            continue
        # Angle du grand côté, calculé à partir des sommets : indépendant de la
        # convention d'angle de minAreaRect, qui varie selon les versions d'OpenCV.
        box = cv2.boxPoints(rect)
        edges = [box[(i + 1) % 4] - box[i] for i in range(4)]
        dx, dy = max(edges, key=lambda e: float(np.hypot(*e)))
        angle = math.degrees(math.atan2(float(dy), float(dx)))
        if angle > 90:
            angle -= 180
        elif angle <= -90:
            angle += 180
        if abs(angle) <= max_angle:
            angles.append(angle)
            weights.append(long_side)
    if len(angles) < 3:
        return 0.0
    order = np.argsort(angles)
    a, wts = np.asarray(angles)[order], np.asarray(weights)[order]
    cumulative = np.cumsum(wts)
    median = float(a[np.searchsorted(cumulative, cumulative[-1] / 2)])
    # minAreaRect mesure dans le repère image (y vers le bas) : on inverse.
    return -median


def rotate_free(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotation libre (anti-horaire), toile agrandie pour ne rien couper."""
    if abs(angle) < 0.05:
        return img
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    matrix[0, 2] += nw / 2 - w / 2
    matrix[1, 2] += nh / 2 - h / 2
    border = _border_color(img)
    return cv2.warpAffine(img, matrix, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=border)


def _border_color(img: np.ndarray) -> tuple[int, ...]:
    edge = np.concatenate([img[0], img[-1], img[:, 0], img[:, -1]])
    med = np.median(edge, axis=0)
    return tuple(int(v) for v in np.atleast_1d(med))


# ---------------------------------------------------------------- amélioration


def remove_shadows(img: np.ndarray) -> np.ndarray:
    """Divise chaque canal par une estimation du fond (papier + ombres).

    Le fond est obtenu en effaçant le texte (dilatation) puis en lissant
    (flou médian). Le texte et les marques gardent leur contraste relatif.
    """
    h, w = img.shape[:2]
    k = max(7, (min(h, w) // 100) | 1)
    blur = max(21, (min(h, w) // 25) | 1)
    planes = cv2.split(img) if img.ndim == 3 else [img]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    protect = _dark_content_mask(gray, k, blur)
    out = []
    for plane in planes:
        bg = cv2.dilate(plane, np.ones((k, k), np.uint8))
        bg = cv2.medianBlur(bg, min(blur, 255))
        if protect is not None:
            bg = _fill_background(bg, protect)
        norm = cv2.divide(plane, bg, scale=255)
        out.append(norm)
    return cv2.merge(out) if img.ndim == 3 else out[0]


def _dark_content_mask(gray: np.ndarray, k: int, blur: int) -> np.ndarray | None:
    """Grandes zones sombres (photo d'identité, aplat, logo) à ne pas « blanchir ».

    Une ombre assombrit le papier progressivement et modérément ; une photo
    est nettement plus sombre que le papier qui l'entoure. Sans cette
    protection, la division par le fond ferait disparaître la photo.
    """
    bg = cv2.medianBlur(cv2.dilate(gray, np.ones((k, k), np.uint8)), min(blur, 255))
    paper = float(np.percentile(bg, 90))
    if paper < 60:
        return None
    # Référence locale très large : le niveau du papier autour de la zone.
    big = max(31, (min(gray.shape) // 2) | 1)  # plus large qu'une photo d'identité
    small = cv2.resize(bg, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    surround = cv2.resize(cv2.dilate(small, np.ones((big // 4 | 1, big // 4 | 1), np.uint8)),
                          (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
    mask = (((bg < 0.62 * surround) & (bg < 0.75 * paper)) | (bg < 0.5 * paper)).astype(np.uint8) * 255
    if mask.mean() < 0.5:  # moins de 0,2 % de l'image : rien à protéger
        return None
    return cv2.dilate(mask, np.ones((k, k), np.uint8))


def _fill_background(bg: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Remplace le fond sous les zones protégées par celui du papier voisin."""
    scale = 0.2
    small_bg = cv2.resize(bg, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(mask, (small_bg.shape[1], small_bg.shape[0]), interpolation=cv2.INTER_NEAREST)
    filled = cv2.inpaint(small_bg, small_mask, 5, cv2.INPAINT_TELEA)
    filled = cv2.resize(filled, (bg.shape[1], bg.shape[0]), interpolation=cv2.INTER_LINEAR)
    return np.where(mask > 0, filled, bg).astype(np.uint8)


def white_balance(img: np.ndarray) -> np.ndarray:
    """Ramène le papier (pixels clairs) au blanc neutre."""
    if img.ndim != 3:
        return img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bright = gray >= np.percentile(gray, 90)
    if bright.sum() < 100:
        return img
    ref = img[bright].mean(axis=0)
    gains = 255.0 / np.maximum(ref, 1.0)
    gains = np.clip(gains / gains.max() * min(gains.max(), 1.6), 0.6, 1.6)
    return np.clip(img.astype(np.float32) * gains, 0, 255).astype(np.uint8)


def clahe(img: np.ndarray, clip: float = 2.0) -> np.ndarray:
    tool = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    if img.ndim == 2:
        return tool.apply(img)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    return cv2.cvtColor(cv2.merge((tool.apply(l), a, b)), cv2.COLOR_LAB2BGR)


def denoise(img: np.ndarray, strength: int = 4) -> np.ndarray:
    # Fenêtre de recherche réduite (11) : 3 à 4 fois plus rapide, suffisant
    # pour le grain d'une photo de téléphone.
    if img.ndim == 2:
        return cv2.fastNlMeansDenoising(img, None, strength, 5, 11)
    return cv2.fastNlMeansDenoisingColored(img, None, strength, strength, 5, 11)


def sharpen(img: np.ndarray, amount: float = 0.6, radius: float = 1.2) -> np.ndarray:
    blurred = cv2.GaussianBlur(img, (0, 0), radius)
    return cv2.addWeighted(img, 1 + amount, blurred, -amount, 0)


def adjust_brightness_contrast(img: np.ndarray, brightness: int = 0, contrast: int = 0) -> np.ndarray:
    """``brightness`` et ``contrast`` de -100 à 100 ; 0 = inchangé."""
    if brightness == 0 and contrast == 0:
        return img
    alpha = 1.0 + contrast / 100.0  # 0 .. 2
    beta = brightness * 1.28
    # Contraste centré sur le gris moyen pour ne pas décaler la luminosité.
    out = (img.astype(np.float32) - 128.0) * alpha + 128.0 + beta
    return np.clip(out, 0, 255).astype(np.uint8)


def colorfulness(img: np.ndarray) -> float:
    """Indice de Hasler et Süsstrunk (0 = gris ; > 15 = couleurs nettes)."""
    if img.ndim == 2:
        return 0.0
    b, g, r = cv2.split(img.astype(np.float32))
    rg = np.abs(r - g)
    yb = np.abs(0.5 * (r + g) - b)
    return float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))


def color_marks_mask(img: np.ndarray) -> np.ndarray:
    """Masque des marques colorées (encre bleue, tampons rouges, photos)."""
    if img.ndim == 2:
        return np.zeros(img.shape, np.uint8)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]
    mask = ((sat > 70) & (val > 40) & (val < 245)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return cv2.dilate(mask, np.ones((3, 3), np.uint8))


def has_color_content(img: np.ndarray, min_ratio: float = 0.002) -> bool:
    """Vrai si l'image contient des marques colorées ou est globalement colorée."""
    if img.ndim == 2:
        return False
    small = resize_to_max(img, 800)
    flat = white_balance(remove_shadows(small))
    return colorfulness(flat) > 15 or (color_marks_mask(flat) > 0).mean() > min_ratio


def binarize(img: np.ndarray, preserve_color_marks: bool = True) -> np.ndarray:
    """Noir et blanc par seuil local, tolérant aux variations d'éclairage.

    Avec ``preserve_color_marks``, les zones colorées sont recopiées de
    l'image source : une signature bleue ou un tampon rouge restent visibles.
    """
    flat = remove_shadows(img)
    gray = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY) if flat.ndim == 3 else flat
    h, w = gray.shape
    block = max(15, (min(h, w) // 40) | 1)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 10)
    # Les grandes zones sombres (aplats, photos) seraient évidées par le seuil
    # local : on les reprend du seuil global.
    _, global_bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    solid = cv2.erode(255 - global_bw, np.ones((block, block), np.uint8))
    region = cv2.dilate(solid, np.ones((block, block), np.uint8)) > 0
    bw[region] = global_bw[region]
    if not preserve_color_marks or img.ndim == 2:
        return bw
    mask = color_marks_mask(img)
    if mask.mean() < 0.05:  # pratiquement aucune couleur
        return bw
    out = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
    out[mask > 0] = flat[mask > 0]
    return out


def enhance(img: np.ndarray, settings: PageSettings) -> np.ndarray:
    mode = settings.mode
    if mode is EnhanceMode.ORIGINAL:
        return adjust_brightness_contrast(img, settings.brightness, settings.contrast)
    if mode is EnhanceMode.AUTO:
        # Jamais de binarisation en automatique : couleur ou niveaux de gris.
        # La moindre marque colorée (signature, tampon, photo) impose la couleur.
        mode = EnhanceMode.COLOR if has_color_content(img) else EnhanceMode.GRAYSCALE

    if mode is EnhanceMode.BLACK_WHITE:
        out = binarize(img, settings.preserve_color_marks)
        return adjust_brightness_contrast(out, settings.brightness, settings.contrast)

    out = remove_shadows(img) if settings.remove_shadows else img
    if mode is EnhanceMode.GRAYSCALE:
        out = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY) if out.ndim == 3 else out
    else:
        out = white_balance(out)
    out = clahe(out, 1.5 if settings.remove_shadows else 2.0)
    if settings.denoise:
        out = denoise(out, 3)
    if settings.sharpen:
        out = sharpen(out, 0.5)
    return adjust_brightness_contrast(out, settings.brightness, settings.contrast)


# ---------------------------------------------------------------- chaîne complète


def geometry(img: np.ndarray, settings: PageSettings, kind: DocumentKind = DocumentKind.DOCUMENT,
             osd_rotation: int = 0) -> np.ndarray:
    """Rotation, cadrage/perspective et redressement, sans amélioration."""
    out = rotate_quarter(img, settings.rotation + osd_rotation)
    corners = settings.corners
    if corners is None and settings.auto_detect:
        corners = detect_document(out)
    aspect = ID1_ASPECT if kind is DocumentKind.ID_CARD else None
    if corners is not None:
        out = warp_document(out, corners, aspect)
    if settings.deskew and kind is DocumentKind.DOCUMENT:
        out = rotate_free(out, -estimate_skew(out))
    return out


def process(img: np.ndarray, settings: PageSettings, kind: DocumentKind = DocumentKind.DOCUMENT,
            osd_rotation: int = 0) -> np.ndarray:
    return enhance(geometry(img, settings, kind, osd_rotation), settings)


def resize_to_max(img: np.ndarray, max_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    if max(h, w) <= max_side:
        return img
    s = max_side / max(h, w)
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def is_bilevel(img: np.ndarray) -> bool:
    if img.ndim != 2:
        return False
    values = np.unique(img[:: max(1, img.shape[0] // 200), :: max(1, img.shape[1] // 200)])
    return set(values.tolist()) <= {0, 255}
