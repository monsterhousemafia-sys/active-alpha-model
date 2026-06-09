#!/usr/bin/env python3
"""Integration smoke: dashboard snapshot, T212, pick, readiness — no live order submit."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(name: str, ok: bool, **extra) -> dict:
    return {"name": name, "pass": ok, **extra}


def run_integration_test(root: Path) -> dict:
    root = Path(root)
    from aa_pilot_launch import bootstrap_live_trading_runtime, run_preflight

    bootstrap_live_trading_runtime(root)
    steps: list[dict] = []

    try:
        pre = run_preflight(root)
        steps.append(
            _step(
                "pilot_preflight",
                bool(pre.get("live_trading_ready")),
                blockers=pre.get("blockers"),
                t212_connected=pre.get("t212_connected"),
            )
        )
    except Exception as exc:
        steps.append(_step("pilot_preflight", False, error=str(exc)[:300]))
        pre = {}

    try:
        from ui.live_trading_dashboard import service as dash

        snap = dash.refresh_snapshot(root, force_sync=True, timeout_s=120.0)
        broker = snap.get("broker") or {}
        pick = snap.get("today_pick") or {}
        cash_ok = broker.get("cash_eur") is not None and not broker.get("error")
        pick_ok = bool(pick.get("symbol"))
        steps.append(
            _step(
                "dashboard_snapshot",
                cash_ok and pick_ok,
                cash_eur=broker.get("cash_eur"),
                broker_error=broker.get("error"),
                broker_warning=broker.get("warning"),
                pick_symbol=pick.get("symbol"),
                pick_target_eur=pick.get("target_eur"),
                traffic=snap.get("traffic"),
            )
        )
    except Exception as exc:
        steps.append(_step("dashboard_snapshot", False, error=str(exc)[:300]))
        snap = {}

    try:
        from execution.confirmed_live.trading_mode_policy import (
            execution_credentials_ready,
            get_trading_mode,
            trading_readiness,
        )

        mode = get_trading_mode(root)
        rd = trading_readiness(root)
        exec_ok = execution_credentials_ready(root)
        order_ui_ready = (
            mode == "ai_assisted"
            and rd.get("ready")
            and exec_ok
            and bool((snap.get("today_pick") or {}).get("symbol"))
            and (snap.get("broker") or {}).get("cash_eur") is not None
        )
        steps.append(
            _step(
                "order_button_ready",
                order_ui_ready,
                mode=mode,
                readiness=rd,
                execution_credentials=exec_ok,
            )
        )
    except Exception as exc:
        steps.append(_step("order_button_ready", False, error=str(exc)[:300]))

    try:
        from analytics.live_trading_operations import rebalance_status

        st = rebalance_status(root)
        steps.append(
            _step(
                "rebalance_schedule",
                True,
                is_due=st.get("is_due"),
                recorded_days=st.get("recorded_trading_days_since_rebalance"),
                every=st.get("rebalance_every_trading_days"),
                summary_de=st.get("summary_de"),
            )
        )
    except Exception as exc:
        steps.append(_step("rebalance_schedule", False, error=str(exc)[:300]))

    try:
        from analytics.live_trading_operations import sync_broker_and_quotes

        sync = sync_broker_and_quotes(root, force_quotes=False, force_sync=True)
        b = sync.get("broker") or {}
        steps.append(
            _step(
                "t212_connect_action",
                b.get("cash_eur") is not None,
                cash_eur=b.get("cash_eur"),
                error=b.get("error"),
            )
        )
    except Exception as exc:
        steps.append(_step("t212_connect_action", False, error=str(exc)[:300]))

    blockers = [s["name"] for s in steps if not s["pass"]]
    report = {
        "generated_at_utc": _utc_now(),
        "overall_pass": len(blockers) == 0,
        "blockers": blockers,
        "steps": steps,
        "note_de": "Keine echte T212-Order gesendet — nur Lesen/Snapshot/Preflight.",
    }
    out = root / "evidence" / "live_dashboard_integration_test_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = run_integration_test(ROOT)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("overall_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
