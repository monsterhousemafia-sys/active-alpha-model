"""Cloud-Teacher-Orchestrierung — Gemini/Ollama, Stufe A, Evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/king_cloud_teacher_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_teacher_question_from_kpis(kpis: Dict[str, Any]) -> str:
    blockers = list(kpis.get("blockers") or [])
    phase_hint = "forschung_reif" if kpis.get("forschung_reif_ok") else "wachstum"
    if blockers:
        return (
            f"Active Alpha Stufe A — Phase {phase_hint}. "
            f"KPI-Blocker: {', '.join(blockers)}. "
            "Konkrete king_ops-Schritte auf Deutsch (keine Orders, nur Evidence-basiert)."
        )
    return (
        f"Active Alpha Stufe A — Phase {phase_hint}, alle KPIs grün. "
        "Nächster Forschungsschritt mit vollem T212-Guthaben (variable_free_cash) — king_ops-Befehle auf Deutsch."
    )


def run_cloud_teacher_consult(
    root: Path,
    question: str,
    *,
    mode: str = "kombi",
    source: str = "stufe_a",
    persist: bool = True,
) -> Dict[str, Any]:
    """fetch_cloud_tip + Evidence — Gemini wenn Key, sonst Ollama keyless."""
    root = Path(root)
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "message_de": "Teacher-Frage fehlt"}

    ctx = ""
    try:
        from analytics.king_evidence_rag import rag_context_for_prompt

        ctx = rag_context_for_prompt(root)
    except Exception:
        pass

    from analytics.r3_external_advisor import fetch_cloud_tip, resolve_primary_cloud_provider

    provider = resolve_primary_cloud_provider(root)
    out = fetch_cloud_tip(root, q, extra_context=ctx, mode=mode)
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": bool(out.get("ok")),
        "source": source,
        "provider": out.get("provider") or provider,
        "model": out.get("model"),
        "compute_boost": bool(out.get("compute_boost")),
        "task_tier": out.get("task_tier"),
        "question_de": q[:500],
        "tip_de": str(out.get("tip_de") or "")[:8000],
        "headline_de": str(out.get("headline_de") or out.get("message_de") or "")[:200],
        "advisory_only": True,
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def load_cloud_teacher_evidence(root: Path) -> Dict[str, Any]:
    path = Path(root) / _EVIDENCE_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def teacher_context_for_prompt(root: Path, *, max_chars: int = 1200) -> str:
    doc = load_cloud_teacher_evidence(root)
    tip = str(doc.get("tip_de") or "").strip()
    if not tip:
        return ""
    provider = doc.get("provider") or "cloud"
    return (
        f"Cloud-Teacher ({provider} · {doc.get('model') or '—'}):\n{tip[:max_chars]}\n"
    )
