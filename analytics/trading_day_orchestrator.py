"""Trading-day orchestrator — one run, one story, one T212 sync."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_EVIDENCE_REL = Path("evidence/trading_day_orchestrator_latest.json")


def run_trading_day_orchestrator(
    root: Path,
    *,
    phase: str = "full",
    force: bool = False,
) -> Dict[str, Any]:
    """
    Phases:
      full      — daily-mark + snap + warnings + checklist + cockpit
      pre-us    — force quotes snap + cockpit
      us-open   — force quotes snap + cockpit
    """
    root = Path(root)
    phase = str(phase or "full").strip().lower()
    steps: List[Dict[str, Any]] = []
    out: Dict[str, Any] = {
        "schema_version": 1,
        "phase": phase,
        "ok": True,
        "skipped": False,
        "steps": steps,
    }

    from execution.linux_nvme_storage import apply_nvme_storage_env
    from execution.linux_security_boundary import apply_native_app_env

    apply_native_app_env(root)
    apply_nvme_storage_env(root)

    snap: Dict[str, Any] = {}
    checklist: Dict[str, Any] = {}

    try:
        if phase == "full":
            from analytics.live_trading_operations import run_daily_live_cycle

            cycle = run_daily_live_cycle(root, armed_auto=False, force_rebalance=False)
            steps.append({"step": "daily_mark", "ok": bool(cycle.get("ok", cycle.get("sync_ok")))})
            out["ok"] = steps[-1]["ok"]

            from ui.live_trading_dashboard.service import _refresh_snapshot_impl, write_dashboard_txt

            snap = _refresh_snapshot_impl(root, force_quotes=True, force_sync=False)
            write_dashboard_txt(root, snap)
            steps.append({"step": "snapshot", "ok": not snap.get("error")})

            from analytics.monday_ops_checklist import write_monday_checklist_to_activity_log

            checklist = write_monday_checklist_to_activity_log(root, source="AUTO")
            steps.append({"step": "checklist", "ok": bool(checklist.get("ok"))})
        else:
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl, write_dashboard_txt

            snap = _refresh_snapshot_impl(root, force_quotes=True, force_sync=False)
            write_dashboard_txt(root, snap)
            steps.append({"step": phase, "ok": not snap.get("error")})
            out["ok"] = steps[-1]["ok"]
    except Exception as exc:
        out["ok"] = False
        out["error"] = str(exc)[:300]
        steps.append({"step": "error", "ok": False, "detail": str(exc)[:200]})

    warnings: Dict[str, Any] = {}
    try:
        from analytics.pilot_trading_day_warnings import collect_trading_day_warnings

        warnings = collect_trading_day_warnings(root, snap=snap)
        steps.append({"step": "warnings", "ok": not warnings.get("must_resolve_before_trading")})
    except Exception as exc:
        warnings = {"error": str(exc)[:200]}
        steps.append({"step": "warnings", "ok": False})

    try:
        from analytics.h1_governance_status import sync_h1_governance_status

        sync_h1_governance_status(root)
        steps.append({"step": "h1_status", "ok": True})
    except Exception:
        steps.append({"step": "h1_status", "ok": False})

    return _finalize(root, out, snap=snap, warnings=warnings, checklist=checklist)


def _finalize(
    root: Path,
    out: Dict[str, Any],
    *,
    snap: Dict[str, Any],
    warnings: Dict[str, Any],
    checklist: Dict[str, Any],
) -> Dict[str, Any]:
    from analytics.trading_day_cockpit import build_trading_day_cockpit, write_trading_day_cockpit
    from analytics.snapshot_freshness import mark_snapshot_fresh

    cockpit = build_trading_day_cockpit(
        root,
        snap=snap,
        warnings=warnings,
        checklist=checklist,
        orchestrator_phase=str(out.get("phase") or "full"),
        steps=out.get("steps") or [],
    )
    cockpit["snap"] = snap
    cockpit["warnings_doc"] = warnings
    paths = write_trading_day_cockpit(root, cockpit)
    out["cockpit"] = {k: v for k, v in cockpit.items() if k != "snap"}
    out["cockpit_paths"] = paths
    out["next_step_de"] = cockpit.get("next_step_de")

    try:
        from analytics.operator_public_status import publish_public_status

        publish_public_status(root, notify=False)
    except Exception:
        pass

    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(
            root,
            level="B",
            action=f"trading_day_{out.get('phase')}",
            result=str(out.get("next_step_de") or "—")[:120],
        )
    except Exception:
        pass

    try:
        from ui.live_trading_dashboard.activity_log import log_dashboard_activity

        log_dashboard_activity(
            root,
            category="Active Alpha",
            action=f"Trading-Day ({out.get('phase')})",
            result=str(out.get("next_step_de") or "")[:240],
            status="ERFOLGREICH" if out.get("ok") else "FEHLGESCHLAGEN",
            source="AUTO",
            user_action_required=bool(warnings.get("must_resolve_before_trading")),
        )
    except Exception:
        pass

    mark_snapshot_fresh(root, source=f"orchestrator:{out.get('phase')}")
    path = root / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    out["cockpit"] = {k: v for k, v in cockpit.items() if k != "snap"}
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        from analytics.preview_freshness import mark_preview_inputs_changed

        mark_preview_inputs_changed(root, source=f"trading-day:{out.get('phase')}")
    except Exception:
        pass
    return out
