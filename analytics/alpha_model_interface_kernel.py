"""Alpha Model interface stack — Runtime (KI lokal) vs. optionale Werkstatt."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_FOUNDATION_REL = Path("control/alpha_model_interface.json")
_POLICY_REL = Path("control/alpha_model_workshop_policy.json")
_EVIDENCE_REL = Path("evidence/alpha_model_interface_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_foundation(root: Path) -> Dict[str, Any]:
    path = Path(root) / _FOUNDATION_REL
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema_version": 2,
        "primary_interface": "r3_ki",
        "fallback_interface": "ollama_local",
        "primary_label_de": "Alpha Model KI — lokaler Hauptkanal",
    }


def load_workshop_policy(root: Path) -> Dict[str, Any]:
    path = Path(root) / _POLICY_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _workshop_session_active(root: Path | None = None) -> bool:
    try:
        from analytics.r3_kernel_roles import cursor_build_session_active, load_kernel_roles

        base = Path(root) if root else Path(__file__).resolve().parents[1]
        return cursor_build_session_active(load_kernel_roles(base))
    except Exception:
        return os.environ.get("AA_OPERATOR_CHANNEL", "").strip().lower() == "conversational"


def _ollama_ready(root: Path) -> Dict[str, Any]:
    try:
        from analytics.local_llm_bridge import health_report

        return health_report(root)
    except Exception as exc:
        return {"ready": False, "ollama_ok": False, "detail_de": str(exc)[:120]}


def interface_stack_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    foundation = load_foundation(root)
    policy = load_workshop_policy(root)
    ollama = _ollama_ready(root)
    workshop_active = _workshop_session_active(root)
    roles: Dict[str, Any] = {}
    try:
        from analytics.r3_kernel_roles import build_kernel_roles_status

        roles = build_kernel_roles_status(root)
    except Exception:
        pass

    try:
        from analytics.r3_conversation_continuity import continuity_status

        conversation_preserved = bool(continuity_status(root).get("preserved"))
    except Exception:
        conversation_preserved = False

    primary = str(foundation.get("primary_interface") or "r3_ki").strip()
    if primary in ("r3_ki", "ollama_local"):
        if ollama.get("ready"):
            active = "r3_ki" if primary == "r3_ki" else "ollama_local"
            headline = str(
                foundation.get("primary_label_de")
                or "Alpha Model KI lokal — Ollama / active-alpha-chat"
            )
            fallback_armed = True
        elif primary == "r3_ki":
            active = "r3_ki"
            headline = "Alpha Model KI — Ollama nicht bereit (python3 tools/ai_kernel.py llm-setup)"
            fallback_armed = False
        else:
            active = "degraded"
            headline = "Steuerung eingeschränkt — Ollama nicht bereit"
            fallback_armed = False
    elif ollama.get("ready"):
        active = "ollama_local"
        headline = "Alpha Model KI lokal — Ollama übernimmt Steuerung"
        fallback_armed = True
    elif workshop_active:
        active = "workshop"
        headline = str(
            foundation.get("workshop_label_de")
            or (roles.get("cursor") or {}).get("role_de")
            or "Alpha Model — Werkstatt (optional)"
        )
        fallback_armed = False
    else:
        active = "degraded"
        headline = "Steuerung eingeschränkt — Ollama nicht bereit"
        fallback_armed = False

    doc = {
        "schema_version": 2,
        "checked_at_utc": _utc_now(),
        "foundation": foundation,
        "workshop_policy": policy,
        "primary_interface": foundation.get("primary_interface", "r3_ki"),
        "fallback_interface": foundation.get("fallback_interface", "ollama_local"),
        "active_interface": active,
        "workshop_session_active": workshop_active,
        "workshop_label_de": foundation.get("workshop_label_de") or policy.get("workshop_label_de"),
        "ollama": ollama,
        "conversation_preserved": conversation_preserved,
        "r3_kernel_roles": roles,
        "headline_de": headline,
        "fallback_armed": fallback_armed,
        "model_home": policy.get("model_home") or "local_machine",
        "execution_mode": policy.get("execution_mode"),
        "multitask_mode": policy.get("multitask_mode"),
        "ok": active in ("r3_ki", "ollama_local"),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def should_use_ollama_fallback(root: Path) -> bool:
    foundation = load_foundation(root)
    primary = str(foundation.get("primary_interface") or "r3_ki").strip()
    if primary not in ("r3_ki", "ollama_local"):
        return False
    return bool(_ollama_ready(root).get("ready"))


def write_foundation_policy(root: Path) -> Dict[str, Any]:
    from analytics.r3_desktop_migration import write_local_primary_policy

    out = write_local_primary_policy(root)
    return dict(out.get("foundation") or {})
