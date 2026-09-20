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

from keraunos.catalog import WINGET_CATALOG
from keraunos.scanner import assert_no_secrets
from keraunos.schema import KeraunosState, WinGetPackage

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
]

INSTALL_VERBS = r"(?:install|add|get|setup|grab|fetch)"
REMOVE_VERBS = r"(?:uninstall|remove|delete|drop|purge)"
UPDATE_VERBS = r"(?:update|upgrade|refresh|bump)"

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
        return None, 0.0

    def resolve_preset(self, clause: str,
                        min_confidence: float = 75.0) -> Optional[Tuple[str, bool, float]]:
        clean = (clause or "").strip().lower()
        if not clean:
            return None

        # 1. Exact phrase hit
        if clean in PHRASE_PRESET_MAP:
            preset_key, original_val = PHRASE_PRESET_MAP[clean]
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
        # Pre-strip conversational noise
        cleaned = FILLER_RE.sub(" ", prompt or "")
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

        for raw_clause in self.split_clauses(text_prompt):
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

    BARE_VERBS = frozenset({"update", "upgrade", "refresh", "bump", "install", "add", "get", "setup", "uninstall", "remove", "delete", "set"})

    # -- unresolved reporting (for UI warning banners) -------------------------------
    def find_unresolved(self, text_prompt: str,
                        diagnostics: List[ResolutionDiagnostic]) -> List[str]:
        """Clauses that produced no preset/package/action diagnostic."""
        if any(d.target_type in ("greeting", "system_sweep") for d in diagnostics):
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
                if d.target_type in ("action", "system_sweep"):
                    if d.resolved_target in ("git_sync", "all_packages"):
                        covered = True
                        break
            if not covered:
                unresolved.append(clause)
        return unresolved
