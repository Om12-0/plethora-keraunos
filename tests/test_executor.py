"""Tests for diff calculation and drift comparison (no real installs)."""
from keraunos.drift import DriftDetector
from keraunos.executor import ExecutionEngine
from keraunos.schema import KeraunosState


def _state(**kw):
    base = {"version": 1, "winget": [], "scoop": [], "system": {},
            "registry": [], "dotfiles": {}}
    base.update(kw)
    return KeraunosState(**base)


def test_diff_detects_winget_add(tmp_path):
    eng = ExecutionEngine(tmp_path)
    eng.save_state(_state())
    desired = _state(winget=[{"id": "7zip.7zip"}, {"id": "Neovim.Neovim"}])
    diff = eng.calculate_diff(desired)
    assert sorted(diff["winget_add"]) == ["7zip.7zip", "Neovim.Neovim"]
    assert diff["winget_remove"] == []


def test_diff_detects_removals_and_system(tmp_path):
    eng = ExecutionEngine(tmp_path)
    eng.save_state(_state(winget=[{"id": "7zip.7zip"}], system={"dark_mode": True}))
    desired = _state(system={"dark_mode": True})
    diff = eng.calculate_diff(desired)
    assert diff["winget_remove"] == ["7zip.7zip"]
    assert diff["system_tweaks"] == {}  # unchanged -> no tweak


def test_diff_system_change_flagged(tmp_path):
    eng = ExecutionEngine(tmp_path)
    eng.save_state(_state())
    diff = eng.calculate_diff(_state(system={"dark_mode": True}))
    assert diff["system_tweaks"] == {"dark_mode": True}


def test_drift_compare_uses_injected_inventory():
    desired = _state(winget=[{"id": "7zip.7zip"}], scoop=["fzf"])
    report = DriftDetector.compare(desired, installed_winget=[], installed_scoop=[])
    assert not report.in_sync
    keys = {(i.category, i.key) for i in report.items}
    assert ("winget", "7zip.7zip") in keys
    assert ("scoop", "fzf") in keys
    report2 = DriftDetector.compare(desired, installed_winget=["7zip.7zip"], installed_scoop=["fzf"])
    assert report2.in_sync


def test_render_diff_text_empty(tmp_path):
    eng = ExecutionEngine(tmp_path)
    eng.save_state(_state())
    diff = eng.calculate_diff(_state())
    assert "already in sync" in eng.render_diff_text(diff)
