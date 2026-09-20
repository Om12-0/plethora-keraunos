"""
keraunos/slm.py - Ultra-lightweight offline SLM parser (~85 MB SmolLM2-135M).
Extracts Windows setup and package intents into strict JSON offline.
"""

import json
import os
import sys
from typing import Any, Dict, Optional
from llama_cpp import Llama

_SLM_INSTANCE: Optional[Llama] = None

SYSTEM_PRE_PROMPT = """You are Keraunos SLM. Extract Windows software and settings into JSON format with keys: packages, presets, meta_action."""

FEW_SHOT_USER = "install chrome and dark mode"
FEW_SHOT_ASSISTANT = '{"packages": [{"name": "chrome", "action": "install"}], "presets": [{"key": "dark_mode", "value": true}], "meta_action": null}'


def get_model_path() -> str:
    base_dir = getattr(sys, "_MEIPASS", os.path.abspath("."))
    model_path = os.path.join(base_dir, "models", "smollm2-135m-instruct-q4_k_m.gguf")
    if not os.path.exists(model_path):
        model_path = os.path.join(os.path.abspath("."), "models", "smollm2-135m-instruct-q4_k_m.gguf")
    return model_path


def get_slm() -> Optional[Llama]:
    global _SLM_INSTANCE
    if _SLM_INSTANCE is None:
        path = get_model_path()
        if os.path.exists(path):
            _SLM_INSTANCE = Llama(
                model_path=path,
                n_ctx=512,
                n_threads=4,
                verbose=False,
            )
    return _SLM_INSTANCE


def _safe_json_parse(content: str) -> Optional[Dict[str, Any]]:
    if not content or not content.strip():
        return None
    cleaned = content.strip()
    try:
        res = json.loads(cleaned)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # Truncation fallback: find last valid closing brace
    idx = cleaned.rfind("}")
    while idx > 0:
        candidate = cleaned[:idx+1]
        try:
            res = json.loads(candidate)
            if isinstance(res, dict):
                return res
        except Exception:
            idx = cleaned.rfind("}", 0, idx)
    return None


def extract_intent_slm(text: str) -> Optional[Dict[str, Any]]:
    llm = get_slm()
    if not llm:
        return None

    try:
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PRE_PROMPT},
                {"role": "user", "content": FEW_SHOT_USER},
                {"role": "assistant", "content": FEW_SHOT_ASSISTANT},
                {"role": "user", "content": text.strip()},
            ],
            temperature=0.0,
            max_tokens=256,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        parsed = _safe_json_parse(content)
        if not parsed:
            return None

        if "packages" not in parsed or not isinstance(parsed.get("packages"), list):
            parsed["packages"] = []
        if "presets" not in parsed or not isinstance(parsed.get("presets"), list):
            parsed["presets"] = []
        if "meta_action" not in parsed:
            parsed["meta_action"] = None

        return parsed
    except Exception:
        return None
