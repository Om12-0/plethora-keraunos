"""
tests/test_slm.py - Integration and smoke tests for embedded Qwen2.5 SLM Tier-2 compiler.
"""
from keraunos.compiler import OfflineIntentCompiler
from keraunos.slm import extract_intent_slm, get_model_path, get_slm


def test_slm_model_file_exists():
    """Verify the GGUF model file is present in the models directory."""
    path = get_model_path()
    assert path.endswith("qwen2.5-0.5b-instruct-q4_k_m.gguf")


def test_slm_instance_lazy_loads():
    """Verify lazy-loading singleton returns an initialized Llama instance."""
    slm = get_slm()
    assert slm is not None


def test_slm_extract_intent_returns_valid_dict():
    """Verify extract_intent_slm returns structured JSON dictionary."""
    result = extract_intent_slm("turn on dark mode and install chrome")
    assert result is not None
    assert isinstance(result.get("packages"), list)
    assert isinstance(result.get("presets"), list)


def test_slm_hybrid_compiler_end_to_end():
    """End-to-end smoke test for natural complex speech resolved via SLM Tier 2."""
    compiler = OfflineIntentCompiler()
    prompt = "i am a student setting up my laptop please turn on dark mode and install chrome and vs code"
    state, diagnostics = compiler.compile(prompt)

    resolved_targets = [d.resolved_target for d in diagnostics]
    assert state.system.get("dark_mode") is True
    assert any("Chrome" in pkg.id for pkg in state.winget)
    assert any("VisualStudioCode" in pkg.id for pkg in state.winget)
    print("SLM Hybrid Verification: PASSED")
