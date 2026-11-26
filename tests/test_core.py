import json
import re
import string
from importlib import resources
from pathlib import Path

import pytest

from feuillet.core import i18n
from feuillet.core.errors import OutputFileError, WatermarkError
from feuillet.core.files import ensure_new_output, suggest_output_name
from feuillet.core.platform_check import evaluate

SRC = Path(__file__).parents[1] / "src" / "feuillet"


# ------------------------------------------------------------ Windows 10/11


@pytest.mark.parametrize("major,minor,build,ok,name", [
    (6, 1, 7601, False, None),  # Windows 7 SP1
    (6, 3, 9600, False, None),  # Windows 8.1
    (10, 0, 10000, False, None),  # préversion de Windows 10
    (10, 0, 10240, True, "Windows 10"),
    (10, 0, 19045, True, "Windows 10"),
    (10, 0, 22000, True, "Windows 11"),
    (10, 0, 26100, True, "Windows 11"),
])
def test_windows_versions(major, minor, build, ok, name):
    status = evaluate("win32", major, minor, build)
    assert status.supported is ok
    if ok:
        assert status.name.startswith(name)
    else:
        assert status.reason_key == "error.platform_windows_too_old"


def test_non_windows_refused():
    status = evaluate("linux")
    assert not status.supported and status.reason_key == "error.platform_not_windows"


# ------------------------------------------------------------ traductions


def _catalog(lang):
    return json.loads(resources.files("feuillet.locales").joinpath(f"{lang}.json").read_text("utf-8"))


def _used_keys() -> set[str]:
    keys = set()
    for py in SRC.rglob("*.py"):
        text = py.read_text("utf-8")
        keys |= set(re.findall(r"""tr\(\s*["']([a-z_]+\.[a-z_0-9.]+)["']""", text))
        keys |= {f"error.{k}" for k in re.findall(r"""(?:Error|AppError)\(\s*["']([a-z_0-9]+)["']""", text)}
        keys |= {f"error.{k}" for k in re.findall(r""":\s*["'](scanner_[a-z_0-9]+)["']""", text)}
    return keys


def test_both_languages_have_same_keys():
    assert set(_catalog("fr")) == set(_catalog("en"))


def test_every_used_key_is_translated():
    missing = _used_keys() - set(_catalog("fr"))
    assert not missing, f"Clés absentes : {sorted(missing)}"


def test_placeholders_match_between_languages():
    fr, en = _catalog("fr"), _catalog("en")
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
    for key in fr:
        assert fields(fr[key]) == fields(en[key]), key


def test_tr_switches_language_and_formats():
    i18n.set_language("en")
    try:
        assert i18n.tr("watermark.pdf_info", n=3) == "3-page PDF"
    finally:
        i18n.set_language("fr")
    assert i18n.tr("watermark.pdf_info", n=3) == "PDF de 3 page(s)"
    assert i18n.tr("cle.inconnue") == "cle.inconnue"


def test_error_message_is_translated():
    assert "mot de passe" not in WatermarkError("empty_text").user_message()
    assert WatermarkError("empty_text").user_message() == "Saisissez le texte du filigrane."


# ------------------------------------------------------------ fichiers


def test_output_cannot_be_original(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    with pytest.raises(OutputFileError) as exc:
        ensure_new_output(src, src, overwrite=True)
    assert exc.value.code == "output_is_original"


def test_output_exists_and_missing_dir(tmp_path):
    existing = tmp_path / "b.pdf"
    existing.write_bytes(b"x")
    with pytest.raises(OutputFileError):
        ensure_new_output(existing)
    with pytest.raises(OutputFileError):
        ensure_new_output(tmp_path / "absent" / "c.pdf")


def test_suggest_output_name_never_collides(tmp_path):
    src = tmp_path / "contrat.pdf"
    src.write_bytes(b"x")
    first = suggest_output_name(src, "filigrane")
    assert first.name == "contrat_filigrane.pdf"
    first.write_bytes(b"x")
    assert suggest_output_name(src, "filigrane").name == "contrat_filigrane_2.pdf"


def test_downloads_dir_and_output_folder(tmp_path, monkeypatch):
    from feuillet.core.files import downloads_dir, suggest_output_name

    monkeypatch.setenv("FEUILLET_OUTPUT_DIR", str(tmp_path))
    assert downloads_dir() == tmp_path
    out = suggest_output_name("/ailleurs/contrat.pdf", "filigrane", folder=tmp_path)
    assert out == tmp_path / "contrat_filigrane.pdf"
    out.write_bytes(b"x")
    assert suggest_output_name("/ailleurs/contrat.pdf", "filigrane", folder=tmp_path).name == "contrat_filigrane_2.pdf"
