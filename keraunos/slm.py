"""
keraunos/slm.py - Local Embedded Small Language Model (Qwen2.5-0.5B).
Extracts declarative Windows actions from human speech offline with strict JSON schema.
Zero network calls, zero API keys. Fully air-gapped.
"""

import json
import os
import sys
from typing import Any, Dict, Optional

_LLM_INSTANCE = None

SYSTEM_PROMPT = """\
You are Keraunos SLM, an offline Windows system configuration intent extractor.
Given a user request, extract intended software installs/uninstalls/updates, and Windows system personalization tweaks.
You must output ONLY valid JSON matching this schema:
{
  "packages": [
    {"name": "string", "action": "install" | "remove" | "update"}
  ],
  "presets": [
    {"key": "dark_mode" | "light_mode" | "hide_taskbar_search" | "show_taskbar_search" | "disable_bing_in_start_search" | "enable_bing_in_start_search" | "show_file_extensions" | "hide_file_extensions" | "compact_explorer_view" | "enable_long_paths" | "disable_game_bar", "value": true | false}
  ],
  "meta_action": null | "update_all" | "git_sync"
}
If the user is just saying hello or asking for help, output empty arrays and meta_action null.
Do NOT invent packages or keys not listed above. Output JSON only. No explanations."""


def get_model_path() -> str:
    """Resolve GGUF model path for both frozen (PyInstaller) and dev environments."""
    base_dir = getattr(sys, "_MEIPASS", None)
    if base_dir:
        # Running from PyInstaller bundle
        model_path = os.path.join(base_dir, "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
        if os.path.exists(model_path):
            return model_path

    # Dev / repo fallback
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_path = os.path.join(repo_root, "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf")
    if os.path.exists(model_path):
        return model_path

    # CWD fallback
    return os.path.join(os.path.abspath("."), "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf")


def get_slm():
    """Lazy-load singleton Llama instance. Returns None if model unavailable."""
    global _LLM_INSTANCE
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    path = get_model_path()
    if not os.path.exists(path):
        return None

    try:
        from llama_cpp import Llama
        _LLM_INSTANCE = Llama(
            model_path=path,
            n_ctx=1024,
            n_threads=4,
            verbose=False,
        )
        return _LLM_INSTANCE
    except Exception:
        return None


def extract_intent_slm(text: str) -> Optional[Dict[str, Any]]:
    """Send natural language to the local SLM and extract structured intent JSON.

    Returns None if the model is unavailable or inference fails.
    """
    llm = get_slm()
    if not llm:
        return None

    try:
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        # Validate structure minimally
        if not isinstance(parsed, dict):
            return None
        if "packages" not in parsed:
            parsed["packages"] = []
        if "presets" not in parsed:
            parsed["presets"] = []
        if "meta_action" not in parsed:
            parsed["meta_action"] = None

        return parsed
    except Exception:
        return None
