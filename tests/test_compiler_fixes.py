"""Regression tests for compiler matching, polarity routing, and threshold gating."""
from __future__ import annotations

import pytest

from keraunos.compiler import OfflineIntentCompiler


def test_disable_light_mode_enables_dark_mode():
    """compile('disable light mode') must set dark_mode=True and light_mode=False."""
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("disable light mode")

    assert state.system.get("dark_mode") is True
    assert state.system.get("light_mode") is False

    # Must be applied
    applied_presets = [d.resolved_target for d in diagnostics if d.applied]
    assert "dark_mode" in applied_presets


def test_disable_light_mode_zero_bing_search_mentions():
    """compile('disable light mode') must have ZERO mentions of Bing search."""
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("disable light mode")

    assert "disable_bing_in_start_search" not in state.system
    for d in diagnostics:
        assert "bing" not in d.resolved_target.lower()
        assert d.resolved_target != "disable_bing_in_start_search"


def test_disabl_light_mode_typo_handling():
    """compile('disabl light mode') handles the typo to turn on dark mode with zero Bing mentions."""
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile("disabl light mode")

    assert state.system.get("dark_mode") is True
    assert state.system.get("light_mode") is False

    assert "disable_bing_in_start_search" not in state.system
    for d in diagnostics:
        assert "bing" not in d.resolved_target.lower()
        assert d.resolved_target != "disable_bing_in_start_search"


def test_low_confidence_suggestion_does_not_mutate_system_state():
    """If a match has confidence < 85%, diagnostic.applied is False and system state is not mutated."""
    compiler = OfflineIntentCompiler()
    # "comfortable" matches "comfortable view" at ~81.5% confidence
    state, diagnostics = compiler.compile("comfortable")

    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert 75.0 <= diag.confidence < 85.0
    assert diag.applied is False
    assert "compact_explorer_view" not in state.system


def test_low_confidence_package_suggestion_does_not_mutate_winget():
    """Package suggestion below 85% is not added to state.winget."""
    compiler = OfflineIntentCompiler()
    # "install firef" matches "firefox" at ~83.3%
    state, diagnostics = compiler.compile("install firef")

    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert 75.0 <= diag.confidence < 85.0
    assert diag.applied is False
    assert len(state.winget) == 0


def test_mutual_exclusivity_dark_and_light_mode():
    """Enabling light mode explicitly disables dark mode and vice versa."""
    compiler = OfflineIntentCompiler()

    state_light, _ = compiler.compile("light mode")
    assert state_light.system.get("light_mode") is True
    assert state_light.system.get("dark_mode") is False

    state_dark, _ = compiler.compile("dark mode")
    assert state_dark.system.get("dark_mode") is True
    assert state_dark.system.get("light_mode") is False
