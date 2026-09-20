"""Curated system tweaks mapping human-friendly keys to exact registry locations."""
from __future__ import annotations

from typing import Any, Dict, List

# Each preset is a list of {path, name, value, type} dicts compatible with RegistryTweak.
SYSTEM_PRESETS: Dict[str, List[Dict[str, Any]]] = {
    "dark_mode": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "name": "AppsUseLightTheme", "value": 0, "type": "DWord"},
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "name": "SystemUsesLightTheme", "value": 0, "type": "DWord"},
    ],
    "light_mode": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "name": "AppsUseLightTheme", "value": 1, "type": "DWord"},
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "name": "SystemUsesLightTheme", "value": 1, "type": "DWord"},
    ],
    "hide_taskbar_search": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Search", "name": "SearchboxTaskbarMode", "value": 0, "type": "DWord"},
    ],
    "show_taskbar_search": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Search", "name": "SearchboxTaskbarMode", "value": 1, "type": "DWord"},
    ],
    "show_file_extensions": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "HideFileExt", "value": 0, "type": "DWord"},
    ],
    "hide_file_extensions": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "HideFileExt", "value": 1, "type": "DWord"},
    ],
    "show_hidden_files": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "Hidden", "value": 1, "type": "DWord"},
    ],
    "hide_hidden_files": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "Hidden", "value": 2, "type": "DWord"},
    ],
    "compact_explorer_view": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "UseCompactMode", "value": 1, "type": "DWord"},
    ],
    "comfortable_explorer_view": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "name": "UseCompactMode", "value": 0, "type": "DWord"},
    ],
    "disable_bing_in_start_search": [
        {"path": r"HKCU:\Software\Policies\Microsoft\Windows\Explorer", "name": "DisableSearchBoxSuggestions", "value": 1, "type": "DWord"},
    ],
    "show_this_pc_on_desktop": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel", "name": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "value": 0, "type": "DWord"},
    ],
    "disable_game_bar": [
        {"path": r"HKCU:\Software\Microsoft\Windows\CurrentVersion\GameDVR", "name": "AppCaptureEnabled", "value": 0, "type": "DWord"},
    ],
    "enable_long_paths": [
        {"path": r"HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem", "name": "LongPathsEnabled", "value": 1, "type": "DWord"},
    ],
}


def resolve_system_tweaks(system: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expand ``system: {key: bool}`` into a flat list of registry operations."""
    ops: List[Dict[str, Any]] = []
    for key, enabled in system.items():
        if not enabled:
            continue
        preset = SYSTEM_PRESETS.get(key)
        if preset is None:
            raise KeyError(
                f"Unknown system tweak '{key}'. Available: {sorted(SYSTEM_PRESETS)}"
            )
        ops.extend(preset)
    return ops


def list_presets() -> List[str]:
    return sorted(SYSTEM_PRESETS)
