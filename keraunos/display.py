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


# Win32 Display Topology Flags for SetDisplayConfig
SDC_APPLY = 0x00000080
SDC_TOPOLOGY_INTERNAL = 0x00000001  # PC screen only
SDC_TOPOLOGY_CLONE = 0x00000002     # Duplicate
SDC_TOPOLOGY_EXTEND = 0x00000004    # Extend
SDC_TOPOLOGY_EXTERNAL = 0x00000008  # Second screen only


def set_display_topology(topology: str = "clone") -> bool:
    """Set multi-monitor display topology ('clone'/'duplicate', 'extend', 'internal'/'pc_only', 'external'/'second_only')."""
    top_lower = (topology or "").strip().lower()
    flag_map = {
        "clone": SDC_TOPOLOGY_CLONE,
        "duplicate": SDC_TOPOLOGY_CLONE,
        "mirror": SDC_TOPOLOGY_CLONE,
        "extend": SDC_TOPOLOGY_EXTEND,
        "internal": SDC_TOPOLOGY_INTERNAL,
        "pc_only": SDC_TOPOLOGY_INTERNAL,
        "external": SDC_TOPOLOGY_EXTERNAL,
        "second_only": SDC_TOPOLOGY_EXTERNAL,
    }
    flag = flag_map.get(top_lower, SDC_TOPOLOGY_CLONE)

    # 1. Primary Win32 API call: SetDisplayConfig
    if sys.platform == "win32" and user32 is not None and hasattr(user32, "SetDisplayConfig"):
        try:
            res = user32.SetDisplayConfig(0, None, 0, None, SDC_APPLY | flag)
            if res == 0:
                return True
        except Exception:
            pass

    # 2. Native Windows fallback via DisplaySwitch.exe
    if sys.platform == "win32":
        import subprocess
        switch_arg = {
            SDC_TOPOLOGY_CLONE: "/clone",
            SDC_TOPOLOGY_EXTEND: "/extend",
            SDC_TOPOLOGY_INTERNAL: "/internal",
            SDC_TOPOLOGY_EXTERNAL: "/external",
        }.get(flag, "/clone")
        try:
            CREATE_NO_WINDOW = 0x08000000
            res = subprocess.run(["DisplaySwitch.exe", switch_arg], capture_output=True, creationflags=CREATE_NO_WINDOW)
            return res.returncode == 0
        except Exception:
            pass

    return False

