"""Drift detection — read-only scan of machine vs. state.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from keraunos.registry_map import SYSTEM_PRESETS
from keraunos.schema import KeraunosState
from keraunos.tools import RegistryTool, ScoopTool, WingetTool


@dataclass
class DriftItem:
    category: str  # "winget" | "scoop" | "system" | "registry" | "dotfiles"
    key: str
    expected: str
    actual: str
    action: str  # "add" | "remove" | "update"


@dataclass
class DriftReport:
    in_sync: bool
    items: List[DriftItem] = field(default_factory=list)

    def summary(self) -> str:
        if not self.items:
            return "In sync — no drift detected."
        lines = [f"Drift: {len(self.items)} difference(s) found:"]
        for it in self.items:
            lines.append(f"  [{it.category}/{it.action}] {it.key}: expected={it.expected!r} actual={it.actual!r}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {"in_sync": self.in_sync,
                "items": [vars(i) for i in self.items]}


class DriftDetector:
    """All scans are read-only; never mutates the machine."""

    # -- raw scanners ------------------------------------------------------------
    @staticmethod
    def scan_installed_winget() -> List[str]:
        """Read-only scan of user-installed software (WinGet IDs)."""
        return WingetTool.list_ids()

    @staticmethod
    def scan_installed_scoop() -> List[str]:
        if not ScoopTool.available():
            return []
        import subprocess
        try:
            proc = subprocess.run(["scoop", "list"], capture_output=True, text=True, timeout=120)
        except Exception:
            return []
        apps: List[str] = []
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] not in ("Installed", "----", "Name"):
                apps.append(parts[0])
        return apps

    @staticmethod
    def check_registry_key(path: str, name: str) -> Any:
        try:
            return RegistryTool.read(path, name)
        except Exception:
            return ""

    # -- comparison ---------------------------------------------------------------
    @staticmethod
    def compare(desired: KeraunosState,
                installed_winget: List[str] | None = None,
                installed_scoop: List[str] | None = None) -> DriftReport:
        if installed_winget is None:
            installed_winget = DriftDetector.scan_installed_winget()
        if installed_scoop is None:
            installed_scoop = DriftDetector.scan_installed_scoop()

        items: List[DriftItem] = []
        have_winget = set(installed_winget or [])
        want_winget = {p.id for p in desired.winget}
        for pkg in sorted(want_winget - have_winget):
            items.append(DriftItem("winget", pkg, "installed", "missing", "add"))
        for pkg in sorted(have_winget & want_winget):
            pass  # installed as desired — no drift
        # NOTE: extra packages installed outside keraunos are reported as informational removes.
        # We only flag them when strict mode is desired; by default list first 20.
        # (Kept quiet to avoid noise from pre-installed OEM software.)

        have_scoop = set(installed_scoop or [])
        want_scoop = set(desired.scoop or [])
        for pkg in sorted(want_scoop - have_scoop):
            items.append(DriftItem("scoop", pkg, "installed", "missing", "add"))

        # System presets: only check enabled tweaks.
        for key, enabled in (desired.system or {}).items():
            if not enabled or key not in SYSTEM_PRESETS:
                continue
            for reg in SYSTEM_PRESETS[key]:
                actual = str(DriftDetector.check_registry_key(reg["path"], reg["name"]))
                if actual != str(reg["value"]):
                    items.append(DriftItem("system", f"{key}:{reg['name']}",
                                           str(reg["value"]), actual or "(unset)", "update"))

        # Custom registry entries.
        for reg in desired.registry or []:
            actual = str(DriftDetector.check_registry_key(reg.path, reg.name))
            if actual != str(reg.value):
                items.append(DriftItem("registry", f"{reg.path}\\{reg.name}",
                                       str(reg.value), actual or "(unset)", "update"))

        return DriftReport(in_sync=not items, items=items)

    @staticmethod
    def compare_file(state_file: Path | str) -> DriftReport:
        desired = KeraunosState.from_yaml_file(state_file)
        return DriftDetector.compare(desired)
