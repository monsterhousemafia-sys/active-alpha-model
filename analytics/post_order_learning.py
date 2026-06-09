"""Post-order learning hook — outcome sync + mini learn after GUI orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_EVIDENCE_REL = Path("evidence/post_order_learning_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_post_order_learning(root: Path) -> Dict[str, Any]:
    """Sync live fills, capture, light audit — no auto-trading."""
    root = Path(root)
    out: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "ok": True,
        "steps": [],
    }

    from execution.linux_security_boundary import apply_native_app_env

    apply_native_app_env(root)

    try:
        from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

        sync = sync_live_execution_outcomes(root, refresh_history=False)
        out["outcome_sync"] = sync
        out["steps"].append({"step": "outcome_sync", "ok": bool(sync.get("ok"))})
    except Exception as exc:
        out["outcome_sync"] = {"ok": False, "error": str(exc)[:200]}
        out["steps"].append({"step": "outcome_sync", "ok": False})
        out["ok"] = False

    try:
        from analytics.public_learning_kernel import run_capture_only

        cap = run_capture_only(root)
        out["capture"] = {"learning_healthy": (cap.get("readiness") or {}).get("learning_healthy")}
        out["steps"].append({"step": "capture", "ok": True})
    except Exception as exc:
        out["capture"] = {"error": str(exc)[:200]}
        out["steps"].append({"step": "capture", "ok": False})

    try:
        from analytics.learning_cycle_audit import run_learning_cycle_audit

        audit = run_learning_cycle_audit(root)
        out["audit"] = {"ok": audit.get("ok"), "live_n_mature": (audit.get("live_metrics") or {}).get("n_mature")}
        out["steps"].append({"step": "audit", "ok": bool(audit.get("ok"))})
    except Exception as exc:
        out["audit"] = {"error": str(exc)[:200]}
        out["steps"].append({"step": "audit", "ok": False})

    try:
        from analytics.headless_dashboard_refresh import run_headless_refresh

        refresh = run_headless_refresh(root, mode="snapshot", skip_window_check=True, force=True)
        out["refresh"] = {"ok": refresh.get("ok"), "traffic": refresh.get("traffic")}
        out["steps"].append({"step": "refresh", "ok": bool(refresh.get("ok"))})
    except Exception as exc:
        out["steps"].append({"step": "refresh", "ok": False, "error": str(exc)[:120]})

    try:
        from analytics.trading_day_cockpit import build_trading_day_cockpit, write_trading_day_cockpit
        from analytics.pilot_trading_day_warnings import collect_trading_day_warnings
        from ui.live_trading_dashboard.service import _refresh_snapshot_impl

        snap = _refresh_snapshot_impl(root, force_quotes=False, force_sync=False)
        warnings = collect_trading_day_warnings(root, snap=snap)
        cockpit = build_trading_day_cockpit(root, snap=snap, warnings=warnings, orchestrator_phase="post-order")
        write_trading_day_cockpit(root, cockpit)
        out["next_step_de"] = cockpit.get("next_step_de")
    except Exception:
        pass

    try:
        from ui.live_trading_dashboard.activity_log import log_dashboard_activity

        mature = (out.get("audit") or {}).get("live_n_mature")
        log_dashboard_activity(
            root,
            category="Lernen",
            action="Post-Order Learn",
            result=f"Fills sync — reif: {mature if mature is not None else '—'}",
            status="ERFOLGREICH" if out.get("ok") else "INFO",
            source="AUTO",
        )
    except Exception:
        pass

    path = root / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
