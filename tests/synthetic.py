"""Images de test générées : un document « photographié » de façon réaliste.

Page blanche avec du texte, une signature bleue et un tampon rouge, posée en
biais sur une table sombre, avec une ombre. Aucun fichier externe requis.
"""

from __future__ import annotations

import cv2
import numpy as np

PAGE_W, PAGE_H = 1240, 1754  # A4 à 150 DPI

LINES = [
    "ATTESTATION DE DOMICILE",
    "Je soussigne Jean Dupont, demeurant a Cotonou,",
    "certifie que les informations ci-dessous sont exactes.",
    "Fait pour servir et valoir ce que de droit.",
    "Reference : 2026-11-0457",
    "Montant : 125 000 FCFA",
]


def make_page(with_marks: bool = True) -> np.ndarray:
    page = np.full((PAGE_H, PAGE_W, 3), 250, np.uint8)
    y = 180
    for i, line in enumerate(LINES * 3):
        scale = 1.4 if i == 0 else 1.0
        cv2.putText(page, line, (110, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 20, 20), 2 if i else 3, cv2.LINE_AA)
        y += 70
    # petits caractères
    cv2.putText(page, "mentions legales en petits caracteres - ne pas effacer", (110, PAGE_H - 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
    if with_marks:
        # signature bleue
        t = np.linspace(0, 4 * np.pi, 200)
        pts = np.stack([800 + t * 18, 1450 + 40 * np.sin(t * 1.7)], axis=1).astype(np.int32)
        cv2.polylines(page, [pts], False, (170, 60, 20), 4, cv2.LINE_AA)
        # tampon rouge
        cv2.circle(page, (400, 1450), 110, (40, 40, 200), 6, cv2.LINE_AA)
        cv2.putText(page, "MAIRIE", (325, 1465), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (40, 40, 200), 3, cv2.LINE_AA)
    return page


def make_photo(page: np.ndarray | None = None, size=(2000, 2600), shadow: bool = True, seed: int = 3):
    """Renvoie (photo, coins_vrais) : page déformée en perspective sur une table."""
    rng = np.random.default_rng(seed)
    page = make_page() if page is None else page
    w, h = size
    table = np.full((h, w, 3), (60, 75, 95), np.uint8)
    noise = rng.normal(0, 8, (h, w, 1)).astype(np.int16)
    table = np.clip(table.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    ph, pw = page.shape[:2]
    corners = camera_corners(pw / ph, size)
    src = np.array([[0, 0], [pw - 1, 0], [pw - 1, ph - 1], [0, ph - 1]], np.float32)
    m = cv2.getPerspectiveTransform(src, corners)
    warped = cv2.warpPerspective(page, m, (w, h))
    mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), m, (w, h))
    photo = table.copy()
    photo[mask > 0] = warped[mask > 0]
    if shadow:
        xx = np.linspace(0, 1, w)[None, :, None]
        yy = np.linspace(0, 1, h)[:, None, None]
        light = 0.55 + 0.45 * np.clip(xx * 0.8 + yy * 0.6, 0, 1)
        photo = np.clip(photo * light, 0, 255).astype(np.uint8)
    return photo, corners


def camera_corners(aspect: float, size=(2000, 2600), tilt_x=18.0, tilt_y=-10.0, roll=4.0) -> np.ndarray:
    """Coins d'une feuille plane photographiée par un vrai appareil (sténopé).

    Contrairement à 4 points choisis au hasard, cette projection respecte la
    géométrie réelle : on peut donc vérifier que les proportions sont retrouvées.
    """
    w, h = size
    f = 1.1 * max(w, h)
    half_h = 1.0 / max(1.0, aspect)  # l'objet tient toujours dans le cadre
    half_w = half_h * aspect
    pts = np.array([[-half_w, -half_h, 0], [half_w, -half_h, 0], [half_w, half_h, 0], [-half_w, half_h, 0]])
    ax, ay, az = np.radians([tilt_x, tilt_y, roll])
    rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    cam = pts @ (rz @ ry @ rx).T + np.array([0.05, 0.0, 2.9])
    proj = np.stack([f * cam[:, 0] / cam[:, 2] + w / 2, f * cam[:, 1] / cam[:, 2] + h / 2], axis=1)
    return proj.astype(np.float32)


def make_card(width: int = 856, height: int = 540) -> np.ndarray:
    card = np.full((height, width, 3), (215, 230, 240), np.uint8)
    cv2.rectangle(card, (40, 120), (260, 420), (150, 120, 100), -1)  # photo
    cv2.putText(card, "CARTE NATIONALE D'IDENTITE", (290, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 40, 20), 2)
    for i, txt in enumerate(["NOM : DUPONT", "PRENOM : JEAN", "NE LE : 01.01.1990"]):
        cv2.putText(card, txt, (300, 180 + 60 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (30, 30, 30), 2)
    return card
