"""WinGet, Scoop, and Registry execution tools with safe subprocess handling."""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List, NoReturn, Optional

IS_WINDOWS = platform.system() == "Windows"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ------------------------------------------------------ UAC / elevation --
def is_admin() -> bool:
    """Check if the current process has administrative privileges."""
    if not IS_WINDOWS:
        # POSIX: uid 0 == root.
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except AttributeError:
            return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except Exception:
        return False


def run_elevated_powershell(command: str, *, timeout: int = 600) -> subprocess.CompletedProcess:
    """Execute a PowerShell command elevated via Start-Process -Verb RunAs.

    Shows a UAC prompt. ``command`` runs hidden and synchronously (-Wait).
    Raises RuntimeError if PowerShell itself cannot be launched.
    """
    if not IS_WINDOWS:
        raise RuntimeError("Elevation via RunAs is only supported on Windows.")
    if not command or not command.strip():
        raise ValueError("Elevated command must be non-empty")
    # Escape for embedding inside a double-quoted PowerShell string.
    escaped = command.replace("`", "``").replace('"', '`"').replace("$", "`$")
    full_ps = (
        "Start-Process powershell -Verb RunAs -Wait "
        "-ArgumentList '-NoProfile','-NonInteractive','-Command',"
        f' "{escaped}"'
    )
    try:
        return subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", full_ps],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("PowerShell not found on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Elevated command timed out after {timeout}s.") from exc


def relaunch_self_elevated(reason: str = "Administrator privileges are required.") -> NoReturn:
    """Re-launch the current process elevated (UAC prompt) and exit.

    Used when HKLM-scoped registry work is requested without admin rights.
    """
    if not IS_WINDOWS:
        raise RuntimeError(reason + " (elevation is Windows-only)")
    params = " ".join(f'"{a}"' for a in sys.argv)
    ps = (
        f"Start-Process -FilePath '{sys.executable}' -Verb RunAs "
        f"-ArgumentList '{params.replace(chr(39), chr(39) * 2)}'"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=CREATE_NO_WINDOW)
    print(reason + " Relaunching elevated — please approve the UAC prompt.")
    raise SystemExit(10)


# ------------------------------------------------------ Shell refresh ---
_PS_BROADCAST = r"""
$code = @'
[System.Runtime.InteropServices.DllImport("user32.dll", SetLastError = true)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@
try {
  $win32 = Add-Type -MemberDefinition $code -Name Win32Keraunos -Namespace Shell -PassThru -ErrorAction Stop
  [UIntPtr]$r = [UIntPtr]::Zero
  [void]$win32::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$r)
  [void]$win32::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, "Policy", 2, 5000, [ref]$r)
  "broadcast-ok"
} catch { "broadcast-failed: $($_.Exception.Message)" }
"""


def refresh_windows_shell(restart_explorer: bool = False, *, timeout: int = 120) -> bool:
    """Broadcast WM_SETTINGCHANGE so Explorer / theme / taskbar apply instantly.

    - Always sends the lightweight broadcast (no reboot/sign-out needed).
    - Only restarts Explorer when ``restart_explorer=True`` (taskbar tweaks).
    Returns True when the broadcast reported success (or platform is non-Windows).
    """
    if not IS_WINDOWS:
        return True
    try:
        res = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_BROADCAST],
                   timeout=timeout)
        ok = "broadcast-ok" in (res.stdout or "")
    except RuntimeError:
        ok = False
    if restart_explorer:
        try:
            _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                  "Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue"],
                 timeout=60)
        except RuntimeError:
            pass
    return ok


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _run(cmd: List[str], *, timeout: int = 600, check: bool = False) -> CommandResult:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executable not found: {cmd[0]}. Is it installed and on PATH?") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from exc
    res = CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")
    if check and not res.ok:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}\n{res.stderr.strip() or res.stdout.strip()}")
    return res


def _ps_run(ps_command: str, *, timeout: int = 120, check: bool = False) -> CommandResult:
    pwsh = shutil.which("powershell") or shutil.which("pwsh")
    if pwsh is None:
        raise RuntimeError("PowerShell not found on PATH; registry operations require Windows PowerShell.")
    return _run([pwsh, "-NoProfile", "-NonInteractive", "-Command", ps_command], timeout=timeout, check=check)


