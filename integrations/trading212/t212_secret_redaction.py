"""Secret redaction helpers for Trading 212 logs and reports."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^\s\"']+)", re.MULTILINE),
    re.compile(r"(?i)(api[_-]?secret\s*[:=]\s*)([^\s\"']+)", re.MULTILINE),
    re.compile(r"(?i)(authorization\s*:\s*basic\s+)([a-z0-9+/=]+)", re.MULTILINE),
    re.compile(r"(?i)(TRADING212_API_KEY\s*=\s*)([^\s]+)"),
    re.compile(r"(?i)(TRADING212_API_SECRET\s*=\s*)([^\s]+)"),
)

_REDACTED = "[REDACTED]"


def redact_secrets(text: str) -> str:
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(lambda m: f"{m.group(1)}{_REDACTED}", out)
    return out


def contains_likely_secret(text: str) -> bool:
    lowered = text.lower()
    if "trading212_api_secret=" in lowered and _REDACTED not in text:
        return True
    if "authorization: basic " in lowered and _REDACTED not in lowered:
        # base64 blobs longer than typical placeholders
        match = re.search(r"authorization:\s*basic\s+([a-z0-9+/=]{20,})", lowered)
        return bool(match)
    return False


def audit_payload_for_secrets(payload: Dict[str, Any]) -> List[str]:
    findings: List[str] = []
    raw = str(payload)
    if contains_likely_secret(raw):
        findings.append("SECRET_PATTERN_DETECTED_IN_PAYLOAD")
    return findings
