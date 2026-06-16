"""Stufe B — operativer Preis-Cross-Check (Evidence + manueller Tick)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

from analytics.price_crosscheck import (
    evaluate_price_crosscheck,
    load_price_data_sources_policy,
    run_price_crosscheck,
)

_EVIDENCE_REL = Path("evidence/king_stufe_b_latest.json")
_STATE_REL = Path("control/king_stufe_b_state.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _parse_utc(raw: str):
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _cooldown_ok(root: Path, minutes: int) -> bool:
    state = _load_json(root / _STATE_REL)
    stamp = _parse_utc(str(state.get("last_tick_utc") or ""))
    if not stamp:
        return True
    age = (datetime.now(timezone.utc) - stamp).total_seconds() / 60.0
    return age >= float(minutes)


def run_stufe_b_tick(root: Path, *, force: bool = False, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = load_price_data_sources_policy(root)
    if not policy.get("enabled", True):
        return {"ok": True, "skipped": True, "headline_de": "Stufe B deaktiviert"}

    cd = int(policy.get("tick_cooldown_min") or 30)
    if not force and not _cooldown_ok(root, cd):
        cached = _load_json(root / _EVIDENCE_REL)
        if cached:
            return {**cached, "ok": True, "skipped": True, "reason_de": f"cooldown_{cd}m"}

    crosscheck = run_price_crosscheck(root, persist=True, fetch_reference=True)
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": crosscheck.get("headline_de") or "Stufe B — Preis-Cross-Check",
        "ok": bool(crosscheck.get("ok")),
        "verdict": crosscheck.get("verdict"),
        "block_signal_refresh": crosscheck.get("block_signal_refresh"),
        "crosscheck_ref": "evidence/price_crosscheck_latest.json",
        "spy_status": crosscheck.get("spy_status"),
        "reference_coverage_ratio": crosscheck.get("reference_coverage_ratio"),
        "counts": crosscheck.get("counts"),
        "messages_de": crosscheck.get("messages_de") or [],
        "blocks": crosscheck.get("blocks") or [],
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
        atomic_write_json(
            root / _STATE_REL,
            {"schema_version": 1, "last_tick_utc": _utc_now(), "last_verdict": doc.get("verdict")},
        )
    return doc
