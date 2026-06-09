"""Evidence-RAG für König 32B — kompakter Kontext statt 8k-Vollstopfen."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_POLICY_REL = Path("control/king_stufe_a_policy.json")
_EVIDENCE_REL = Path("evidence/king_evidence_rag_latest.json")

_EXTRACTORS: Dict[str, List[str]] = {
    "evidence/king_network_pulse_latest.json": [
        "phase",
        "beat",
        "handoff_to",
        "h1_status",
        "next_action_de",
        "headline_de",
    ],
    "evidence/r3_t212_prognosis_latest.json": [
        "ok",
        "signal_date",
        "investable_eur",
        "worthwhile_buy_count",
        "summary_de",
        "updated_at_utc",
    ],
    "evidence/pilot_investment_plan_latest.json": [
        "investable_eur",
        "executable",
        "signal_date",
        "positions",
        "updated_at_utc",
    ],
    "evidence/king_trading_assist_latest.json": [
        "summary_de",
        "follow_on_count",
        "worthwhile_buy_count",
        "headline_de",
    ],
    "evidence/daily_alpha_h1_evaluation_latest.json": [
        "status",
        "pass_full_seal",
        "metrics_strategy",
        "headline_de",
    ],
    "control/prediction_readiness.json": ["ok", "signal_date", "blockers", "h1_backtest_status"],
    "evidence/king_32b_forschung_latest.json": ["growth", "headline_de"],
    "evidence/king_cloud_teacher_latest.json": [
        "provider",
        "model",
        "compute_boost",
        "headline_de",
        "tip_de",
    ],
    "evidence/r3_daytrading_data_care_latest.json": [
        "ok",
        "steps_ok",
        "headline_de",
        "t212_trusted",
        "orders_allowed",
        "updated_at_utc",
    ],
    "evidence/r3_daily_postmortem_latest.json": [
        "bad_day",
        "portfolio_return_pct",
        "benchmark_return_pct",
        "delta_vs_benchmark_pct",
        "summary_de",
        "as_of_date",
    ],
    "evidence/pilot_portfolio_reevaluation_latest.json": [
        "status",
        "urgency",
        "trade_required",
        "summary_de",
        "worthwhile_buys",
    ],
    "evidence/t212_trust_latest.json": [
        "trusted",
        "orders_allowed",
        "reason_code",
        "message_de",
        "last_sync_utc",
    ],
    "evidence/public_learning_report_latest.json": [
        "quality_score",
        "headline_de",
        "live_metrics",
        "backtest_metrics",
    ],
}


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


def load_stufe_a_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {"enabled": True, "evidence_rag_max_chars": 4500, "evidence_rag_paths": list(_EXTRACTORS)}
    return doc


def _pick_fields(doc: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in keys:
        if k not in doc:
            continue
        v = doc[k]
        if isinstance(v, str) and len(v) > 240:
            out[k] = v[:240] + "…"
        else:
            out[k] = v
    return out


def build_evidence_rag(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = load_stufe_a_policy(root)
    paths = list(policy.get("evidence_rag_paths") or _EXTRACTORS.keys())
    max_chars = int(policy.get("evidence_rag_max_chars") or 4500)
    chunks: List[Dict[str, Any]] = []

    for rel in paths:
        rel_s = str(rel).replace("\\", "/")
        full = root / rel_s
        raw = _load_json(full)
        if not raw:
            continue
        keys = _EXTRACTORS.get(rel_s, list(raw.keys())[:8])
        slim = _pick_fields(raw, keys)
        if rel_s == "evidence/pilot_investment_plan_latest.json" and raw.get("allocations"):
            slim["top_allocations"] = [
                {"symbol": a.get("symbol"), "target_eur": a.get("target_eur")}
                for a in (raw.get("allocations") or [])[:6]
                if isinstance(a, dict)
            ]
        chunks.append({"path": rel_s, "fields": slim})

    text = json.dumps(chunks, ensure_ascii=False, separators=(",", ":"))
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "…truncated]"

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "chunk_count": len(chunks),
        "char_count": len(text),
        "chunks": chunks,
        "rag_text": text,
        "headline_de": f"Evidence-RAG — {len(chunks)} Quellen, {len(text)} Zeichen",
    }
    if persist:
        from aa_safe_io import atomic_write_json

        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def rag_context_for_prompt(root: Path) -> str:
    doc = _load_json(Path(root) / _EVIDENCE_REL)
    if doc.get("rag_text"):
        return f"Evidence-RAG (Stufe A):\n{doc['rag_text']}\n"
    fresh = build_evidence_rag(root, persist=True)
    return f"Evidence-RAG (Stufe A):\n{fresh.get('rag_text', '')}\n"
