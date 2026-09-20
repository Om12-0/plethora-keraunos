"""Export KeraunosState to Microsoft WinGet Configuration (DSC v0.2) format.

Produces a `configuration.dsc.yaml` consumable by:
    winget configure --file configuration.dsc.yaml
See: https://learn.microsoft.com/en-us/windows/package-manager/configuration/
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

from keraunos.schema import KeraunosState

DSC_SCHEMA = "https://aka.ms/configuration-dsc-schema/0.2"
DSC_VERSION = "0.2.0"
WINGET_RESOURCE = "Microsoft.WinGet.DSC/WinGetPackage"


def _safe_id(package_id: str) -> str:
    """DSC resource ids must be unique, alphanumeric + underscore/dash."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", package_id)
    return f"Package_{safe}"


class DscExporter:
    """Translate Keraunos desired-state into WinGet Configuration DSC YAML."""

    @staticmethod
    def to_dict(state: KeraunosState) -> Dict[str, Any]:
        resources: List[Dict[str, Any]] = []
        for pkg in state.winget:
            settings: Dict[str, Any] = {"id": pkg.id, "source": "winget"}
            if pkg.version:
                settings["version"] = pkg.version
            resources.append({
                "resource": WINGET_RESOURCE,
                "id": _safe_id(pkg.id),
                "directives": {
                    "description": f"Install {pkg.id} (managed by Keraunos)",
                    "allowPrerelease": True,
                },
                "settings": settings,
            })
        return {
            "$schema": DSC_SCHEMA,
            "properties": {
                "configurationVersion": DSC_VERSION,
                "resources": resources,
            },
        }

    @staticmethod
    def to_yaml(state: KeraunosState) -> str:
        return yaml.safe_dump(DscExporter.to_dict(state), sort_keys=False, indent=2,
                              allow_unicode=True)

    @staticmethod
    def export(state: KeraunosState, output_path: Path | str) -> Path:
        """Write the DSC manifest to ``output_path`` and return the path."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(DscExporter.to_yaml(state), encoding="utf-8")
        return out

    @staticmethod
    def export_current(state_file: Path | str, output_path: Path | str) -> Path:
        """Convenience: load a Keraunos state.yaml then export it."""
        state = KeraunosState.from_yaml_file(state_file)
        return DscExporter.export(state, output_path)