# ---------------------------------------------------------------- WinGet ---
class WingetTool:
    """Thin wrapper around the WinGet CLI."""

    @staticmethod
    def available() -> bool:
        return shutil.which("winget") is not None

    @staticmethod
    def require_available() -> None:
        if not WingetTool.available():
            raise RuntimeError(
                "winget CLI not found. Install 'App Installer' from the Microsoft Store, "
                "then ensure `winget` is on PATH."
            )

    @staticmethod
    def install(package_id: str, version: Optional[str] = None) -> CommandResult:
        WingetTool.require_available()
        cmd = ["winget", "install", "--id", package_id, "-e",
               "--accept-package-agreements", "--accept-source-agreements", "--silent"]
        if version:
            cmd += ["--version", version]
        res = _run(cmd, timeout=1200)
        if not res.ok:
            blob = (res.stderr + res.stdout)
            if "No package found" in blob or "No available upgrade" in blob and "install" in blob:
                raise RuntimeError(f"WinGet could not resolve package '{package_id}': {blob.strip()[-2000:]}")
            raise RuntimeError(f"winget install {package_id} failed ({res.returncode}): {blob.strip()[-2000:]}")
        return res

    @staticmethod
    def uninstall(package_id: str) -> CommandResult:
        WingetTool.require_available()
        cmd = ["winget", "uninstall", "--id", package_id, "-e", "--silent",
               "--accept-source-agreements"]
        res = _run(cmd, timeout=1200)
        if not res.ok:
            blob = (res.stderr + res.stdout).strip()[-2000:]
            raise RuntimeError(f"winget uninstall {package_id} failed ({res.returncode}): {blob}")
        return res

    @staticmethod
    def list_ids(source: str = "winget") -> List[str]:
        """Best-effort parse of `winget list` output into package IDs (2nd column)."""
        if not WingetTool.available():
            return []
        res = _run(["winget", "list", "--source", source], timeout=300)
        if not res.ok:
            return []
        ids: List[str] = []
        lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
        # Skip header + separator (first two non-empty lines) when they look like a table.
        start = 0
        if len(lines) >= 2 and set(lines[1].strip()) <= set("- "):
            start = 2
        for line in lines[start:]:
            parts = line.split()
            if len(parts) >= 2 and "." in parts[1]:
                ids.append(parts[1])
        return ids


# ---------------------------------------------------------------- Scoop ----
class ScoopTool:
    @staticmethod
    def available() -> bool:
        return shutil.which("scoop") is not None

    @staticmethod
    def install(package: str) -> CommandResult:
        if not ScoopTool.available():
            raise RuntimeError("scoop CLI not found. Install from https://scoop.sh first.")
        res = _run(["scoop", "install", package], timeout=1200)
        if not res.ok:
            raise RuntimeError(f"scoop install {package} failed: {(res.stderr or res.stdout).strip()[-2000:]}")
        return res

    @staticmethod
    def uninstall(package: str) -> CommandResult:
        if not ScoopTool.available():
            raise RuntimeError("scoop CLI not found.")
        res = _run(["scoop", "uninstall", package], timeout=1200)
        if not res.ok:
            raise RuntimeError(f"scoop uninstall {package} failed: {(res.stderr or res.stdout).strip()[-2000:]}")
        return res


# -------------------------------------------------------------- Registry --
_REG_TYPE_MAP = {
    "DWord": "DWord",
    "QWord": "QWord",
    "String": "String",
    "ExpandString": "ExpandString",
    "Binary": "Binary",
    "MultiString": "MultiString",
}


class RegistryTool:
    """Registry writes via PowerShell. Always ensures the key path exists first."""

    @staticmethod
    def _ps_escape(value: object) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return "'" + value.replace("'", "''") + "'"
        if isinstance(value, bytes):
            return "([byte[]]@(" + ",".join(str(b) for b in value) + "))"
        if isinstance(value, (list, tuple)):
            inner = ",".join(RegistryTool._ps_escape(v) for v in value)
            return f"@({inner})"
        return "'" + str(value).replace("'", "''") + "'"

    @staticmethod
    def read(path: str, name: str) -> str:
        ps = (
            f"$v = (Get-ItemProperty -Path '{path}' -Name '{name}' "
            f"-ErrorAction SilentlyContinue).'{name}'; "
            f"if ($null -eq $v) {{ '' }} else {{ \"$v\" }}"
        )
        return _ps_run(ps).stdout.strip()

    @staticmethod
    def write(path: str, name: str, value: object, reg_type: str = "DWord") -> CommandResult:
        if reg_type not in _REG_TYPE_MAP:
            raise ValueError(f"Unsupported registry type '{reg_type}'")
        ps_value = RegistryTool._ps_escape(value)
        ps = (
            f"if (-not (Test-Path -LiteralPath '{path}')) "
            f"{{ New-Item -Path '{path}' -Force | Out-Null }}; "
            f"Set-ItemProperty -Path '{path}' -Name '{name}' "
            f"-Value {ps_value} -Type {reg_type} -Force"
        )
        return _ps_run(ps, check=True)

    @staticmethod
    def ensure_present(path: str) -> None:
        _ps_run(f"if (-not (Test-Path -LiteralPath '{path}')) {{ New-Item -Path '{path}' -Force | Out-Null }}", check=True)
