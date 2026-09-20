"""Secret scanner — blocks API keys / tokens from entering state.yaml or git history."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

PATTERNS: List[str] = [
    r"(?i)sk-[a-zA-Z0-9]{32,}",  # sk- style secret token
    r"(?i)sk-ant-[a-zA-Z0-9\-_]{20,}",  # sk-ant style secret token
    r"(?i)xox[bap]-[a-zA-Z0-9\-]{10,}",  # Slack
    r"(?i)ghp_[a-zA-Z0-9]{36}",  # GitHub PAT (classic)
    r"(?i)github_pat_[a-zA-Z0-9_]{60,}",  # GitHub fine-grained PAT
    r"(?i)gsk_[a-zA-Z0-9]{30,}",  # Groq
    r"(?i)AKIA[0-9A-Z]{16}",  # AWS access key id
    r"-----BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY-----",
    r"(?i)aws_secret_access_key\s*[:=]\s*[A-Za-z0-9/+=]{30,}",
    r"(?i)openai_api_key\s*[:=]\s*sk-[a-zA-Z0-9\-_]{10,}",
]

_COMPILED = [re.compile(p) for p in PATTERNS]


@dataclass(frozen=True)
class SecretFinding:
    pattern: str
    match_preview: str  # redacted preview, never the full secret
    line: int = 0


def _redact(match: str) -> str:
    if len(match) <= 8:
        return "***"
    return f"{match[:4]}***{match[-2:]}"


def scan_text_for_secrets(content: str) -> List[str]:
    """Return the list of patterns that matched (legacy simple API)."""
    findings: List[str] = []
    for pattern, rx in zip(PATTERNS, _COMPILED):
        if rx.search(content or ""):
            findings.append(pattern)
    return findings


def scan_text_detailed(content: str) -> List[SecretFinding]:
    """Return detailed, redacted findings with line numbers."""
    out: List[SecretFinding] = []
    for pattern, rx in zip(PATTERNS, _COMPILED):
        for i, line in enumerate((content or "").splitlines(), start=1):
            for m in rx.finditer(line):
                out.append(SecretFinding(pattern=pattern, match_preview=_redact(m.group(0)), line=i))
    return out


def scan_file(path: Path | str) -> List[SecretFinding]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text_detailed(text)


def assert_no_secrets(content: str, *, context: str = "state") -> None:
    findings = scan_text_detailed(content)
    if findings:
        lines = sorted({f.line for f in findings})
        raise ValueError(
            f"Refusing to persist {context}: {len(findings)} potential secret(s) "
            f"matched on line(s) {lines}. Remove API keys/tokens before committing."
        )
