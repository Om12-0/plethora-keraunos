"""Tests for the declarative schema (YAML round-trip + validation)."""
from keraunos.schema import KeraunosState


def test_empty_state_defaults():
    s = KeraunosState()
    assert s.version == 1
    assert s.winget == []
    assert s.system == {}


def test_yaml_round_trip(tmp_path):
    s = KeraunosState.model_validate({
        "version": 1,
        "winget": [{"id": "7zip.7zip"}, {"id": "Neovim.Neovim", "version": "0.10.0"}],
        "scoop": ["fzf"],
        "system": {"dark_mode": True, "show_file_extensions": True},
        "registry": [{"path": r"HKCU:\Software\Test", "name": "Foo", "value": 1, "type": "DWord"}],
        "dotfiles": {"terminal_theme": "OneHalfDark"},
    })
    p = tmp_path / "state.yaml"
    s.to_yaml_file(p)
    loaded = KeraunosState.from_yaml_file(p)
    assert loaded == s


def test_invalid_registry_type_rejected():
    import pytest
    with pytest.raises(Exception):
        KeraunosState.model_validate({
            "registry": [{"path": "HKCU:\\x", "name": "y", "value": 1, "type": "Nope"}]
        })


def test_from_yaml_empty_string_gives_defaults():
    assert KeraunosState.from_yaml("") == KeraunosState()
