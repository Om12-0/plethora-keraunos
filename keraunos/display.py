"""
keraunos/display.py - Native Windows Display & Monitor Management via Win32.
"""

import ctypes
from ctypes import wintypes
import sys

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

CCHDEVICENAME = 32
DM_POSITION = 0x00000020
CDS_UPDATEREGISTRY = 0x00000001
CDS_SET_PRIMARY = 0x00000010


class POINTL(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * CCHDEVICENAME),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPosition", POINTL),
        ("dmScale", wintypes.SHORT),
        ("dmCopies", wintypes.SHORT),
        ("dmDefaultSource", wintypes.SHORT),
        ("dmPrintQuality", wintypes.SHORT),
        ("dmColor", wintypes.SHORT),
        ("dmDuplex", wintypes.SHORT),
        ("dmYResolution", wintypes.SHORT),
        ("dmTTOption", wintypes.SHORT),
        ("dmCollate", wintypes.SHORT),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


def set_primary_monitor(monitor_index: int = 1) -> bool:
    """Set primary display to monitor index (1-based index) using Win32 API without spawning any terminal."""
    if sys.platform != "win32" or user32 is None:
        return False

    target_name = f"\\\\.\\DISPLAY{monitor_index}"
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)

    if not user32.EnumDisplaySettingsW(target_name, -1, ctypes.byref(dm)):
        return False

    dm.dmPosition.x = 0
    dm.dmPosition.y = 0
    dm.dmFields |= DM_POSITION

    res = user32.ChangeDisplaySettingsExW(
        target_name, ctypes.byref(dm), None, CDS_SET_PRIMARY | CDS_UPDATEREGISTRY, None
    )
    user32.ChangeDisplaySettingsExW(None, None, None, 0, None)
    return res == 0
