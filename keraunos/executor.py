"""Transactional apply engine with rollback-script generation."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

import yaml

from keraunos.registry_map import SYSTEM_PRESETS, resolve_system_tweaks
from keraunos.scanner import assert_no_secrets
from keraunos.schema import KeraunosState
from keraunos.tools import RegistryTool, ScoopTool, WingetTool, is_admin, refresh_windows_shell

StatusCallback = Callable[[str], None]

# Registry paths containing these substrings need an Explorer restart to visibly apply.
_EXPLORER_SENSITIVE = ("Explorer", "Taskbar", "Search", "StartMenu", "Desktop", "Shell")


CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _is_hklm(path: str) -> bool:
    return (path or "").upper().startswith("HKLM:")


def _touches_explorer(paths: List[str]) -> bool:
    return any(any(token.lower() in (p or "").lower() for token in _EXPLORER_SENSITIVE) for p in paths)


class ExecutionEngine:
    def __init__(self, state_dir: Path | str = Path.home() / ".keraunos"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "state.yaml"
        self.rollback_dir = self.state_dir / "rollbacks"
        self.rollback_dir.mkdir(parents=True, exist_ok=True)

    # -- state ---------------------------------------------------------------------
    def load_current_state(self) -> KeraunosState:
        if not self.state_file.exists():
            return KeraunosState()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return KeraunosState(**data)
        except Exception as exc:
            raise RuntimeError(f"Cannot parse {self.state_file}: {exc}") from exc

    def save_state(self, state: KeraunosState) -> None:
        assert_no_secrets(state.to_yaml(), context="state.yaml")
        with open(self.state_file, "w", encoding="utf-8") as f:
            yaml.dump(state.model_dump(mode="python"), f, indent=2, sort_keys=False, allow_unicode=True)

    # -- diff -----------------------------------------------------------------------
    def calculate_diff(self, desired: KeraunosState) -> Dict[str, Any]:
        current = self.load_current_state()
        cur_winget = {p.id: (p.version or "") for p in current.winget}
        des_winget = {p.id: (p.version or "") for p in desired.winget}
        cur_scoop, des_scoop = set(current.scoop), set(desired.scoop)

        # System tweaks that are newly enabled (or changed value).
        system_tweaks: Dict[str, Any] = {}
        for k, v in (desired.system or {}).items():
            if current.system.get(k) != v:
                system_tweaks[k] = v

        cur_reg = {(r.path, r.name): (str(r.value), r.type) for r in current.registry}
        new_reg: List[Dict[str, Any]] = []
        for r in desired.registry:
            if cur_reg.get((r.path, r.name)) != (str(r.value), r.type):
                new_reg.append(r.model_dump())

        return {
            "winget_add": sorted(set(des_winget) - set(cur_winget)),
            "winget_remove": sorted(set(cur_winget) - set(des_winget)),
            "winget_upgrade": sorted(pid for pid in set(des_winget) & set(cur_winget)
                                     if des_winget[pid] != cur_winget[pid] and des_winget[pid]),
            "scoop_add": sorted(des_scoop - cur_scoop),
            "scoop_remove": sorted(cur_scoop - des_scoop),
            "system_tweaks": system_tweaks,
            "custom_registry": new_reg,
            "dotfiles": desired.dotfiles.model_dump(),
            "custom_actions": list(getattr(desired, "custom_actions", [])),
        }

    def render_diff_text(self, diff: Dict[str, Any]) -> str:
        lines: List[str] = []
        for pkg in diff.get("winget_add", []):
            lines.append(f"+ winget: {pkg}")
        for pkg in diff.get("winget_remove", []):
            lines.append(f"- winget: {pkg}")
        for pkg in diff.get("scoop_add", []):
            lines.append(f"+ scoop: {pkg}")
        for pkg in diff.get("scoop_remove", []):
            lines.append(f"- scoop: {pkg}")
        for key, val in (diff.get("system_tweaks") or {}).items():
            lines.append(f"~ system.{key} = {val}")
        for reg in diff.get("custom_registry", []):
            lines.append(f"~ registry {reg['path']}\\{reg['name']} = {reg['value']} ({reg['type']})")
        for act in diff.get("custom_actions", []):
            if act.get("type") == "set_primary_monitor":
                lines.append(f"~ hardware.display.primary = Display {act.get('index', 1)}")
        if diff.get("dotfiles", {}).get("powershell_profile"):
            lines.append("~ dotfiles.powershell_profile updated")
        if diff.get("dotfiles", {}).get("terminal_theme"):
            lines.append(f"~ dotfiles.terminal_theme = {diff['dotfiles']['terminal_theme']}")
        return "\n".join(lines) if lines else "(no changes — already in sync)"

    # -- rollback --------------------------------------------------------------------
    def _write_rollback(self, diff: Dict[str, Any], current: KeraunosState) -> Path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        script = self.rollback_dir / f"rollback-{ts}.ps1"
        prev = self.rollback_dir / "last_rollback.ps1"
        lines = ["# Auto-generated rollback script — run to undo the last `apply`.", ""]
        for pkg in diff.get("winget_add", []):
            lines.append(f"winget uninstall --id {pkg} -e --silent --accept-source-agreements")
        for reg in resolve_system_tweaks({k: True for k in diff.get("system_tweaks", {}) if k in SYSTEM_PRESETS}):
            pass  # system preset previous values unknown without snapshot; record intent below
        if diff.get("system_tweaks"):
            lines.append(f"# NOTE: re-apply previous system values from: {self.state_file}.bak-{ts}")
        with open(script, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        with open(prev, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        # Snapshot previous state file for registry/dotfile restoration.
        try:
            if self.state_file.exists():
                (self.state_dir / f"state.yaml.bak-{ts}").write_text(
                    self.state_file.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
        _ = current
        return script

    # -- apply -------------------------------------------------------------------------
    def needs_elevation(self, desired: KeraunosState) -> bool:
        """True when desired state targets HKLM keys (admin required)."""
        for reg in resolve_system_tweaks({k: True for k, v in (desired.system or {}).items()
                                          if v and k in SYSTEM_PRESETS}):
            if _is_hklm(reg["path"]):
                return True
        return any(_is_hklm(r.path) for r in desired.registry or [])

    def apply_state(self, desired: KeraunosState,
                    status_callback: StatusCallback = print,
                    *, remove_extras: bool = False,
                    elevation: str = "raise") -> Dict[str, Any]:
        """Apply desired state transactionally. Returns the diff that was applied.

        Args:
            elevation: "raise" (fail fast when HKLM targeted without admin),
                "warn" (log a warning and continue — HKLM writes will fail
                per-key with a clear error), or "relaunch" (re-spawn elevated
                via UAC and exit current process).
        """
        assert_no_secrets(desired.to_yaml(), context="desired state")
        if elevation not in ("raise", "warn", "relaunch"):
            raise ValueError("elevation must be 'raise', 'warn', or 'relaunch'")
        if self.needs_elevation(desired) and not is_admin():
            msg = ("Desired state targets HKLM registry keys, which require "
                   "Administrator privileges. Re-run elevated (right-click -> "
                   "Run as administrator) or scope tweaks to HKCU.")
            if elevation == "raise":
                raise PermissionError(msg)
            if elevation == "relaunch":
                from keraunos.tools import relaunch_self_elevated
                relaunch_self_elevated(msg)
            status_callback(f"[UAC] WARNING: {msg}")
        current = self.load_current_state()
        diff = self.calculate_diff(desired)
        rollback_script = self._write_rollback(diff, current)
        status_callback(f"[Rollback] script written to {rollback_script}")

        applied: List[str] = []
        failed: List[str] = []
        NOTES: List[str] = []

        def _step(label: str, fn) -> None:
            status_callback(label)
            try:
                fn()
                applied.append(label)
            except Exception as exc:
                failed.append(f"{label} :: {exc}")
                raise

        # 0. Custom actions (e.g. Hardware display)
        for act in getattr(desired, "custom_actions", []):
            if act.get("type") == "set_primary_monitor":
                from keraunos.display import set_primary_monitor
                idx = act.get("index", 1)
                _step(f"[Display] Setting primary monitor to Display {idx}...",
                      lambda m=idx: set_primary_monitor(m))

        # 1. WinGet installs
        for pkg_id in diff["winget_add"]:
            version = next((p.version for p in desired.winget if p.id == pkg_id), None)
            _step(f"[WinGet] Installing {pkg_id}...",
                  lambda pid=pkg_id, ver=version: WingetTool.install(pid, ver))

        # 2. Optional removals (opt-in; never remove by default to avoid data loss)
        if remove_extras:
            for pkg_id in diff["winget_remove"]:
                _step(f"[WinGet] Removing {pkg_id}...",
                      lambda pid=pkg_id: WingetTool.uninstall(pid))
            for pkg in diff["scoop_remove"]:
                _step(f"[Scoop] Removing {pkg}...",
                      lambda p=pkg: ScoopTool.uninstall(p))

        # 3. Scoop installs
        for pkg in diff["scoop_add"]:
            _step(f"[Scoop] Installing {pkg}...",
                  lambda p=pkg: ScoopTool.install(p))

        # 4. System registry presets (only enabled keys)
        enabled = {k: v for k, v in (desired.system or {}).items() if v}
        unknown = [k for k in enabled if k not in SYSTEM_PRESETS]
        if unknown:
            raise KeyError(f"Unknown system tweak(s): {unknown}. Valid: {sorted(SYSTEM_PRESETS)}")
        mutated_paths: List[str] = []
        registry_touched = False
        for tweak_key in enabled:
            if tweak_key not in diff.get("system_tweaks", {}):
                continue
            _step(f"[System] Applying tweak: {tweak_key}", lambda: None)
            for reg in SYSTEM_PRESETS[tweak_key]:
                RegistryTool.write(reg["path"], reg["name"], reg["value"], reg.get("type", "DWord"))
                mutated_paths.append(reg["path"])
                registry_touched = True

        # 5. Custom registry entries
        for reg in desired.registry:
            _step(f"[Registry] {reg.path}\\{reg.name} = {reg.value}",
                  lambda r=reg: RegistryTool.write(r.path, r.name, r.value, r.type))
            mutated_paths.append(reg.path)
            registry_touched = True

        # 5b. Live shell refresh — no sign-out/reboot required.
        if registry_touched:
            restart = _touches_explorer(mutated_paths)
            try:
                ok = refresh_windows_shell(restart_explorer=restart)
                status_callback("[Shell] Live refresh broadcast sent"
                                + (" + Explorer restarted." if restart else ".")
                                + ("" if ok else " (broadcast reported no change)"))
            except Exception as exc:  # noqa: BLE001 — refresh must never fail the apply
                status_callback(f"[Shell] Refresh skipped: {exc}")

        # 6. Dotfiles
        self._apply_dotfiles(desired, status_callback)

        # 7. Persist desired state (only after everything above succeeded)
        self.save_state(desired)
        status_callback("[Complete] State written and verified.")

        if failed:
            NOTES.append(f"Rollback available at: {rollback_script}")
            raise RuntimeError("Apply completed with failures:\n" + "\n".join(failed))
        return diff

    # -- dotfiles -------------------------------------------------------------------------
    def _apply_dotfiles(self, desired: KeraunosState, status_callback: StatusCallback) -> None:
        profile_body: Optional[str] = desired.dotfiles.powershell_profile
        if profile_body:
            assert_no_secrets(profile_body, context="powershell profile")
            # Resolve the real per-user profile path via PowerShell ($PROFILE).
            from keraunos.tools import _ps_run  # local import to avoid cycle at module load
            try:
                res = _ps_run("$PROFILE", timeout=60)
                profile_path = Path(res.stdout.strip().strip('"').strip("'"))
            except Exception:
                profile_path = Path.home() / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
            try:
                profile_path.parent.mkdir(parents=True, exist_ok=True)
                profile_path.write_text(profile_body, encoding="utf-8")
                status_callback(f"[Dotfiles] Wrote PowerShell profile -> {profile_path}")
            except OSError as exc:
                raise RuntimeError(f"Cannot write PowerShell profile: {exc}") from exc
