"""Unified trading-day cockpit — one story for R3 Cockpit und r3-show."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

_EVIDENCE_JSON = Path("evidence/trading_day_latest.json")
_EVIDENCE_TXT = Path("evidence/trading_day_latest.txt")
_HOME_TXT = Path(".local/share/r3-os/trading_day_latest.txt")


def _utc_now() -> str:
    from datetime import timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _local_date_de() -> str:
    return datetime.now(ZoneInfo("Europe/Berlin")).strftime("%A %d.%m.%Y")


def _next_user_step(snap: Dict[str, Any], warnings: Dict[str, Any]) -> str:
    crit = int(warnings.get("critical_count") or 0)
    st = snap.get("rebalance_status") or {}
    if crit > 0 and st.get("is_due"):
        return f"② Rebalance bestätigen — {crit} kritische Warnung(en) zuerst prüfen"
    if st.get("is_due"):
        return "② Rebalance — Order-Welle mit GUI bestätigen"
    if crit > 0:
        return f"Warnungen beheben ({crit} kritisch) — «Aktualisieren»"
    return "① Täglicher Markt erledigt — auf Rebalance-Zähler warten"


def build_trading_day_cockpit(
    root: Path,
    *,
    snap: Optional[Dict[str, Any]] = None,
    warnings: Optional[Dict[str, Any]] = None,
    checklist: Optional[Dict[str, Any]] = None,
    orchestrator_phase: str = "full",
    steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    snap = dict(snap or {})
    warnings = dict(warnings or {})
    checklist = dict(checklist or {})

    try:
        from analytics.h1_governance_status import load_h1_governance_status

        h1 = load_h1_governance_status(root)
    except Exception:
        h1 = {}

    learn: Dict[str, Any] = {}
    learn_path = root / "evidence/public_learning_report_latest.json"
    if learn_path.is_file():
        try:
            learn = json.loads(learn_path.read_text(encoding="utf-8"))
            if not isinstance(learn, dict):
                learn = {}
        except (json.JSONDecodeError, OSError):
            learn = {}

    evo = (learn.get("evolution") or {}) if learn else {}
    live = (learn.get("metrics") or {}).get("live") or {}
    mature = int(live.get("n_mature") or 0)
    stage = str(evo.get("stage_id") or "sportwagen")
    next_stage = str(evo.get("next_stage_id") or "sport_plus")
    min_fills = 3

    qc = snap.get("quote_coverage") or {}
    try:
        from analytics.closed_loop_score import build_closed_loop_score, format_circle_lines_de

        circle = build_closed_loop_score(root, snap=snap, warnings=warnings)
    except Exception:
        circle = {}

    doc: Dict[str, Any] = {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "date_de": _local_date_de(),
        "phase": "PRE_GO_LIVE",
        "orchestrator_phase": orchestrator_phase,
        "traffic": snap.get("traffic"),
        "next_step_de": _next_user_step(snap, warnings),
        "warnings": {
            "count": int(warnings.get("count") or 0),
            "critical_count": int(warnings.get("critical_count") or 0),
            "headline_de": warnings.get("headline_de"),
        },
        "quote_coverage_de": qc.get("quote_coverage_label_de") or "—",
        "rebalance_due": bool((snap.get("rebalance_status") or {}).get("is_due")),
        "h1": {
            "status": h1.get("status"),
            "progress_pct": h1.get("progress_pct"),
            "sealed": h1.get("sealed"),
            "banner_de": h1.get("banner_de"),
        },
        "evolution": {
            "stage_id": stage,
            "next_stage_id": next_stage,
            "live_fills_mature": mature,
            "fills_to_next": max(0, min_fills - mature),
        },
        "learning_message_de": learn.get("message_de") if learn else None,
        "checklist_items": checklist.get("items") or [],
        "steps": steps or [],
        "snap_summary_de": str(snap.get("today_action_de") or "")[:240],
        "circle_score": circle,
    }
    base_lines = format_cockpit_lines_de(doc)
    circle_lines = format_circle_lines_de(circle) if circle else []
    doc["circle_lines_de"] = circle_lines
    doc["cockpit_lines_de"] = circle_lines + ([""] if circle_lines else []) + base_lines
    return doc


def format_cockpit_lines_de(doc: Dict[str, Any]) -> List[str]:
    w = doc.get("warnings") or {}
    h1 = doc.get("h1") or {}
    evo = doc.get("evolution") or {}
    lines = [
        f"{doc.get('date_de')} · Phase: {doc.get('phase')}",
        f"├── Auto: refresh {'✓' if doc.get('steps') else '—'} · "
        f"Warnungen {w.get('critical_count', 0)}× kritisch · Kurse {doc.get('quote_coverage_de')}",
        f"├── Du: {doc.get('next_step_de')}",
        f"├── {h1.get('banner_de') or 'H1: —'}",
        f"└── Evolution: {evo.get('stage_id')} → {evo.get('next_stage_id')} "
        f"({evo.get('live_fills_mature', 0)}/{(evo.get('live_fills_mature', 0) + (evo.get('fills_to_next') or 0))} Fills)",
    ]
    return lines


def write_trading_day_cockpit(root: Path, doc: Dict[str, Any]) -> Dict[str, str]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(exist_ok=True)
    circle = doc.get("circle_score") or {}
    if circle:
        try:
            from analytics.closed_loop_score import write_closed_loop_score

            write_closed_loop_score(root, circle)
        except Exception:
            pass
    json_path = root / _EVIDENCE_JSON
    txt_path = root / _EVIDENCE_TXT
    lines = list(doc.get("cockpit_lines_de") or [])
    text = "\n".join(lines)
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    txt_path.write_text(text + "\n", encoding="utf-8")
    home = Path.home() / _HOME_TXT
    home.parent.mkdir(parents=True, exist_ok=True)
    home.write_text(text + "\n", encoding="utf-8")
    return {
        "json": str(json_path),
        "txt": str(txt_path),
        "home_txt": str(home),
    }


def load_trading_day_cockpit_doc(root: Path) -> Dict[str, Any]:
    """Load cockpit doc; tolerates legacy orchestrator wrapper in same path."""
    path = Path(root) / _EVIDENCE_JSON
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return {}
        nested = doc.get("cockpit")
        if isinstance(nested, dict) and nested.get("cockpit_lines_de"):
            return nested
        return doc
    except (json.JSONDecodeError, OSError):
        return {}


def load_trading_day_snap(root: Path, *, max_age_s: int = 1500) -> Optional[Dict[str, Any]]:
    """Reuse orchestrator snap if fresh enough (e.g. for warnings at 14:25)."""
    doc = load_trading_day_cockpit_doc(root)
    if not doc:
        return None
    try:
        at = doc.get("generated_at_utc")
        if not at:
            return None
        from datetime import timezone

        ts = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > float(max_age_s):
            return None
        embedded = doc.get("snap")
        return embedded if isinstance(embedded, dict) else None
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None
