"""Pydantic v2 declarative schema definitions for Keraunos desired-state."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class WinGetPackage(BaseModel):
    id: str
    version: Optional[str] = None

    @field_validator("id")
    @classmethod
    def _non_empty_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("WinGet package id must be non-empty")
        return v


class RegistryTweak(BaseModel):
    path: str
    name: str
    value: Any
    type: str = "DWord"  # DWord, String, QWord, Binary, ExpandString, MultiString

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        allowed = {"DWord", "String", "QWord", "Binary", "ExpandString", "MultiString"}
        if v not in allowed:
            raise ValueError(f"registry type must be one of {sorted(allowed)}")
        return v

    @field_validator("path", "name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("registry path/name must be non-empty")
        return v.strip()


class DotfilesConfig(BaseModel):
    powershell_profile: Optional[str] = None
    terminal_theme: Optional[str] = None


class KeraunosState(BaseModel):
    version: int = 1
    winget: List[WinGetPackage] = Field(default_factory=list)
    scoop: List[str] = Field(default_factory=list)
    system: Dict[str, Any] = Field(default_factory=dict)
    registry: List[RegistryTweak] = Field(default_factory=list)
    dotfiles: DotfilesConfig = Field(default_factory=DotfilesConfig)

    @field_validator("version")
    @classmethod
    def _version_supported(cls, v: int) -> int:
        if v != 1:
            raise ValueError(f"unsupported state version: {v}")
        return v

    # -- (de)serialisation helpers -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="python")

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False, indent=2, allow_unicode=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KeraunosState":
        return cls(**(data or {}))

    @classmethod
    def from_yaml(cls, text: str) -> "KeraunosState":
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("state.yaml must decode to a mapping at top level")
        return cls(**data)

    @classmethod
    def from_yaml_file(cls, path: Path | str) -> "KeraunosState":
        p = Path(path)
        if not p.exists():
            return cls()
        return cls.from_yaml(p.read_text(encoding="utf-8"))

    def to_yaml_file(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_yaml(), encoding="utf-8")
