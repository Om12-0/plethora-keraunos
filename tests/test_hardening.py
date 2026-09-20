"""Tests for UAC helpers, shell refresh, elevation gating, and git remotes."""
from keraunos.executor import ExecutionEngine
from keraunos.git_store import StateRepository
from keraunos.schema import KeraunosState
from keraunos import tools


def test_is_admin_returns_bool():
    assert isinstance(tools.is_admin(), bool)


def test_refresh_non_windows_short_circuits(monkeypatch):
    monkeypatch.setattr(tools, "IS_WINDOWS", False)
    assert tools.refresh_windows_shell() is True
    assert tools.refresh_windows_shell(restart_explorer=True) is True


def test_run_elevated_rejects_empty():
    try:
        tools.run_elevated_powershell("")
    except (ValueError, RuntimeError) as exc:
        assert "non-empty" in str(exc) or "Windows" in str(exc)
    else:
        raise AssertionError("expected ValueError/RuntimeError")


def test_needs_elevation_hklm_vs_hkcu(tmp_path):
    eng = ExecutionEngine(tmp_path)
    hkcu = KeraunosState.model_validate({
        "registry": [{"path": r"HKCU:\Software\Test", "name": "V", "value": 1, "type": "DWord"}]
    })
    hklm = KeraunosState.model_validate({
        "registry": [{"path": r"HKLM:\SYSTEM\CurrentControlSet\Control\Test", "name": "V",
                      "value": 1, "type": "DWord"}]
    })
    hklm_preset = KeraunosState.model_validate({"system": {"enable_long_paths": True}})
    assert eng.needs_elevation(hkcu) is False
    assert eng.needs_elevation(hklm) is True
    assert eng.needs_elevation(hklm_preset) is True


def test_apply_raises_without_admin_on_hklm(tmp_path, monkeypatch):
    import pytest
    eng = ExecutionEngine(tmp_path)
    monkeypatch.setattr("keraunos.executor.is_admin", lambda: False)
    hklm = KeraunosState.model_validate({
        "registry": [{"path": r"HKLM:\SYSTEM\X", "name": "V", "value": 1, "type": "DWord"}]
    })
    with pytest.raises(PermissionError):
        eng.apply_state(hklm, status_callback=lambda *_: None, elevation="raise")


def test_git_remote_set_and_list(tmp_path):
    repo = StateRepository(tmp_path / "state")
    repo.set_remote("https://example.com/user/keraunos-state.git")
    assert repo.get_remote_url() == "https://example.com/user/keraunos-state.git"
    assert repo.list_remotes()["origin"] == "https://example.com/user/keraunos-state.git"
    # Re-setting replaces without error.
    repo.set_remote("https://example.com/user/other.git")
    assert repo.get_remote_url() == "https://example.com/user/other.git"


def test_git_push_without_remote_raises(tmp_path):
    import pytest
    repo = StateRepository(tmp_path / "empty")
    with pytest.raises((ValueError, RuntimeError)):
        repo.push("origin", "main")
