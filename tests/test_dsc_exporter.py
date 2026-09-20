"""Tests for the WinGet DSC manifest exporter."""
import yaml

from keraunos.dsc_exporter import DSC_SCHEMA, DSC_VERSION, WINGET_RESOURCE, DscExporter
from keraunos.schema import KeraunosState


def _state():
    return KeraunosState.model_validate({
        "version": 1,
        "winget": [
            {"id": "7zip.7zip"},
            {"id": "Neovim.Neovim", "version": "0.10.4"},
        ],
    })


def test_manifest_top_level_structure():
    manifest = DscExporter.to_dict(_state())
    assert manifest["$schema"] == DSC_SCHEMA
    assert manifest["properties"]["configurationVersion"] == DSC_VERSION
    assert isinstance(manifest["properties"]["resources"], list)


def test_each_package_becomes_winget_resource():
    resources = DscExporter.to_dict(_state())["properties"]["resources"]
    assert len(resources) == 2
    by_id = {r["settings"]["id"]: r for r in resources}
    assert set(by_id) == {"7zip.7zip", "Neovim.Neovim"}
    for r in resources:
        assert r["resource"] == WINGET_RESOURCE
        assert r["settings"]["source"] == "winget"
        assert r["directives"]["allowPrerelease"] is True
        assert r["id"].startswith("Package_")
    assert by_id["Neovim.Neovim"]["settings"]["version"] == "0.10.4"
    assert "version" not in by_id["7zip.7zip"]["settings"]


def test_export_writes_valid_yaml(tmp_path):
    out = tmp_path / "nested" / "configuration.dsc.yaml"
    returned = DscExporter.export(_state(), out)
    assert returned == out
    assert out.exists()
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert loaded["$schema"] == DSC_SCHEMA
    assert len(loaded["properties"]["resources"]) == 2


def test_empty_state_exports_empty_resources():
    manifest = DscExporter.to_dict(KeraunosState())
    assert manifest["properties"]["resources"] == []
