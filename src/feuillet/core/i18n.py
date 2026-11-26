"""Traductions français / anglais.

Les textes sont rangés dans ``feuillet/locales/<langue>.json`` sous forme de
clés à points (``scanner.generate_pdf``). Une clé absente dans la langue
active retombe sur le français, puis sur la clé elle-même : l'interface ne
plante jamais à cause d'une traduction manquante.
"""

from __future__ import annotations

import json
import locale
from functools import cache
from importlib import resources

SUPPORTED_LANGUAGES = ("fr", "en")
DEFAULT_LANGUAGE = "fr"

_current = DEFAULT_LANGUAGE


@cache
def _catalog(lang: str) -> dict[str, str]:
    text = resources.files("feuillet.locales").joinpath(f"{lang}.json").read_text("utf-8")
    return json.loads(text)


def detect_system_language() -> str:
    try:
        code = (locale.getlocale()[0] or "").lower()
    except ValueError:
        code = ""
    return "en" if code.startswith("en") else DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    global _current
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Langue non prise en charge : {lang}")
    _current = lang


def current_language() -> str:
    return _current


def has_key(key: str) -> bool:
    return key in _catalog(_current) or key in _catalog(DEFAULT_LANGUAGE)


def tr(key: str, **params: object) -> str:
    text = _catalog(_current).get(key) or _catalog(DEFAULT_LANGUAGE).get(key) or key
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            return text
    return text
