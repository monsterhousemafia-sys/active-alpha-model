"""Geheimnisse aus Logs und JSON-Ausgaben entfernen."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping, Union

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_KV_RE = re.compile(
    r"(?i)(AA_CLOUDFLARE_TUNNEL_TOKEN|password|passwd|secret|api[_-]?key|token)\s*[=:]\s*(\S+)"
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_REDACTED = "[REDACTED]"


def redact_text(text: str) -> str:
    if not text:
        return text
    out = _JWT_RE.sub(_REDACTED, text)
    out = _KV_RE.sub(lambda m: f"{m.group(1)}={_REDACTED}", out)
    return out


def redact_mapping(doc: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, val in doc.items():
        key_l = str(key).lower()
        if (
            not isinstance(val, (bool, int, float))
            and any(
                mark in key_l
                for mark in ("token", "password", "secret", "passwd", "credential", "api_key")
            )
        ):
            out[key] = _REDACTED if val else val
            continue
        if isinstance(val, str):
            out[key] = redact_text(val)
        elif isinstance(val, Mapping):
            out[key] = redact_mapping(val)
        elif isinstance(val, list):
            out[key] = [
                redact_mapping(x) if isinstance(x, Mapping) else redact_text(x) if isinstance(x, str) else x
                for x in val
            ]
        else:
            out[key] = val
    return out


def safe_public_doc(doc: Mapping[str, Any]) -> Dict[str, Any]:
    return redact_mapping(deepcopy(dict(doc)))
