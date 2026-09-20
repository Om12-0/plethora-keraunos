"""Deterministic offline intent compiler: English prompt -> KeraunosState.

Zero-LLM deterministic compiler with whole-phrase RapidFuzz token_sort_ratio,
explicit polarity parsing, mutual exclusivity for theme, natural vernacular phrasing,
conversational filler stripping, package update/upgrade routing, and operational
Git/system action triggers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process

from keraunos.catalog import WINGET_CATALOG, search_winget_live
from keraunos.display import set_primary_monitor
from keraunos.scanner import assert_no_secrets
from keraunos.schema import KeraunosState, WinGetPackage
from keraunos.slm import extract_intent_slm

__all__ = [
    "ResolutionDiagnostic",
    "PHRASE_PRESET_MAP",
    "OfflineIntentCompiler",
    "INSTALL_VERBS",
    "REMOVE_VERBS",
    "UPDATE_VERBS",
    "FILLER_RE",
    "GREETINGS_RE",
    "SWEEP_UPDATE_RE",
    "DISPLAY_PATTERN",
    "TYPO_VERBS",
    "THEME_LIGHT_RE",
    "THEME_DARK_RE",
]

TYPO_VERBS = {
    r"\b(?:insall|intall|isnall|isntall|instl)\b": "install",
    r"\b(?:uninsall|unintall|remov|delet)\b": "uninstall",
    r"\b(?:updat|upgrd|updte)\b": "update",
}

THEME_LIGHT_RE = re.compile(r"\b(?:light\s*mode|light\s*theme|white\s*mode)\b", re.IGNORECASE)
THEME_DARK_RE = re.compile(r"\b(?:dark\s*mode|dark\s*theme|black\s*mode)\b", re.IGNORECASE)

DISPLAY_PRIMARY_RE = re.compile(
    r"\b(?:"
    r"(?:change|set|make|switch)\s+(?:the\s*)?(?:primary|main)\s+(?:screen|display|monitor)\s+(?:to\s*)?(?:screen\s*|monitor\s*|display\s*)?(\d+)|"
    r"(?:change|set|make|switch)\s+(?:the\s*)?(?:screen|display|monitor)\s+(\d+)\s+(?:to\s+be\s+)?(?:the\s*)?(?:primary|main)|"
    r"primary\s+(?:screen|display|monitor)\s+(?:to\s*)?(\d+)"
    r")\b",
    re.IGNORECASE,
)
DISPLAY_DUPLICATE_RE = re.compile(
    r"\b(?:"
    r"duplicate\s+(?:the\s*)?(?:screen[s]?|display[s]?|monitor[s]?)?(?:\s*(\d+)\s*(?:to|and|\&)\s*(\d+))?|"
    r"clone\s+(?:the\s*)?(?:screen[s]?|display[s]?|monitor[s]?)?(?:\s*(\d+)\s*(?:to|and|\&)\s*(\d+))?|"
    r"mirror\s+(?:the\s*)?(?:screen[s]?|display[s]?|monitor[s]?)?(?:\s*(\d+)\s*(?:to|and|\&)\s*(\d+))?"
    r")\b",
    re.IGNORECASE,
)
DISPLAY_EXTEND_RE = re.compile(
    r"\b(?:"
    r"extend\s+(?:the\s*)?(?:screen[s]?|display[s]?|monitor[s]?|desktop)?(?:\s*(\d+)\s*(?:to|and|\&)\s*(\d+))?"
    r")\b",
    re.IGNORECASE,
)
DISPLAY_INTERNAL_RE = re.compile(
    r"\b(?:pc\s*screen\s*only|first\s*screen\s*only|internal\s*display\s*only)\b",
    re.IGNORECASE,
)
DISPLAY_EXTERNAL_RE = re.compile(
    r"\b(?:second\s*screen\s*only|external\s*display\s*only|projector\s*only)\b",
    re.IGNORECASE,
)

DISPLAY_PATTERN = DISPLAY_PRIMARY_RE

INSTALL_VERBS = r"(?:install|add|get|setup|grab|fetch)"
REMOVE_VERBS = r"(?:uninstall|remove|delete|drop|purge)"
UPDATE_VERBS = r"(?:update|upgrade|refresh|bump)"

_CHOCO_INSTALL_RE = re.compile(rf"\b(?:choco|chocolatey)\s+{INSTALL_VERBS}\s+([a-zA-Z0-9][a-zA-Z0-9\s\-_~\.\+]*?)(?=$)", flags=re.IGNORECASE)
_SCOOP_INSTALL_RE = re.compile(rf"\bscoop\s+{INSTALL_VERBS}\s+([a-zA-Z0-9][a-zA-Z0-9\s\-_~\.\+]*?)(?=$)", flags=re.IGNORECASE)

# System-wide update sweep pattern (evaluated BEFORE filler stripping)
SWEEP_UPDATE_RE = re.compile(
    r"^\s*(?:please\s+)?(?:can\s+you\s+)?(?:could\s+you\s+)?(?:update|upgrade|refresh)\s+(?:all|everything|all\s+my\s+apps|all\s+apps|all\s+packages|system\s+apps|packages|my\s+apps)\s*[\?!.]*$",
    re.IGNORECASE,
)

# Conversational greetings and help inquiries
GREETINGS_RE = re.compile(
    r"^(?:hi|hello|hey|greetings|help|what can you do|who are you|sup)(?:\s+(?:there|keraunos|me))?[\?!.]*$",
    re.IGNORECASE,
)

# Conversational filler expressions stripped prior to clause analysis
FILLER_RE = re.compile(
    r"\b(?:can you|could you|would you|please|i want to|i'd like to|just|hey keraunos|for me)\b",
    re.IGNORECASE,
)

# Filler words stripped from package candidates
_FILLER_WORDS = frozenset({
    "please", "also", "too", "now", "again", "for", "me", "my", "the",
    "a", "an", "on", "onto", "into", "windows", "machine", "laptop",
    "pc", "computer", "setup", "up", "latest", "version",
})

# Clause separators: commas, semicolons, and coordinating conjunctions
_CLAUSE_SPLIT = re.compile(r"[,;]|\band\b|\bplus\b|\bwith\b|\balso\b", flags=re.IGNORECASE)

_INSTALL_RE = re.compile(rf"\b{INSTALL_VERBS}\s+([a-zA-Z0-9][a-zA-Z0-9\s\-_~\.\+]*?)(?=$)", flags=re.IGNORECASE)
_REMOVE_RE = re.compile(rf"\b{REMOVE_VERBS}\s+([a-zA-Z0-9][a-zA-Z0-9\s\-_~\.\+]*?)(?=$)", flags=re.IGNORECASE)
_UPDATE_RE = re.compile(rf"\b{UPDATE_VERBS}\s+([a-zA-Z0-9][a-zA-Z0-9\s\-_~\.\+]*?)(?=$)", flags=re.IGNORECASE)

# Global operational meta-actions
_GIT_SYNC_RE = re.compile(
    r"\b(?:"
    r"push\s+(?:my\s+)?(?:state\s+)?to\s+github|"
    r"push\s+(?:my\s+)?state|"
    r"sync\s+(?:my\s+)?(?:state\s+to\s+github|repo|repository|state|remote|config)|"
    r"update\s+(?:my\s+)?(?:github\s+repo|remote(?:\s+repo)?|repo)|"
    r"backup\s+(?:my\s+)?(?:config|state)|"
    r"pull\s+latest"
    r")\b",
    re.IGNORECASE,
)

_SYSTEM_UPDATE_ALL_RE = re.compile(
    r"\b(?:"
    r"update\s+all\s+(?:my\s+)?packages|"
    r"upgrade\s+everything|"
    r"update\s+(?:all\s+)?apps|"
    r"upgrade\s+all(?:\s+packages)?|"
    r"update\s+all"
    r")\b",
    re.IGNORECASE,
)

_APP_UPDATE_RE = re.compile(
    r"\b(?:"
    r"check\s+(?:for\s+)?(?:app\s+)?updates|"
    r"update\s+(?:plethora\s+)?keraunos|"
    r"upgrade\s+(?:plethora\s+)?keraunos|"
    r"update\s+this\s+app|"
    r"app\s+update"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class ResolutionDiagnostic:
    original_token: str
    resolved_target: str
    target_type: str  # "package" | "preset" | "action"
    confidence: float
    action: str  # "add" | "remove" | "update" | "enable" | "disable" | "push"
    applied: bool = True  # True if applied to state; False if purely a UI suggestion


# Canonical dictionary of phrases to canonical preset keys and target boolean values
PHRASE_PRESET_MAP: Dict[str, Tuple[str, bool]] = {
    # System Theme
    "dark mode": ("dark_mode", True),
    "dark theme": ("dark_mode", True),
    "light mode": ("light_mode", True),
    "light theme": ("light_mode", True),
    "enable dark mode": ("dark_mode", True),
    "enable dark theme": ("dark_mode", True),
    "disable dark mode": ("light_mode", True),
    "disable dark theme": ("light_mode", True),
    "enable light mode": ("light_mode", True),
    "enable light theme": ("light_mode", True),
    "disable light mode": ("dark_mode", True),
    "disable light theme": ("dark_mode", True),
    "disabl light mode": ("dark_mode", True),
    "disabl dark mode": ("light_mode", True),
    "turn off light mode": ("dark_mode", True),
    "turn on dark mode": ("dark_mode", True),
    "turn off dark mode": ("light_mode", True),
    "turn on light mode": ("light_mode", True),
    # Taskbar Search
    "hide taskbar search": ("hide_taskbar_search", True),
    "hide search bar": ("hide_taskbar_search", True),
    "remove search bar": ("hide_taskbar_search", True),
    "disable taskbar search": ("hide_taskbar_search", True),
    "show taskbar search": ("hide_taskbar_search", False),
    "show search bar": ("hide_taskbar_search", False),
    "enable taskbar search": ("hide_taskbar_search", False),
    "enable search bar": ("hide_taskbar_search", False),
    # Bing in Search
    "disable bing search": ("disable_bing_in_start_search", True),
    "disable bing in start search": ("disable_bing_in_start_search", True),
    "remove bing search": ("disable_bing_in_start_search", True),
    "enable bing search": ("disable_bing_in_start_search", False),
    # Explorer Options
    "show file extensions": ("show_file_extensions", True),
    "display file extensions": ("show_file_extensions", True),
    "hide file extensions": ("show_file_extensions", False),
    "show hidden files": ("show_hidden_files", True),
    "display hidden files": ("show_hidden_files", True),
    "hide hidden files": ("show_hidden_files", False),
    "compact view": ("compact_explorer_view", True),
    "compact explorer": ("compact_explorer_view", True),
    "comfortable view": ("compact_explorer_view", False),
    # Power tweaks
    "enable long paths": ("enable_long_paths", True),
    "long paths": ("enable_long_paths", True),
    "disable long paths": ("enable_long_paths", False),
    "disable game bar": ("disable_game_bar", True),
    "game bar": ("disable_game_bar", True),
    "enable game bar": ("disable_game_bar", False),
}

NEGATION_STEMS = ("disable", "disabl", "turn off", "remove", "deactivate", "stop", "hide", "no")
AFFIRMATIVE_STEMS = ("enable", "enabl", "turn on", "activate", "start", "show", "set", "use", "make")


class OfflineIntentCompiler:
    """High-speed deterministic prompt -> state compiler (fully offline)."""

    def __init__(self, catalog: Optional[Dict[str, str]] = None):
        self.catalog: Dict[str, str] = catalog if catalog is not None else WINGET_CATALOG

    # -- resolution -------------------------------------------------------------
    def resolve_package(self, raw_name: str,
                         min_confidence: float = 75.0) -> Tuple[Optional[str], float]:
        clean = (raw_name or "").strip().lower()
        if not clean:
            return None, 0.0
        # Guard: Reject single digits, pure numbers, or single-char tokens from catalog matching
        if clean.isdigit() or len(clean) <= 1:
            return None, 0.0
        # 1. Exact match against catalog keys
        if clean in self.catalog:
            return self.catalog[clean], 100.0
        # 2. Dotted WinGet ID passthrough
        if "." in clean and not any(c in clean for c in " \t"):
            return raw_name.strip(), 100.0
        # 3. Fuzzy match against catalog keys via token_sort_ratio
        result = process.extractOne(clean, self.catalog.keys(), scorer=fuzz.token_sort_ratio)
        if result:
            match_key, score, _ = result
            if score >= min_confidence:
                return self.catalog[match_key], float(score)
            # Fallback N-Gram Typo Matcher for shorthand typos (>= 68%)
            if score >= 68.0:
                return self.catalog[match_key], float(score)
        # 4. Fallback query to local winget CLI for unlisted packages
        live_id = search_winget_live(clean)
        if live_id:
            return live_id, 90.0
        return None, 0.0

    def resolve_preset(self, clause: str,
                        min_confidence: float = 75.0) -> Optional[Tuple[str, bool, float]]:
        clean = (clause or "").strip().lower()
        if not clean:
            return None

        # 1. Exact phrase hit
        if clean in PHRASE_PRESET_MAP:
            preset_key, original_val = PHRASE_PRESET_MAP[clean]
            if preset_key in ("light_mode", "dark_mode") or "light" in clean or "dark" in clean:
                if not (THEME_LIGHT_RE.search(clean) or THEME_DARK_RE.search(clean)):
                    return None
            return preset_key, original_val, 100.0

        # 2. Extract single best phrase match via whole-phrase token_sort_ratio
        result = process.extractOne(clean, PHRASE_PRESET_MAP.keys(), scorer=fuzz.token_sort_ratio)
        if not result:
            return None

        matched_phrase, score, _ = result
        if score < min_confidence:
            return None

        preset_key, original_val = PHRASE_PRESET_MAP[matched_phrase]
        target_val = original_val

        # Theme guard: ensure light_mode/dark_mode only match when accompanied by explicit theme keywords
        if preset_key in ("light_mode", "dark_mode") or "light" in matched_phrase or "dark" in matched_phrase:
            if not (THEME_LIGHT_RE.search(clean) or THEME_DARK_RE.search(clean)):
                return None

        # 3. Explicit Polarity Inversion & Theme Routing
        has_negation = any(neg in clean for neg in NEGATION_STEMS)
        matched_has_negation = any(neg in matched_phrase for neg in NEGATION_STEMS)

        if has_negation and not matched_has_negation:
            if "light" in matched_phrase or preset_key == "light_mode":
                preset_key = "dark_mode"
                target_val = True
            elif "dark" in matched_phrase or preset_key == "dark_mode":
                preset_key = "light_mode"
                target_val = True
            else:
                target_val = not original_val

        return preset_key, target_val, float(score)

    # -- compilation --------------------------------------------------------------
    @staticmethod
    def split_clauses(prompt: str) -> List[str]:
        # Pre-normalize typo verbs
        normalized = prompt or ""
        for pattern, replacement in TYPO_VERBS.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        # Pre-strip conversational noise
        cleaned = FILLER_RE.sub(" ", normalized)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return [c.strip(" \t.") for c in _CLAUSE_SPLIT.split(cleaned) if c.strip(" \t.")]

    @classmethod
    def _clean_candidate(cls, candidate: str) -> str:
        words = [w for w in candidate.strip().lower().split() if w not in _FILLER_WORDS]
        while words and words[0] in _FILLER_WORDS:
            words.pop(0)
        return " ".join(words).strip()

    def _add_package(self, state: KeraunosState, pkg_id: str) -> bool:
        if any(p.id.lower() == pkg_id.lower() for p in state.winget):
            return False
        state.winget.append(WinGetPackage(id=pkg_id))
        return True

    def compile(
        self,
        text_prompt: str,
        base_state: Optional[KeraunosState] = None,
        auto_apply_threshold: float = 85.0,
        suggestion_threshold: float = 75.0,
    ) -> Tuple[KeraunosState, List[ResolutionDiagnostic]]:
        """Compile a prompt into (state, diagnostics). Never touches the network.

        Threshold gating:
          - confidence >= auto_apply_threshold (85%): applied=True, mutates state.
          - suggestion_threshold <= confidence < auto_apply_threshold: applied=False, UI suggestion only.
          - confidence < suggestion_threshold: Unresolved.
        """
        if not text_prompt or not text_prompt.strip():
            raise ValueError("Prompt must be non-empty")
        assert_no_secrets(text_prompt, context="prompt")

        state = base_state.model_copy(deep=True) if base_state else KeraunosState()
        diagnostics: List[ResolutionDiagnostic] = []

        trimmed_prompt = text_prompt.strip()

        # Multi-Monitor Hardware Display Extraction (Primary, Duplicate, Extend, Internal, External)
        working_prompt = trimmed_prompt

        # 1. Primary monitor match
        prim_match = DISPLAY_PRIMARY_RE.search(working_prompt)
        if prim_match:
            g = [m for m in prim_match.groups() if m]
            monitor_num = int(g[0]) if g else 1
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=prim_match.group(0),
                    resolved_target=f"Primary Monitor -> Display {monitor_num}",
                    target_type="hardware_display",
                    confidence=100.0,
                    action="set_primary",
                    applied=True,
                )
            )
            state.custom_actions.append({"type": "set_primary_monitor", "index": monitor_num})
            working_prompt = working_prompt[:prim_match.start()] + " " + working_prompt[prim_match.end():]

        # 2. Duplicate / Clone / Mirror match
        dup_match = DISPLAY_DUPLICATE_RE.search(working_prompt)
        if dup_match:
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=dup_match.group(0),
                    resolved_target="Display Topology -> Duplicate (Clone)",
                    target_type="hardware_display",
                    confidence=100.0,
                    action="set_topology",
                    applied=True,
                )
            )
            state.custom_actions.append({"type": "set_display_topology", "topology": "clone"})
            working_prompt = working_prompt[:dup_match.start()] + " " + working_prompt[dup_match.end():]

        # 3. Extend match
        ext_match = DISPLAY_EXTEND_RE.search(working_prompt)
        if ext_match:
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=ext_match.group(0),
                    resolved_target="Display Topology -> Extend Desktop",
                    target_type="hardware_display",
                    confidence=100.0,
                    action="set_topology",
                    applied=True,
                )
            )
            state.custom_actions.append({"type": "set_display_topology", "topology": "extend"})
            working_prompt = working_prompt[:ext_match.start()] + " " + working_prompt[ext_match.end():]

        # 4. PC Screen Only (Internal)
        int_match = DISPLAY_INTERNAL_RE.search(working_prompt)
        if int_match:
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=int_match.group(0),
                    resolved_target="Display Topology -> PC Screen Only",
                    target_type="hardware_display",
                    confidence=100.0,
                    action="set_topology",
                    applied=True,
                )
            )
            state.custom_actions.append({"type": "set_display_topology", "topology": "pc_only"})
            working_prompt = working_prompt[:int_match.start()] + " " + working_prompt[int_match.end():]

        # 5. Second Screen Only (External)
        ext_only_match = DISPLAY_EXTERNAL_RE.search(working_prompt)
        if ext_only_match:
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=ext_only_match.group(0),
                    resolved_target="Display Topology -> Second Screen Only",
                    target_type="hardware_display",
                    confidence=100.0,
                    action="set_topology",
                    applied=True,
                )
            )
            state.custom_actions.append({"type": "set_display_topology", "topology": "second_only"})
            working_prompt = working_prompt[:ext_only_match.start()] + " " + working_prompt[ext_only_match.end():]

        working_prompt = working_prompt.strip()
        if not working_prompt and diagnostics:
            return state, diagnostics

        # System-wide software update sweep check (evaluated BEFORE filler stripping)
        if SWEEP_UPDATE_RE.match(trimmed_prompt):
            for p in state.winget:
                p.version = None
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=trimmed_prompt,
                    resolved_target="all_packages",
                    target_type="system_sweep",
                    confidence=100.0,
                    action="update",
                    applied=True,
                )
            )
            return state, diagnostics

        # Conversational greeting & help check
        if GREETINGS_RE.match(trimmed_prompt):
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=trimmed_prompt,
                    resolved_target="welcome",
                    target_type="greeting",
                    confidence=100.0,
                    action="greet",
                    applied=True,
                )
            )
            return state, diagnostics

        for raw_clause in self.split_clauses(working_prompt or text_prompt):
            clause = raw_clause.strip()
            if not clause:
                continue
            lower = clause.lower()

            # -------------------------------------------------------------
            # 0. Global Action Keywords (Git Sync & System Updates)
            # -------------------------------------------------------------
            if _GIT_SYNC_RE.search(lower):
                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=clause,
                        resolved_target="git_sync",
                        target_type="action",
                        confidence=100.0,
                        action="push",
                        applied=True,
                    )
                )
                continue

            if _SYSTEM_UPDATE_ALL_RE.search(lower):
                for p in state.winget:
                    p.version = None  # Ensure latest version
                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=clause,
                        resolved_target="all_packages",
                        target_type="action",
                        confidence=100.0,
                        action="update",
                        applied=True,
                    )
                )
                continue

            if _APP_UPDATE_RE.search(lower):
                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=clause,
                        resolved_target="check_app_updates",
                        target_type="action",
                        confidence=100.0,
                        action="update",
                        applied=True,
                    )
                )
                continue

            # -------------------------------------------------------------
            # 1. Preset Check (Strict single best-match per clause)
            # -------------------------------------------------------------
            preset_match = self.resolve_preset(lower, min_confidence=suggestion_threshold)
            if preset_match:
                preset_key, val, conf = preset_match
                is_auto_apply = conf >= auto_apply_threshold

                if is_auto_apply:
                    if preset_key == "dark_mode" and val:
                        state.system["dark_mode"] = True
                        state.system["light_mode"] = False
                    elif preset_key == "light_mode" and val:
                        state.system["light_mode"] = True
                        state.system["dark_mode"] = False
                    else:
                        state.system[preset_key] = val

                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=clause,
                        resolved_target=preset_key,
                        target_type="preset",
                        confidence=conf,
                        action="enable" if val else "disable",
                        applied=is_auto_apply,
                    )
                )
                continue

            # -------------------------------------------------------------
            # 2. Package Removal: "uninstall|remove|delete <name>"
            # -------------------------------------------------------------
            remove_match = _REMOVE_RE.search(lower)
            if remove_match:
                candidate = self._clean_candidate(remove_match.group(1))
                if candidate:
                    pkg_id, conf = self.resolve_package(candidate, min_confidence=suggestion_threshold)
                    target_id = pkg_id or candidate
                    is_auto_apply = conf >= auto_apply_threshold

                    if is_auto_apply and pkg_id:
                        state.winget = [p for p in state.winget if p.id.lower() != target_id.lower()]

                    diagnostics.append(
                        ResolutionDiagnostic(
                            original_token=candidate,
                            resolved_target=target_id,
                            target_type="package",
                            confidence=conf if pkg_id else 0.0,
                            action="remove",
                            applied=is_auto_apply and bool(pkg_id),
                        )
                    )
                continue

            # -------------------------------------------------------------
            # 3. Package Update / Upgrade: "update|upgrade|refresh|bump <name>"
            # -------------------------------------------------------------
            update_match = _UPDATE_RE.search(lower)
            if update_match:
                candidate = self._clean_candidate(update_match.group(1))
                if candidate:
                    pkg_id, conf = self.resolve_package(candidate, min_confidence=suggestion_threshold)
                    if pkg_id:
                        is_auto_apply = conf >= auto_apply_threshold
                        if is_auto_apply:
                            # If existing, ensure latest; if not, add it
                            existing = next((p for p in state.winget if p.id.lower() == pkg_id.lower()), None)
                            if existing:
                                existing.version = None
                            else:
                                self._add_package(state, pkg_id)

                        diagnostics.append(
                            ResolutionDiagnostic(
                                original_token=candidate,
                                resolved_target=pkg_id,
                                target_type="package",
                                confidence=conf,
                                action="update",
                                applied=is_auto_apply,
                            )
                        )
                continue

            # -------------------------------------------------------------
            # 3b. Explicit Package Managers: "choco|chocolatey install <name>" / "scoop install <name>"
            # -------------------------------------------------------------
            choco_match = _CHOCO_INSTALL_RE.search(lower)
            if choco_match:
                candidate = self._clean_candidate(choco_match.group(1))
                if candidate:
                    if candidate not in state.choco:
                        state.choco.append(candidate)
                    diagnostics.append(
                        ResolutionDiagnostic(
                            original_token=candidate,
                            resolved_target=f"choco:{candidate}",
                            target_type="package_choco",
                            confidence=100.0,
                            action="add",
                            applied=True,
                        )
                    )
                continue

            scoop_match = _SCOOP_INSTALL_RE.search(lower)
            if scoop_match:
                candidate = self._clean_candidate(scoop_match.group(1))
                if candidate:
                    if candidate not in state.scoop:
                        state.scoop.append(candidate)
                    diagnostics.append(
                        ResolutionDiagnostic(
                            original_token=candidate,
                            resolved_target=f"scoop:{candidate}",
                            target_type="package_scoop",
                            confidence=100.0,
                            action="add",
                            applied=True,
                        )
                    )
                continue

            # -------------------------------------------------------------
            # 4. Package Addition: "install|add|get|setup <name>"
            # -------------------------------------------------------------
            install_match = _INSTALL_RE.search(lower)
            if install_match:
                candidate = self._clean_candidate(install_match.group(1))
                if candidate:
                    pkg_id, conf = self.resolve_package(candidate, min_confidence=suggestion_threshold)
                    if pkg_id:
                        is_auto_apply = conf >= auto_apply_threshold
                        if is_auto_apply:
                            self._add_package(state, pkg_id)

                        diagnostics.append(
                            ResolutionDiagnostic(
                                original_token=candidate,
                                resolved_target=pkg_id,
                                target_type="package",
                                confidence=conf,
                                action="add",
                                applied=is_auto_apply,
                            )
                        )
                continue

            # -------------------------------------------------------------
            # 5. Bare-name Fallback (e.g. "7zip", "Microsoft.VisualStudioCode")
            # -------------------------------------------------------------
            cleaned_full = self._clean_candidate(clause)
            if not cleaned_full:
                continue

            pkg_id, conf = self.resolve_package(cleaned_full, min_confidence=suggestion_threshold)
            if pkg_id and self._looks_like_package_token(cleaned_full):
                is_auto_apply = conf >= auto_apply_threshold
                if is_auto_apply:
                    self._add_package(state, pkg_id)

                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=cleaned_full,
                        resolved_target=pkg_id,
                        target_type="package",
                        confidence=conf,
                        action="add",
                        applied=is_auto_apply,
                    )
                )
                continue

            for token in cleaned_full.split():
                hit = self.catalog.get(token)
                if hit:
                    self._add_package(state, hit)
                    diagnostics.append(
                        ResolutionDiagnostic(
                            original_token=token,
                            resolved_target=hit,
                            target_type="package",
                            confidence=100.0,
                            action="add",
                            applied=True,
                        )
                    )

        # =================================================================
        # TIER 2: SLM Fallback (Qwen2.5-0.5B local inference)
        # Route to SLM when:
        #   (a) unresolved clauses remain, OR
        #   (b) prompt is complex natural speech (6+ words) with no applied results
        # =================================================================
        applied_count = sum(1 for d in diagnostics if d.applied)
        unresolved = self.find_unresolved(text_prompt, diagnostics)
        word_count = len(trimmed_prompt.split())

        if unresolved or (word_count >= 6 and applied_count == 0):
            slm_input = ", ".join(unresolved) if unresolved else trimmed_prompt
            try:
                slm_result = extract_intent_slm(slm_input)
                if slm_result:
                    self._apply_slm_result(state, diagnostics, slm_result, prompt=trimmed_prompt)
            except Exception:
                pass  # Graceful degradation: Tier-1 only

        # Dedupe identical diagnostics while preserving order
        seen, unique = set(), []
        for d in diagnostics:
            key = (d.original_token.lower(), d.resolved_target.lower(), d.action)
            if key not in seen:
                seen.add(key)
                unique.append(d)
        return state, unique

    @staticmethod
    def _looks_like_package_token(text: str) -> bool:
        """Guard so prose clauses ('make my setup fast') don't become packages."""
        if not text or len(text.split()) > 4:
            return False
        return True

    def _apply_slm_result(
        self,
        state: KeraunosState,
        diagnostics: List[ResolutionDiagnostic],
        slm_result: Dict,
        prompt: str = "",
    ) -> None:
        """Translate SLM JSON output into state mutations and diagnostics."""
        # -- packages --
        for pkg in slm_result.get("packages", []):
            name = (pkg.get("name") or "").strip()
            action = (pkg.get("action") or "install").strip().lower()
            if not name:
                continue

            pkg_id, conf = self.resolve_package(name, min_confidence=60.0)
            if not pkg_id:
                continue

            if action == "install":
                self._add_package(state, pkg_id)
                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=name,
                        resolved_target=pkg_id,
                        target_type="package",
                        confidence=95.0,
                        action="add",
                        applied=True,
                    )
                )
            elif action == "remove":
                state.winget = [p for p in state.winget if p.id.lower() != pkg_id.lower()]
                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=name,
                        resolved_target=pkg_id,
                        target_type="package",
                        confidence=95.0,
                        action="remove",
                        applied=True,
                    )
                )
            elif action == "update":
                existing = next((p for p in state.winget if p.id.lower() == pkg_id.lower()), None)
                if existing:
                    existing.version = None
                else:
                    self._add_package(state, pkg_id)
                diagnostics.append(
                    ResolutionDiagnostic(
                        original_token=name,
                        resolved_target=pkg_id,
                        target_type="package",
                        confidence=95.0,
                        action="update",
                        applied=True,
                    )
                )

        # -- presets --
        for preset in slm_result.get("presets", []):
            key = (preset.get("key") or "").strip()
            val = preset.get("value", True)
            if not key:
                continue

            # Theme guard: ensure light_mode/dark_mode only apply when accompanied by explicit theme keywords in prompt
            if key in ("light_mode", "dark_mode"):
                if not (THEME_LIGHT_RE.search(prompt) or THEME_DARK_RE.search(prompt)):
                    continue

            # Enforce mutual exclusivity for theme presets
            if key == "dark_mode" and val:
                state.system["dark_mode"] = True
                state.system["light_mode"] = False
            elif key == "light_mode" and val:
                state.system["light_mode"] = True
                state.system["dark_mode"] = False
            else:
                state.system[key] = val

            diagnostics.append(
                ResolutionDiagnostic(
                    original_token=key,
                    resolved_target=key,
                    target_type="preset",
                    confidence=95.0,
                    action="enable" if val else "disable",
                    applied=True,
                )
            )

        # -- meta_action --
        meta = slm_result.get("meta_action")
        if meta == "update_all":
            for p in state.winget:
                p.version = None
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token="update_all",
                    resolved_target="all_packages",
                    target_type="system_sweep",
                    confidence=95.0,
                    action="update",
                    applied=True,
                )
            )
        elif meta == "git_sync":
            diagnostics.append(
                ResolutionDiagnostic(
                    original_token="git_sync",
                    resolved_target="git_sync",
                    target_type="action",
                    confidence=95.0,
                    action="push",
                    applied=True,
                )
            )

    BARE_VERBS = frozenset({"update", "upgrade", "refresh", "bump", "install", "add", "get", "setup", "uninstall", "remove", "delete", "set"})

    # -- unresolved reporting (for UI warning banners) -------------------------------
    def find_unresolved(self, text_prompt: str,
                         diagnostics: List[ResolutionDiagnostic]) -> List[str]:
        """Clauses that produced no preset/package/action diagnostic."""
        if any(d.target_type in ("greeting", "system_sweep", "hardware_display") for d in diagnostics):
            return []
        unresolved: List[str] = []
        for clause in self.split_clauses(text_prompt):
            low = clause.lower().strip()
            if not low or low in self.BARE_VERBS or GREETINGS_RE.match(low):
                continue
            covered = False
            for d in diagnostics:
                if d.original_token.lower() == low or d.original_token.lower() in low or low in d.original_token.lower():
                    covered = True
                    break
                if d.target_type == "package" and (
                    d.original_token.lower() in low or d.resolved_target.lower() in low
                ):
                    covered = True
                    break
                if d.target_type in ("action", "system_sweep", "hardware_display"):
                    if d.resolved_target in ("git_sync", "all_packages") or d.target_type == "hardware_display":
                        covered = True
                        break
            if not covered:
                unresolved.append(clause)
        return unresolved
