"""
tests/test_display_and_typos.py - Unit tests for Win32 Display Engine, Typo Verb Normalization, and Custom Actions.
"""
from keraunos.compiler import OfflineIntentCompiler
from keraunos.display import set_primary_monitor
from keraunos.executor import ExecutionEngine
from keraunos.schema import KeraunosState


def test_display_pattern_resolution():
    compiler = OfflineIntentCompiler()
    prompt = "change primary screen to screen 1"
    state, diagnostics = compiler.compile(prompt)

    assert len(diagnostics) == 1
    assert diagnostics[0].target_type == "hardware_display"
    assert diagnostics[0].resolved_target == "Primary Monitor -> Display 1"
    assert diagnostics[0].confidence == 100.0
    assert diagnostics[0].applied is True

    assert len(state.custom_actions) == 1
    assert state.custom_actions[0] == {"type": "set_primary_monitor", "index": 1}


def test_display_pattern_variations():
    compiler = OfflineIntentCompiler()
    for prompt in [
        "set main display to 2",
        "switch primary monitor to monitor 1",
        "make main screen display 2",
    ]:
        state, diagnostics = compiler.compile(prompt)
        assert any(d.target_type == "hardware_display" for d in diagnostics)
        assert len(state.custom_actions) > 0


def test_typo_verb_normalization():
    compiler = OfflineIntentCompiler()
    prompt = "insall chrome, uninsall edge, updte 7zip"
    state, diagnostics = compiler.compile(prompt)

    resolved_targets = [d.resolved_target for d in diagnostics if d.applied]
    assert "Google.Chrome" in resolved_targets
    assert "7zip.7zip" in resolved_targets


def test_fallback_ngram_typo_matcher():
    compiler = OfflineIntentCompiler()
    # Shorthand / typo for vs code
    pkg_id, conf = compiler.resolve_package("vs coe")
    assert pkg_id == "Microsoft.VisualStudioCode"
    assert conf >= 68.0


def test_display_diff_rendering():
    engine = ExecutionEngine()
    state = KeraunosState()
    state.custom_actions.append({"type": "set_primary_monitor", "index": 2})

    diff = engine.calculate_diff(state)
    assert len(diff.get("custom_actions", [])) == 1
    diff_text = engine.render_diff_text(diff)
    assert "hardware.display.primary = Display 2" in diff_text
