"""Acquisition par WIA 2.0 (Windows Image Acquisition), via l'objet COM « WIA.DeviceManager ».

WIA est fourni par Windows 10/11 et fonctionne en 64 bits : c'est la source
par défaut. Les pilotes « classe Windows » de la plupart des multifonctions
l'exposent.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

from feuillet.core.errors import ScannerError
from feuillet.scanner.sources.base import ColorMode, DeviceInfo, ScanParams, ScanSource

# Constantes WIA (wia.h / WIA Automation Layer)
WIA_DEVICE_TYPE_SCANNER = 1
WIA_FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
PROP_HORIZONTAL_RES = 6147
PROP_VERTICAL_RES = 6148
PROP_CURRENT_INTENT = 6146
PROP_DOCUMENT_HANDLING_SELECT = 3088
PROP_PAGES = 3096
INTENT = {ColorMode.COLOR: 1, ColorMode.GRAYSCALE: 2, ColorMode.BLACK_WHITE: 4}
FEEDER, FLATBED = 1, 2

# Codes d'erreur COM WIA les plus courants
WIA_ERROR_PAPER_EMPTY = 0x80210003
WIA_ERROR_PAPER_JAM = 0x80210002
WIA_ERROR_BUSY = 0x80210006
WIA_ERROR_OFFLINE = 0x80210005
WIA_ERROR_COVER_OPEN = 0x80210016
WIA_ERROR_DEVICE_COMMUNICATION = 0x8021000A
WIA_ERROR_USER_CANCELLED = 0x80210064  # S_FALSE converti selon les pilotes

_ERROR_CODES = {
    WIA_ERROR_PAPER_JAM: "scanner_paper_jam",
    WIA_ERROR_PAPER_EMPTY: "scanner_paper_empty",
    WIA_ERROR_BUSY: "scanner_busy",
    WIA_ERROR_OFFLINE: "scanner_offline",
    WIA_ERROR_COVER_OPEN: "scanner_cover_open",
    WIA_ERROR_DEVICE_COMMUNICATION: "scanner_offline",
}


def _hresult(exc: Exception) -> int | None:
    """Extrait le code d'erreur d'une com_error pywin32.

    ``args = (hresult, texte, excepinfo, argerror)`` : quand ``hresult`` vaut
    DISP_E_EXCEPTION, le vrai code WIA est dans ``excepinfo[5]`` (scode).
    """
    args = getattr(exc, "args", ())
    if len(args) >= 3 and isinstance(args[2], tuple) and len(args[2]) >= 6:
        scode = args[2][5]
        if isinstance(scode, int) and scode:
            return scode & 0xFFFFFFFF
    if args and isinstance(args[0], int) and args[0] < 0:
        return args[0] & 0xFFFFFFFF
    return None


def map_com_error(exc: Exception) -> ScannerError:
    code = _hresult(exc)
    key = _ERROR_CODES.get(code or 0, "scanner_failed")
    return ScannerError(key, backend="WIA", detail=f"0x{code:08X}" if code else str(exc))


def _set_property(props, prop_id: int, value) -> bool:
    for i in range(1, props.Count + 1):
        prop = props.Item(i)
        if prop.PropertyID == prop_id:
            try:
                prop.Value = value
                return True
            except Exception:
                return False
    return False


class WiaSource(ScanSource):
    backend = "WIA"

    def _client(self):
        if sys.platform != "win32":
            raise ScannerError("scanner_backend_missing", backend="WIA")
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise ScannerError("scanner_backend_missing", backend="WIA") from exc
        pythoncom.CoInitialize()
        return win32com.client

    def is_available(self) -> bool:
        try:
            self._client().Dispatch("WIA.DeviceManager")
            return True
        except Exception:
            return False

    def list_devices(self) -> list[DeviceInfo]:
        client = self._client()
        try:
            manager = client.Dispatch("WIA.DeviceManager")
            devices = []
            for i in range(1, manager.DeviceInfos.Count + 1):
                info = manager.DeviceInfos.Item(i)
                if info.Type == WIA_DEVICE_TYPE_SCANNER:
                    name = info.Properties("Name").Value
                    devices.append(DeviceInfo("WIA", info.DeviceID, str(name)))
            return devices
        except ScannerError:
            raise
        except Exception as exc:
            raise map_com_error(exc) from exc

    def acquire(self, device: DeviceInfo, params: ScanParams) -> list[np.ndarray]:
        from feuillet.scanner.imaging import load_images

        client = self._client()
        try:
            manager = client.Dispatch("WIA.DeviceManager")
            info = next((manager.DeviceInfos.Item(i) for i in range(1, manager.DeviceInfos.Count + 1)
                         if manager.DeviceInfos.Item(i).DeviceID == device.id), None)
            if info is None:
                raise ScannerError("scanner_not_found", name=device.name)
            dev = info.Connect()
            if params.use_feeder:
                if not _set_property(dev.Properties, PROP_DOCUMENT_HANDLING_SELECT, FEEDER):
                    raise ScannerError("scanner_no_feeder", name=device.name)
                _set_property(dev.Properties, PROP_PAGES, 1)
            item = dev.Items.Item(1)
            _set_property(item.Properties, PROP_CURRENT_INTENT, INTENT[params.color_mode])
            _set_property(item.Properties, PROP_HORIZONTAL_RES, params.dpi)
            _set_property(item.Properties, PROP_VERTICAL_RES, params.dpi)
        except ScannerError:
            raise
        except Exception as exc:
            raise map_com_error(exc) from exc

        pages: list[np.ndarray] = []
        with tempfile.TemporaryDirectory(prefix="feuillet-wia-") as tmp:
            while True:
                try:
                    if params.show_driver_ui:
                        dialog = client.Dispatch("WIA.CommonDialog")
                        image = dialog.ShowTransfer(item, WIA_FORMAT_PNG, False)
                    else:
                        image = item.Transfer(WIA_FORMAT_PNG)
                except Exception as exc:
                    code = _hresult(exc)
                    if code == WIA_ERROR_PAPER_EMPTY and pages:
                        break  # fin normale du chargeur
                    raise map_com_error(exc) from exc
                if image is None:  # annulation dans la boîte de dialogue du pilote
                    break
                path = Path(tmp) / f"page{len(pages) + 1}.png"
                image.SaveFile(str(path))
                pages.extend(load_images(path))
                if not params.use_feeder:
                    break
        return pages
