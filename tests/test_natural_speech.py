"""Regression tests for natural phrasing, conversational filler, updates, and vernacular comprehension."""
from __future__ import annotations

import pytest

from keraunos.compiler import OfflineIntentCompiler
from keraunos.schema import KeraunosState, WinGetPackage


def test_update_github():
    """compile('update github') resolves to GitHub.cli with action='update' and applied=True."""
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("update github")

    pkg_ids = [p.id for p in state.winget]
    assert "GitHub.cli" in pkg_ids

    update_diags = [d for d in diagnostics if d.resolved_target == "GitHub.cli"]
    assert len(update_diags) == 1
    diag = update_diags[0]
    assert diag.action == "update"
    assert diag.applied is True
    assert diag.confidence == 100.0


def test_conversational_filler_stripping():
    """compile('please install github and update 7zip for me') strips noise and resolves both."""
    compiler = OfflineIntentCompiler()
    prompt = "please install github and update 7zip for me"
    state, diagnostics = compiler.compile(prompt)

    pkg_ids = [p.id for p in state.winget]
    assert "GitHub.cli" in pkg_ids
    assert "7zip.7zip" in pkg_ids

    diag_map = {d.resolved_target: d for d in diagnostics}
    assert diag_map["GitHub.cli"].action == "add"
    assert diag_map["7zip.7zip"].action == "update"

    unresolved = compiler.find_unresolved(prompt, diagnostics)
    assert unresolved == []


def test_git_sync_meta_action():
    """compile('sync my state to github') triggers git_sync diagnostic without unresolved errors."""
    compiler = OfflineIntentCompiler()
    prompt = "sync my state to github"
    state, diagnostics = compiler.compile(prompt)

    sync_diags = [d for d in diagnostics if d.resolved_target == "git_sync"]
    assert len(sync_diags) == 1
    assert sync_diags[0].action == "push"
    assert sync_diags[0].applied is True

    unresolved = compiler.find_unresolved(prompt, diagnostics)
    assert unresolved == []


def test_upgrade_gh_alias():
    """compile('upgrade gh') correctly uses alias 'gh' for GitHub.cli."""
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("upgrade gh")

    pkg_ids = [p.id for p in state.winget]
    assert "GitHub.cli" in pkg_ids
    assert any(d.resolved_target == "GitHub.cli" and d.action == "update" for d in diagnostics)


def test_git_push_and_repo_sync_phrases():
    """Verify various vernacular phrasing for Git synchronization."""
    compiler = OfflineIntentCompiler()
    for phrase in [
        "push to github",
        "sync repo",
        "update remote",
        "push state",
        "backup config",
        "pull latest",
    ]:
        state, diagnostics = compiler.compile(phrase)
        assert any(d.resolved_target == "git_sync" for d in diagnostics), f"Failed for {phrase}"
        unresolved = compiler.find_unresolved(phrase, diagnostics)
        assert unresolved == [], f"Unresolved for {phrase}: {unresolved}"


def test_compound_natural_speech_with_preset():
    """compile('can you update github and enable dark mode please') handles compound natural speech."""
    compiler = OfflineIntentCompiler()
    prompt = "can you update github and enable dark mode please"
    state, diagnostics = compiler.compile(prompt)

    assert any(p.id == "GitHub.cli" for p in state.winget)
    assert state.system.get("dark_mode") is True
    assert state.system.get("light_mode") is False

    unresolved = compiler.find_unresolved(prompt, diagnostics)
    assert unresolved == []


def test_system_sweep_update():
    """compile('Update all my apps') triggers system_sweep diagnostic with zero unresolved clauses."""
    compiler = OfflineIntentCompiler()
    for prompt in ["Update all my apps", "update all apps", "upgrade everything"]:
        state, diagnostics = compiler.compile(prompt)
        assert len(diagnostics) == 1
        assert diagnostics[0].target_type == "system_sweep"
        assert diagnostics[0].resolved_target == "all_packages"
        assert diagnostics[0].action == "update"
        assert diagnostics[0].applied is True

        unresolved = compiler.find_unresolved(prompt, diagnostics)
        assert unresolved == [], f"Unresolved for {prompt}: {unresolved}"

