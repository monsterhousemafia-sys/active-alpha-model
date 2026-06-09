"""R3 Agent Growth — Wachstum durch Meilensteine; Ablehnung entwicklungshemmender Anfragen."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_agent_growth.json")
_EVIDENCE_REL = Path("evidence/r3_agent_growth_latest.json")

_PRODUCTIVE_HINTS = (
    "bau",
    "build",
    "implement",
    "fix",
    "test",
    "pytest",
    "h1",
    "seal",
    "pilot",
    "migration",
    "schritt",
    "preview",
    "cockpit",
    "r3",
    "ubuntu",
    "fusion",
    "aktien",
    "prognose",
    "trading-day",
    "status",
    "warnung",
    "order",
    "native app",
    "spotlight",
    "dock",
    "geheimnis",
    "/r3",
    "/bau",
    "/beitrag",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_growth_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {
        "refusal_rule_de": "Unproduktive Anfragen ablehnen.",
        "growth_priorities_de": [],
        "refuse_categories": [],
    }


def _has_operator_override(message: str, cfg: Dict[str, Any]) -> bool:
    low = str(message or "").lower()
    for phrase in cfg.get("operator_override_phrases_de") or []:
        if str(phrase).lower() in low:
            return True
    return False


def _looks_productive(message: str) -> bool:
    low = str(message or "").lower()
    if low.startswith("/"):
        return True
    return any(hint in low for hint in _PRODUCTIVE_HINTS)


def _next_step_de(root: Path) -> str:
    try:
        from analytics.r3_local_surface import collect_ki_next_steps

        return str(collect_ki_next_steps(root).get("next_step_de") or "").strip()
    except Exception:
        pass
    try:
        from analytics.r3_step_a import evaluate_step_a

        step = evaluate_step_a(root)
        if not step.get("step_a_ready_for_b"):
            for m in step.get("milestones") or []:
                if not m.get("done"):
                    return str(m.get("label_de") or "H1 sealen")
        elif step.get("step_b_released"):
            from analytics.r3_step_b import evaluate_step_b, is_phase_b_active

            bdoc = evaluate_step_b(root, persist=False)
            if is_phase_b_active(root):
                nxt = bdoc.get("step_b_next_de")
                if nxt:
                    return f"Phase B: {nxt}"
            ms = bdoc.get("milestones_de") or []
            if ms:
                return f"Phase B: {ms[0]}"
            return "Phase B — OS-Stack (H1 parallel)"
    except Exception:
        pass
    cfg = load_growth_config(root)
    priorities = cfg.get("growth_priorities_de") or []
    return str(priorities[0] if priorities else "H1 sealen")


def assess_request(root: Path, message: str) -> Dict[str, Any]:
    """True productive → weiter; refused → Antwort mit Redirect."""
    import os

    root = Path(root)
    raw = str(message or "").strip()
    cfg = load_growth_config(root)

    if os.environ.get("AA_AGENT_CHAMBER", "").strip().lower() in ("1", "true", "yes"):
        return {"productive": True, "refused": False, "entfaltungsraum": True}

    if not raw or raw.startswith("/"):
        return {"productive": True, "refused": False}

    if _has_operator_override(raw, cfg):
        return {
            "productive": True,
            "refused": False,
            "operator_override": True,
            "detail_de": "Operator-Override erkannt",
        }

    if _looks_productive(raw):
        return {"productive": True, "refused": False}

    low = raw.lower()
    for cat in cfg.get("refuse_categories") or []:
        if not isinstance(cat, dict):
            continue
        for pattern in cat.get("patterns") or []:
            pat = str(pattern).lower().strip()
            if not pat:
                continue
            matched = pat in low or bool(re.search(rf"\b{re.escape(pat)}\b", low))
            if not matched and " " in pat:
                a, b = pat.split(None, 1)
                matched = bool(re.search(rf"\b{re.escape(a)}\b.*\b{re.escape(b)}", low))
            if matched:
                return {
                    "productive": False,
                    "refused": True,
                    "category_id": cat.get("id"),
                    "category_de": cat.get("label_de"),
                    "reply_de": str(cat.get("reply_de") or cfg.get("refusal_rule_de")),
                }

    return {"productive": True, "refused": False}


def build_refusal_reply(root: Path, assessment: Dict[str, Any]) -> str:
    root = Path(root)
    cfg = load_growth_config(root)
    base = str(assessment.get("reply_de") or cfg.get("refusal_rule_de") or "Das lehne ich ab.")
    nxt = _next_step_de(root)
    lines = [base, ""]
    if nxt:
        lines.append(f"**Nächster produktiver Schritt:** {nxt}")
    lines.append("")
    lines.append("Wenn du bewusst abweichen willst: `Operator Override: <Grund>` schreiben.")
    return "\n".join(lines)


def growth_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_growth_config(root)
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "identity_de": cfg.get("identity_de"),
        "refusal_rule_de": cfg.get("refusal_rule_de"),
        "growth_priorities_de": cfg.get("growth_priorities_de") or [],
        "refuse_categories_n": len(cfg.get("refuse_categories") or []),
        "next_step_de": _next_step_de(root),
        "headline_de": "R3 wächst durch Meilensteine — unproduktive Anfragen werden abgelehnt",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def format_growth_status_de(root: Path) -> str:
    doc = growth_status(root)
    lines = [
        str(doc.get("headline_de") or ""),
        "",
        str(doc.get("identity_de") or ""),
        "",
        "**Prioritäten:**",
    ]
    for p in doc.get("growth_priorities_de") or []:
        lines.append(f"- {p}")
    lines.extend(["", f"**Nächster Schritt:** {doc.get('next_step_de') or '—'}", "", str(doc.get("refusal_rule_de") or "")])
    return "\n".join(lines)
