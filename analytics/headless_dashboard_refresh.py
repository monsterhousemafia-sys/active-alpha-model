"""Headless dashboard refresh — broker, quotes, snapshot without Qt window."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

_CET = ZoneInfo("Europe/Berlin")
_EVIDENCE_REL = Path("evidence/headless_refresh_latest.json")


def in_trading_refresh_window(*, now: Optional[datetime] = None) -> bool:
    """Mo–Fr 14:00–22:00 CET — window for routine snapshot refresh."""
    dt = now or datetime.now(_CET)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_CET)
    else:
        dt = dt.astimezone(_CET)
    if dt.weekday() >= 5:
        return False
    minutes = dt.hour * 60 + dt.minute
    return 14 * 60 <= minutes <= 22 * 60


def _utc_now() -> str:
    from datetime import timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log_activity(root: Path, *, mode: str, result: str, status: str = "ERFOLGREICH") -> None:
    try:
        from ui.live_trading_dashboard.activity_log import log_dashboard_activity

        log_dashboard_activity(
            root,
            category="Auto-Refresh",
            action=f"Headless {mode}",
            result=result[:240],
            status=status,
            source="AUTO",
        )
    except Exception:
        pass


def _publish_status(root: Path) -> None:
    try:
        from analytics.operator_public_status import publish_public_status

        publish_public_status(root, notify=False)
    except Exception:
        pass


def run_headless_refresh(
    root: Path,
    *,
    mode: str = "snapshot",
    force: bool = False,
    skip_window_check: bool = False,
) -> Dict[str, Any]:
    """
    Modes:
      snapshot     — integrated refresh (Mo–Fr 14–22 unless skip_window_check)
      daily-mark   — T212 sync + daily mark + enqueue if due (no order execution)
      pre-us       — force quotes before US open
      us-open      — force quotes during US open burst
      boot         — one light refresh after reboot
    Orders are never submitted — auto_enqueue stays off for snapshot modes.
    """
    root = Path(root)
    mode = str(mode or "snapshot").strip().lower()
    out: Dict[str, Any] = {
        "schema_version": 1,
        "mode": mode,
        "generated_at_utc": _utc_now(),
        "ok": True,
        "skipped": False,
    }

    from execution.linux_nvme_storage import apply_nvme_storage_env
    from execution.linux_security_boundary import apply_native_app_env

    apply_native_app_env(root)
    apply_nvme_storage_env(root)

    from analytics.snapshot_freshness import mark_snapshot_fresh, should_skip_headless_refresh

    skip, reason = should_skip_headless_refresh(root, mode=mode, force=force)
    if skip:
        out["skipped"] = True
        out["reason_de"] = reason
        _write_evidence(root, out)
        return out

    if mode == "snapshot" and not skip_window_check and not in_trading_refresh_window():
        out["skipped"] = True
        out["reason_de"] = "Außerhalb Mo–Fr 14:00–22:00 CET"
        _write_evidence(root, out)
        return out

    force_quotes = force or mode in ("pre-us", "us-open", "boot")
    force_sync = force or mode in ("pre-us", "us-open")

    try:
        if mode == "daily-mark":
            from analytics.live_trading_operations import run_daily_live_cycle

            cycle = run_daily_live_cycle(root, armed_auto=False, force_rebalance=False)
            out["ok"] = bool(cycle.get("ok", cycle.get("sync_ok")))
            out["summary_de"] = str(cycle.get("summary_de") or cycle.get("message_de") or "")[:300]
            out["daily_mark"] = {
                "recorded": (cycle.get("daily_mark") or {}).get("recorded"),
                "rebalance_due": (cycle.get("rebalance_status") or {}).get("is_due"),
            }
            status = "ERFOLGREICH" if out["ok"] else "FEHLGESCHLAGEN"
            _log_activity(root, mode=mode, result=out.get("summary_de") or "daily-mark", status=status)
        else:
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl, write_dashboard_txt

            snap = _refresh_snapshot_impl(
                root,
                force_quotes=force_quotes,
                force_sync=force_sync,
            )
            write_dashboard_txt(root, snap)
            qc = snap.get("quote_coverage") or {}
            out["traffic"] = snap.get("traffic")
            out["summary_de"] = str(snap.get("today_action_de") or "")[:300]
            out["quote_coverage"] = {
                "ok": qc.get("ok"),
                "label_de": qc.get("quote_coverage_label_de"),
                "n_ok": qc.get("n_ok"),
                "n_total": qc.get("n_total"),
            }
            broker = snap.get("broker") or {}
            if broker.get("error"):
                out["ok"] = False
                out["broker_error"] = str(broker.get("error"))[:200]
            status = "ERFOLGREICH" if out["ok"] else "FEHLGESCHLAGEN"
            detail = out.get("summary_de") or str(out.get("quote_coverage"))
            _log_activity(root, mode=mode, result=detail, status=status)
    except Exception as exc:
        out["ok"] = False
        out["error"] = str(exc)[:300]
        _log_activity(root, mode=mode, result=str(exc)[:200], status="FEHLGESCHLAGEN")

    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(
            root,
            level="B",
            action=f"headless_refresh_{mode}",
            result="OK" if out["ok"] else "FAIL",
        )
    except Exception:
        pass

    _publish_status(root)
    if not out.get("skipped"):
        mark_snapshot_fresh(root, source=f"headless:{mode}")
    _write_evidence(root, out)
    if not out.get("skipped") and out.get("ok"):
        try:
            from analytics.preview_freshness import mark_preview_inputs_changed

            mark_preview_inputs_changed(root, source=f"refresh:{mode}")
        except Exception:
            pass
    return out


def _write_evidence(root: Path, doc: Dict[str, Any]) -> None:
    path = root / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
