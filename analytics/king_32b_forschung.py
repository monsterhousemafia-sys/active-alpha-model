"""König 32B — Bestandteil des Forschungsprojekts; wächst mit Evidence und /learn."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/king_32b_forschungsprojekt.json")
_EVIDENCE_REL = Path("evidence/king_32b_forschung_latest.json")
_FORSCHUNG_BRANCH = "forschungszweig_finanzierung"

FORSCHUNG_COMPONENT_ID = "king_32b_forschung"
FORSCHUNG_MODEL_DEFAULT = "qwen2.5-coder:32b"

FORSCHUNG_SYSTEM_IDENTITY_DE = (
    "Du bist König (qwen2.5-coder:32b) — Bestandteil des Forschungsprojekts Active Alpha. "
    "Du wächst mit dem Projekt: Evidence lesen, Gas/Sell unterstützen, /learn und H1 respektieren. "
    "Kein Champion-Wechsel, keine Auto-Orders — Forschung + Operator-Bestätigung."
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


def load_forschungsprojekt_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "component_id": FORSCHUNG_COMPONENT_ID,
            "model": FORSCHUNG_MODEL_DEFAULT,
            "headline_de": "König 32B — Forschungsprojekt",
        }
    return doc


def is_forschungsprojekt_component(component_id: str) -> bool:
    return str(component_id or "").strip() in {
        FORSCHUNG_COMPONENT_ID,
        "king_32b",
        "alpha-model-agent",
        "trading_local",
    }


def resolve_growth_phase(root: Path) -> Dict[str, Any]:
    """KEIM → SPROSS → WACHSTUM → FORSCHUNG_REIF."""
    root = Path(root)
    policy = load_forschungsprojekt_policy(root)
    phases = dict(policy.get("growth_phases_de") or {})

    ollama_ok = False
    model = str(policy.get("model") or FORSCHUNG_MODEL_DEFAULT)
    try:
        from analytics.local_llm_bridge import load_llm_config, ollama_available

        cfg = load_llm_config(root)
        base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
        ollama_ok = ollama_available(base, timeout_s=3.0)
        model = str((cfg.get("role_models") or {}).get("trading_local") or cfg.get("default_model") or model)
    except Exception:
        pass

    king = _load_json(root / "evidence/king_trading_assist_latest.json")
    learn = _load_json(root / "evidence/public_learning_report_latest.json")
    gas = _load_json(root / "evidence/gas_sell_steering_latest.json")
    readiness = _load_json(root / "control/prediction_readiness.json")

    has_decisions = bool(king.get("trade_decisions"))
    learn_ok = bool(learn.get("ok") or learn.get("updated_at_utc"))
    gas_ok = bool(gas.get("on_course") or gas.get("gas_count"))

    stufe_a = _load_json(root / "evidence/king_stufe_a_latest.json")
    kpi_phase = (stufe_a.get("growth_phase") or "").strip()
    if kpi_phase in ("keim", "spross", "wachstum", "forschung_reif"):
        phase = kpi_phase
    elif ollama_ok and has_decisions and learn_ok and readiness.get("ok"):
        phase = "forschung_reif"
    elif ollama_ok and has_decisions and (gas_ok or readiness.get("ok")):
        phase = "wachstum"
    elif ollama_ok:
        phase = "spross"
    else:
        phase = "keim"

    next_growth: List[str] = []
    if phase == "keim":
        next_growth = ["bash tools/setup_ideal_32b.sh", "python3 tools/ai_kernel.py kernel-bond"]
    elif phase == "spross":
        next_growth = ["python3 tools/ai_kernel.py king-trading --force", "bash tools/king_ops.sh alpha-engine"]
    elif phase == "wachstum":
        next_growth = ["python3 tools/ai_kernel.py learn", "/beitrag forschung <Idee>"]
    else:
        next_growth = ["python3 tools/ai_kernel.py evolve", "H1-Seal prüfen"]

    return {
        "phase": phase,
        "phase_de": phases.get(phase) or phase,
        "model": model,
        "ollama_ok": ollama_ok,
        "next_growth_de": next_growth,
        "growth_identity_de": policy.get("growth_identity_de"),
        "wants_to_grow_de": "32B ist Forschungs-Bestandteil — wächst mit Learn, H1 und Gas/Sell-Evidence.",
    }


def build_king_32b_forschung_status(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = load_forschungsprojekt_policy(root)
    growth = resolve_growth_phase(root)
    fz = _load_json(root / "control/r3_forschungszweig.json")

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "component_id": policy.get("component_id") or FORSCHUNG_COMPONENT_ID,
        "is_forschungsprojekt": True,
        "forschungszweig_branch_id": policy.get("forschungszweig_branch_id") or _FORSCHUNG_BRANCH,
        "model": growth.get("model"),
        "agent_cli": policy.get("agent_cli") or "alpha-model-agent",
        "headline_de": policy.get("headline_de"),
        "mission_de": policy.get("mission_de"),
        "growth": growth,
        "roles_de": policy.get("roles_in_forschung_de"),
        "growth_commands_de": policy.get("growth_commands_de"),
        "forschungszweig_title_de": fz.get("title_de"),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def load_king_32b_forschung(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _EVIDENCE_REL)
    if doc:
        return doc
    return build_king_32b_forschung_status(root, persist=False)


def forschung_context_for_prompt(root: Path) -> str:
    """Kompakter Forschungs-Kontext für 32B-System-Prompts (Stufe A + Evidence-RAG)."""
    st = load_king_32b_forschung(root)
    g = st.get("growth") or {}
    rag = ""
    try:
        from analytics.king_evidence_rag import rag_context_for_prompt

        rag = rag_context_for_prompt(root)[:2000]
    except Exception:
        pass
    kpi = st.get("stufe_a_kpis") or {}
    if not kpi:
        stufe_ev = _load_json(root / "evidence/king_stufe_a_latest.json")
        kpi = stufe_ev.get("kpis") or {}
        if stufe_ev.get("growth_phase") and g.get("phase") != stufe_ev.get("growth_phase"):
            g = {**g, "phase": stufe_ev.get("growth_phase")}
    kpi_line = ""
    if kpi:
        kpi_line = f"KPIs: wachstum={kpi.get('wachstum_ok')} reif={kpi.get('forschung_reif_ok')} blockers={kpi.get('blockers')}\n"
    base = (
        f"{FORSCHUNG_SYSTEM_IDENTITY_DE}\n"
        f"Phase: {g.get('phase')} — {g.get('phase_de')}\n"
        f"{kpi_line}"
        f"Nächstes Wachstum: {', '.join(g.get('next_growth_de') or [])}\n"
    )
    teacher_ctx = ""
    try:
        from analytics.cloud_teacher_orchestrator import teacher_context_for_prompt

        teacher_ctx = teacher_context_for_prompt(root, max_chars=1000)
    except Exception:
        pass
    if teacher_ctx:
        base += teacher_ctx
    if rag:
        return (base + rag)[:4500]
    return base[:800]
