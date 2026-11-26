"""Diagnostic des scanners (WIA / TWAIN) sous Windows.

Lancement, depuis le dossier du projet :
    .\\.venv\\Scripts\\python.exe tools\\diagnostic_scanner.py

Copiez tout le texte affiché et envoyez-le : il permet de savoir pourquoi
aucun scanner n'est détecté (appareil absent, pilote, service Windows…).
"""

from __future__ import annotations

import platform
import struct
import subprocess
import sys
import traceback

WIA_TYPES = {0: "inconnu", 1: "scanner", 2: "appareil photo", 3: "caméra vidéo"}


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=20, creationflags=0x08000000)
        raw = out.stdout or out.stderr
        for enc in ("cp850", "cp1252", "utf-8"):
            try:
                return raw.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace").strip()
    except Exception as exc:  # noqa: BLE001
        return f"(échec : {exc})"


def main() -> None:
    section("Système")
    print("Windows :", platform.platform(), "| version :", platform.version())
    print("Python  :", sys.version.split()[0], f"{struct.calcsize('P') * 8} bits", "|", sys.executable)

    section("Service Windows d'acquisition d'images (stisvc)")
    print(run(["sc", "query", "stisvc"]))

    section("Périphériques d'imagerie connus de Windows (PnP)")
    print(run(["powershell", "-NoProfile", "-Command",
               "Get-PnpDevice -Class Image -ErrorAction SilentlyContinue | "
               "Format-Table -AutoSize Status, FriendlyName, InstanceId | Out-String -Width 200"])
          or "(aucun périphérique de classe « Image »)")

    section("WIA via pywin32")
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        manager = win32com.client.Dispatch("WIA.DeviceManager")
        count = manager.DeviceInfos.Count
        print("Périphériques WIA :", count)
        for i in range(1, count + 1):
            info = manager.DeviceInfos.Item(i)
            print(f"\n  [{i}] type = {info.Type} ({WIA_TYPES.get(info.Type, '?')})")
            print("      DeviceID =", info.DeviceID)
            for j in range(1, info.Properties.Count + 1):
                prop = info.Properties.Item(j)
                try:
                    value = prop.Value
                except Exception as exc:  # noqa: BLE001
                    value = f"(illisible : {exc})"
                print(f"      {prop.Name} ({prop.PropertyID}) = {value}")
    except Exception:  # noqa: BLE001
        print("ERREUR :")
        traceback.print_exc(file=sys.stdout)

    section("Détection par Feuillet")
    try:
        from feuillet.scanner import sources

        devices, problems = sources.list_all_devices()
        print("Scanners trouvés :", [f"{d.name} ({d.backend})" for d in devices] or "aucun")
        for p in problems:
            print("Problème :", p.code, p.params, "->", p.user_message())
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stdout)


if __name__ == "__main__":
    main()
    if sys.stdin and sys.stdin.isatty():
        input("\nAppuyez sur Entrée pour fermer…")
