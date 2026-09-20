"""
Plethora Keraunos — Auto-updater engine.
Queries GitHub Releases for new versions, downloads setup artifacts,
and triggers seamless in-place installation.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from keraunos.config import APP_VERSION

GITHUB_REPO = "Om12-0/plethora-keraunos"
API_LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _parse_version(v_str: str) -> Tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", v_str or "")]
    return tuple(nums) if nums else (0, 0, 0)


def is_newer_version(latest_ver: str, current_ver: str = APP_VERSION) -> bool:
    """Compare semver strings (e.g. '1.0.3' > '1.0.2')."""
    return _parse_version(latest_ver) > _parse_version(current_ver)


def check_for_updates(current_version: str = APP_VERSION, timeout: int = 6) -> Optional[Dict[str, Any]]:
    """Check GitHub releases for a newer version of Plethora Keraunos.

    Returns a dict with update info if a newer version is available, or None.
    """
    req = urllib.request.Request(
        API_LATEST_RELEASE_URL,
        headers={
            "User-Agent": f"PlethoraKeraunos/{current_version}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    tag_name = data.get("tag_name", "").strip()
    latest_version = tag_name.lstrip("vV")
    if not latest_version:
        return None

    if not is_newer_version(latest_version, current_version):
        return {
            "has_update": False,
            "latest_version": latest_version,
            "current_version": current_version,
            "release_notes": data.get("body", ""),
            "download_url": None,
            "asset_name": None,
        }

    # Find installer asset (.exe)
    download_url = None
    asset_name = None
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".exe") and "setup" in name.lower():
            download_url = asset.get("browser_download_url")
            asset_name = name
            break

    # Fallback to first .exe asset if no setup named
    if not download_url:
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".exe"):
                download_url = asset.get("browser_download_url")
                asset_name = name
                break

    return {
        "has_update": True,
        "latest_version": latest_version,
        "current_version": current_version,
        "release_notes": data.get("body", ""),
        "download_url": download_url,
        "asset_name": asset_name or f"Plethora-Keraunos-Setup-{latest_version}.exe",
    }


def download_update(
    download_url: str,
    asset_name: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    timeout: int = 60,
) -> Path:
    """Download installer executable to temporary folder with live progress reporting."""
    temp_dir = Path(tempfile.gettempdir())
    dest_path = temp_dir / asset_name

    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": f"PlethoraKeraunos/{APP_VERSION}"},
    )

    with urllib.request.urlopen(req, timeout=timeout) as response, open(dest_path, "wb") as out_file:
        total_length = response.getheader("content-length")
        total_bytes = int(total_length) if total_length else 0
        downloaded = 0
        chunk_size = 64 * 1024

        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total_bytes)

    return dest_path


def launch_installer_and_exit(installer_path: Path | str, silent: bool = False) -> None:
    """Spawn the downloaded installer and cleanly terminate the current process."""
    inst = str(Path(installer_path).resolve())
    args = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" if silent else ""
    ps_cmd = f'Start-Process -FilePath "{inst}" -ArgumentList "{args}"'

    if sys.platform == "win32":
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            creationflags=CREATE_NO_WINDOW,
        )
    else:
        subprocess.Popen([inst])

    sys.exit(0)
