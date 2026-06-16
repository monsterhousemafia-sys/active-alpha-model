"""Anonym-Policy — Internet-only Spread, kein König-Fußabdruck."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

_POLICY_REL = Path("control/spread_anonym_policy.json")
_LAN_RE = re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b")
_HOME_RE = re.compile(r"/home/[a-z0-9_-]+/")


def load_policy(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / _POLICY_REL
    if not path.is_file():
        return {"schema_version": 1, "anonym_enforced": True}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"anonym_enforced": True}
    except (json.JSONDecodeError, OSError):
        return {"anonym_enforced": True}


def is_anonym_enforced(root: Path | None = None) -> bool:
    """Default: anonym an — AA_SPREAD_ANONYM=0 zum Deaktivieren."""
    env = os.environ.get("AA_SPREAD_ANONYM", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    if root is not None:
        return bool(load_policy(root).get("anonym_enforced", True))
    return True


def reddit_profile_block(root: Path) -> Dict[str, Any]:
    """Fail-closed wenn king_ops reddit-post / Firefox-Profil verboten."""
    return {
        "ok": False,
        "blocked": True,
        "anonym": True,
        "detail_de": (
            "Anonym-Policy aktiv — kein king_ops reddit-post / kein König-Firefox-Profil. "
            "Inkognito + evidence/reddit_post_body_ready.txt"
        ),
        "hint_de": "evidence/reddit_post_operator_anonym_de.txt",
        "policy_ref": _POLICY_REL.as_posix(),
    }


def redact_spread_urls(urls: Dict[str, Any]) -> Dict[str, Any]:
    """Öffentliche Evidence: nur HTTPS-Join, keine LAN/Home-Pfade."""
    if not urls:
        return {}
    out: Dict[str, Any] = {}
    remote = str(urls.get("remote_url") or "").strip().rstrip("/")
    if remote.startswith("https://"):
        out["remote_url"] = remote
        out["join_remote"] = f"{remote}/join"
    for key in ("lite_zip", "world_zip", "home_zip"):
        val = str(urls.get(key) or "").strip()
        if val:
            out[key] = Path(val).name
    return out


def redact_federation_export(fed: Dict[str, Any]) -> Dict[str, Any]:
    """Federation-Evidence ohne König-Hostname."""
    if not fed:
        return {}
    out = dict(fed)
    out.pop("king_hostname", None)
    hosts = [h for h in (out.get("hostnames") or []) if h]
    out["hostnames"] = hosts
    out["remote_compute_hosts"] = list(out.get("remote_compute_hosts") or [])
    return out


def scrub_public_text(text: str) -> str:
    text = _LAN_RE.sub("<lan-redacted>", text)
    text = _HOME_RE.sub("~/", text)
    return text


def redact_evidence_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Rekursiv LAN/Home aus Export-Dicts entfernen."""
    if not isinstance(doc, dict):
        return doc
    out: Dict[str, Any] = {}
    for key, val in doc.items():
        if key in {"join_lan", "lan_url", "primary_url", "king_hostname"}:
            continue
        if key == "urls" and isinstance(val, dict):
            out[key] = redact_spread_urls(val)
        elif key == "federation" and isinstance(val, dict):
            out[key] = redact_federation_export(val)
        elif isinstance(val, dict):
            out[key] = redact_evidence_doc(val)
        elif isinstance(val, str):
            if _LAN_RE.search(val) or _HOME_RE.search(val):
                if key.endswith("_path") or key.endswith("_ref"):
                    out[key] = val
                else:
                    out[key] = scrub_public_text(val)
            else:
                out[key] = val
        else:
            out[key] = val
    out["anonym"] = True
    return out
