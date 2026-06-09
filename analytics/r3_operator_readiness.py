"""R3 Operator-Readiness — Prozent/Kanäle/Score außerhalb /r3; Serienpfad zielt 100 %."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_operator_readiness_latest.json")
_DESKTOP_SURFACE_DE = "http://127.0.0.1:17890/desktop"


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


def _critical_ok(
    *,
    series: Dict[str, Any],
    checklist: Dict[str, Any],
    cycle: Dict[str, Any],
) -> bool:
    return bool(series.get("series_ready")) and bool(checklist.get("checklist_ok")) and bool(
        cycle.get("closed")
    )


def build_r3_operator_readiness(root: Path, *, persist: bool = False) -> Dict[str, Any]:
    """Aggregiert R3-Betriebsmetriken für Desktop/Operator — nicht für /r3-Anzeige."""
    root = Path(root)
    series = _load_json(root / "evidence/series_readiness_latest.json")
    checklist = _load_json(root / "evidence/r3_operational_checklist_latest.json")
    cycle = _load_json(root / "evidence/r3_trading_cycle_latest.json")
    growth = _load_json(root / "evidence/r3_local_growth_latest.json")
    flow = _load_json(root / "evidence/r3_flow_latest.json")
    score = _load_json(root / "evidence/r3_closed_loop_score_latest.json")

    critical = _critical_ok(series=series, checklist=checklist, cycle=cycle)
    operational_pct = 100 if critical else int(series.get("readiness_pct") or 0)

    ch_ok = int(flow.get("channels_ok") or 0)
    ch_total = int(flow.get("channels_total") or 0)
    fluidity = flow.get("fluidity_pct")

    headline = (
        "R3 betriebsbereit — 100 %"
        if critical
        else str(series.get("headline_de") or "R3 Betrieb prüfen")[:120]
    )

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "operational_pct": operational_pct,
        "operational_ok": critical,
        "series_readiness_pct": int(series.get("readiness_pct") or 0),
        "series_ready": bool(series.get("series_ready")),
        "growth_pct": int(growth.get("growth_pct") or 0),
        "checklist_ok": bool(checklist.get("checklist_ok")),
        "checklist_de": (
            f"{checklist.get('items_ok')}/{checklist.get('items_total')}"
            if checklist.get("items_total")
            else "—"
        ),
        "cycle_closed": bool(cycle.get("closed")),
        "cycle_pct": cycle.get("cycle_pct"),
        "fluidity_pct": fluidity,
        "channels_ok": ch_ok,
        "channels_total": ch_total,
        "channels_de": str(flow.get("message_de") or "—")[:160],
        "kreis_pct": int(score.get("pct") or 0),
        "kreis_de": str(score.get("headline_de") or "—")[:80],
        "infra_pct": int(fluidity) if fluidity is not None else None,
        "headline_de": headline,
        "surface_de": _DESKTOP_SURFACE_DE,
        "r3_mirror_policy_de": "Keine Prozent-Anzeige auf /r3 — nur Operator/Desktop",
        "evidence_ref": str(_EVIDENCE_REL).replace("\\", "/"),
        "next_de": "bash tools/king_ops.sh series-ready --repair",
    }

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def apply_operator_readiness_repair(root: Path) -> Dict[str, Any]:
    """Sichere Schritte bis R3-Serienpfad 100 % (keine Orders, kein Champion)."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    def _step(step_id: str, label_de: str, fn) -> None:
        try:
            result = fn()
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else bool(result)
            steps.append({"id": step_id, "label_de": label_de, "ok": ok, "detail": result})
        except Exception as exc:
            steps.append({"id": step_id, "label_de": label_de, "ok": False, "error_de": str(exc)[:120]})

    _step(
        "flow",
        "R3 Flow synchronisieren",
        lambda: __import__(
            "analytics.r3_flow_orchestrator", fromlist=["sync_r3_flow"]
        ).sync_r3_flow(root, source_node="operator_readiness", warm_cache=False, persist=True),
    )
    _step(
        "checklist",
        "R3 Checkliste",
        lambda: __import__(
            "analytics.r3_operational_checklist", fromlist=["scan_operational_checklist"]
        ).scan_operational_checklist(root, persist=True),
    )
    _step(
        "series",
        "Serienreife scannen",
        lambda: __import__(
            "analytics.series_readiness", fromlist=["scan_series_readiness"]
        ).scan_series_readiness(root, persist=True, force=True, fast=True),
    )

    doc = build_r3_operator_readiness(root, persist=True)
    ok_n = sum(1 for s in steps if s.get("ok"))
    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok_n == len(steps) and bool(doc.get("operational_ok")),
        "steps": steps,
        "steps_ok": ok_n,
        "steps_total": len(steps),
        "operational_pct": doc.get("operational_pct"),
        "operational_ok": doc.get("operational_ok"),
        "headline_de": doc.get("headline_de"),
        "evidence_ref": str(_EVIDENCE_REL).replace("\\", "/"),
    }


def sync_r3_operator_readiness(
    root: Path,
    *,
    persist: bool = True,
    repair: bool = False,
) -> Dict[str, Any]:
    if repair:
        apply_operator_readiness_repair(root)
        return build_r3_operator_readiness(root, persist=persist)
    return build_r3_operator_readiness(root, persist=persist)
