"""Tests for the offline intent compiler, deterministic commit messages, and CLI."""
from __future__ import annotations

import socket
import urllib.request
from typing import Any, Dict

import importlib.util
from pathlib import Path

import pytest
import yaml

from keraunos.compiler import OfflineIntentCompiler
from keraunos.git_store import generate_deterministic_commit_msg
from keraunos.schema import KeraunosState, WinGetPackage

_cli_path = Path(__file__).resolve().parent.parent / "keraunos.py"
_spec = importlib.util.spec_from_file_location("keraunos_cli", _cli_path)
assert _spec and _spec.loader
_keraunos_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_keraunos_cli)
cli_main = _keraunos_cli.main


def test_exact_names():
    """(a) exact names: install 7zip and vscode -> both IDs, 100% confidence."""
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("install 7zip and vscode")

    pkg_ids = [p.id for p in state.winget]
    assert "7zip.7zip" in pkg_ids
    assert "Microsoft.VisualStudioCode" in pkg_ids

    diag_map = {d.resolved_target: d for d in diagnostics}
    assert "7zip.7zip" in diag_map
    assert diag_map["7zip.7zip"].confidence == 100.0
    assert "Microsoft.VisualStudioCode" in diag_map
    assert diag_map["Microsoft.VisualStudioCode"].confidence == 100.0


def test_typos_and_fuzzy_matching():
    """(b) typos: install vscod, add nvim, setup firfox -> correct IDs, 75-100%."""
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("install vscod, add nvim, setup firfox")

    pkg_ids = [p.id for p in state.winget]
    assert "Microsoft.VisualStudioCode" in pkg_ids
    assert "Neovim.Neovim" in pkg_ids
    assert "Mozilla.Firefox" in pkg_ids

    for d in diagnostics:
        assert 75.0 <= d.confidence <= 100.0
        assert d.action == "add"
        assert d.target_type == "package"


def test_multi_clause_removal_and_presets():
    """(c) multi-clause removal + presets:

    uninstall 7zip, enable dark mode, hide search bar on base state with 7zip ->
    7zip removed, dark_mode=True, hide_taskbar_search=True.
    """
    base_state = KeraunosState(winget=[WinGetPackage(id="7zip.7zip")])
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile(
        "uninstall 7zip, enable dark mode, hide search bar",
        base_state=base_state,
    )

    pkg_ids = [p.id for p in state.winget]
    assert "7zip.7zip" not in pkg_ids
    assert len(state.winget) == 0

    assert state.system.get("dark_mode") is True
    assert state.system.get("hide_taskbar_search") is True

    actions = {d.resolved_target: d.action for d in diagnostics}
    assert actions.get("7zip.7zip") == "remove"
    assert actions.get("dark_mode") == "enable"
    assert actions.get("hide_taskbar_search") == "enable"


def test_offline_proof(monkeypatch):
    """(d) offline proof: monkeypatch socket and urllib to raise, compile must succeed."""
    def _blocked_connect(*args, **kwargs):
        raise RuntimeError("Network disabled: socket connection attempted!")

    def _blocked_urlopen(*args, **kwargs):
        raise RuntimeError("Network disabled: urllib request attempted!")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_urlopen)

    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("install vscod, 7zip and enable dark mode")

    assert len(state.winget) == 2
    assert state.system.get("dark_mode") is True
    assert len(diagnostics) == 3


def test_commit_msg_builder():
    """(e) commit-msg builder cases (add/remove/system/empty)."""
    # 1. Additions (<= 3 items)
    diff_add_small = {"winget_add": ["7zip.7zip", "Microsoft.VisualStudioCode"]}
    assert (
        generate_deterministic_commit_msg(diff_add_small)
        == "feat(packages): add 7zip, VisualStudioCode"
    )

    # 2. Additions (> 3 items, + N more)
    diff_add_large = {
        "winget_add": ["7zip.7zip", "Microsoft.VisualStudioCode", "Git.Git", "Mozilla.Firefox"]
    }
    assert (
        generate_deterministic_commit_msg(diff_add_large)
        == "feat(packages): add 7zip, VisualStudioCode, Git + 1 more"
    )

    # 3. Scoop additions
    diff_scoop_add = {"scoop_add": ["fzf", "ripgrep"]}
    assert generate_deterministic_commit_msg(diff_scoop_add) == "feat(packages): add fzf, ripgrep"

    # 4. Removals
    diff_rem = {"winget_remove": ["7zip.7zip"]}
    assert generate_deterministic_commit_msg(diff_rem) == "feat(packages): remove 7zip"

    # 5. System tweaks (<= 2 keys)
    diff_sys = {"system_tweaks": {"dark_mode": True, "hide_taskbar_search": True}}
    assert (
        generate_deterministic_commit_msg(diff_sys)
        == "chore(system): configure dark_mode, hide_taskbar_search"
    )

    # 6. System tweaks (> 2 keys)
    diff_sys_multi = {
        "system_tweaks": {
            "dark_mode": True,
            "hide_taskbar_search": True,
            "enable_long_paths": True,
        }
    }
    assert (
        generate_deterministic_commit_msg(diff_sys_multi)
        == "chore(system): configure dark_mode, hide_taskbar_search"
    )

    # 7. Combined clauses (add + remove + system)
    diff_combined = {
        "winget_add": ["Microsoft.VisualStudioCode"],
        "winget_remove": ["7zip.7zip"],
        "system_tweaks": {"dark_mode": True},
    }
    assert (
        generate_deterministic_commit_msg(diff_combined)
        == "feat(packages): add VisualStudioCode; feat(packages): remove 7zip; chore(system): configure dark_mode"
    )

    # 8. Empty diff
    assert generate_deterministic_commit_msg({}) == "chore: update system state"

    # 9. Non-dict fallback
    assert generate_deterministic_commit_msg(None) == "chore: update system state"  # type: ignore


def test_cli_aliases_produce_identical_yaml(capsys):
    """(f) generate and compile CLI aliases produce identical YAML."""
    prompt = "install 7zip, enable dark mode"

    ret1 = cli_main(["compile", prompt, "--stdout"])
    out1, _ = capsys.readouterr()
    assert ret1 == 0

    ret2 = cli_main(["generate", prompt, "--stdout"])
    out2, _ = capsys.readouterr()
    assert ret2 == 0

    assert out1 == out2
    parsed = yaml.safe_load(out1)
    assert parsed["system"]["dark_mode"] is True
    assert any(p["id"] == "7zip.7zip" for p in parsed["winget"])


def test_find_unresolved_reporting():
    """Verify unresolved clauses report correctly for UI banner."""
    compiler = OfflineIntentCompiler()
    prompt = "install vscode, bake some cookies, dark mode"
    state, diagnostics = compiler.compile(prompt)
    unresolved = compiler.find_unresolved(prompt, diagnostics)
    assert "bake some cookies" in unresolved


def test_empty_prompt_rejected():
    compiler = OfflineIntentCompiler()
    with pytest.raises(ValueError, match="Prompt must be non-empty"):
        compiler.compile("   ")


def test_secrets_in_prompt_blocked():
    compiler = OfflineIntentCompiler()
    with pytest.raises(ValueError, match="potential secret"):
        compiler.compile("install 7zip with token sk-" + "a" * 35)
