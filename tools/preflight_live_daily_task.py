#!/usr/bin/env python3
"""Preflight for scheduled live daily mark (Step B — enqueue only, no blind POST)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CHECKLIST_REL = Path("control/live_trading_daily_task_checklist.json")
EVIDENCE_REL = Path("evidence/live_trading_daily_task_preflight_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_checklist_doc(root: Path) -> Dict[str, Any]:
    path = Path(root) / CHECKLIST_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _check_venv(root: Path) -> Dict[str, Any]:
    from aa_paths import resolve_venv_python, venv_python_ok

    ok = venv_python_ok(root)
    py = resolve_venv_python(root) if ok else root / ".venv"
    return {
        "id": "venv_ready",
        "ok": ok,
        "detail_de": str(py) if ok else "Projekt-.venv fehlt — setup_linux_native.sh / setup_active_alpha_env.bat",
    }


def _check_project_root(root: Path) -> Dict[str, Any]:
    ok = (root / "active_alpha_model.py").is_file()
    return {
        "id": "project_root",
        "ok": ok,
        "detail_de": "Projektroot OK" if ok else "active_alpha_model.py fehlt",
    }


def _check_live_policy(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import policy_section

    pol = policy_section(root, "live_trading")
    ok = bool(pol.get("enabled", True))
    return {
        "id": "live_trading_enabled",
        "ok": ok,
        "detail_de": "live_trading.enabled=true" if ok else "live_trading deaktiviert in pilot_day_trading.json",
    }


def _check_rebalance_daily(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import policy_section

    pol = policy_section(root, "live_trading")
    every = int(pol.get("rebalance_every_trading_days") or 5)
    ok = every == 1
    return {
        "id": "rebalance_daily",
        "ok": ok,
        "detail_de": f"rebalance_every_trading_days={every}" + (" (OK)" if ok else " — erwartet 1 für daily_alpha_h1"),
    }


def _check_safety_no_auto_real_money(root: Path) -> Dict[str, Any]:
    path = root / "control/learning_collection_policy.json"
    ok = True
    detail = "Policy fehlt — Default sicher"
    if path.is_file():
        try:
            pol = json.loads(path.read_text(encoding="utf-8"))
            auto = bool(pol.get("auto_execute_real_money_enabled"))
            ok = not auto
            detail = f"auto_execute_real_money_enabled={auto}"
        except (json.JSONDecodeError, OSError):
            pass
    return {"id": "safety_no_auto_real_money", "ok": ok, "detail_de": detail}


def _check_safety_enqueue_only(*, scheduled: bool) -> Dict[str, Any]:
    ok = scheduled
    return {
        "id": "safety_enqueue_only",
        "ok": ok,
        "detail_de": (
            "AA_SCHEDULED_LIVE_TASK=1 — armed_auto=false, nur Vormerkung"
            if ok
            else "Nur über run_live_daily_mark_scheduled.bat (headless enqueue)"
        ),
    }


def _check_t212_readonly(root: Path) -> Dict[str, Any]:
    ok = False
    detail = "Keine Read-only Credentials"
    try:
        from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status
        from integrations.trading212.t212_windows_dpapi_credential_store import load_monitoring_credentials

        creds = load_monitoring_credentials(root)
        if creds and creds.configured:
            ok = True
            detail = "Read-only API (DPAPI) konfiguriert"
        else:
            import os

            if os.environ.get("TRADING212_API_KEY") and os.environ.get("TRADING212_API_SECRET"):
                ok = True
                detail = "Read-only API via Umgebungsvariablen"
            else:
                env_path = root / "trading212_zugangsdaten.env"
                if env_path.is_file():
                    ok = True
                    detail = "trading212_zugangsdaten.env vorhanden"
            cached = load_cached_broker_status(root)
            if cached and cached.credentials_configured and cached.cash_eur is not None:
                ok = True
                detail = "Broker-Cache mit Cash vorhanden"
    except Exception as exc:
        detail = str(exc)[:120]
    return {"id": "t212_readonly_credentials", "ok": ok, "detail_de": detail}


def _check_portfolio_csv(root: Path) -> Dict[str, Any]:
    path = root / "model_output_sp500_pit_t212/latest_target_portfolio.csv"
    ok = path.is_file() and path.stat().st_size > 0
    return {
        "id": "portfolio_csv",
        "ok": ok,
        "detail_de": str(path.relative_to(root)) if ok else "Portfolio-CSV fehlt — zuerst Signal (predict)",
    }


def _check_champion_guard(root: Path) -> Dict[str, Any]:
    from analytics.champion_runtime_guard import verify_champion_runtime

    st = verify_champion_runtime(root)
    ok = not st.hard_block
    return {
        "id": "champion_guard_ok",
        "ok": ok,
        "detail_de": st.status_de[:200],
        "blockers": list(st.blockers),
    }


def _check_signal_fresh(root: Path) -> Dict[str, Any]:
    from analytics.prediction_operations import evaluate_prediction_readiness_for_orders

    gate = evaluate_prediction_readiness_for_orders(root)
    price = gate.get("price_latest") or "—"
    return {
        "id": "signal_fresh",
        "ok": bool(gate.get("ok") or gate.get("skipped")),
        "detail_de": (
            gate.get("message_de", "")
            + f" · Preis {price}"
            + (
                f" · {', '.join(gate.get('blockers') or [])}"
                if gate.get("blockers")
                else ""
            )
        )[:240],
        "blockers": list(gate.get("blockers") or []),
    }


def _check_prediction_profile(root: Path) -> Dict[str, Any]:
    try:
        from analytics.prediction_operations import active_profile

        prof = active_profile(root)
        ok = prof == "daily_alpha_h1"
        return {
            "id": "prediction_profile",
            "ok": ok,
            "detail_de": f"active_profile={prof}",
        }
    except Exception as exc:
        return {"id": "prediction_profile", "ok": False, "detail_de": str(exc)[:120]}


def _check_ki_mode(root: Path) -> Dict[str, Any]:
    from execution.confirmed_live.trading_mode_policy import trading_readiness

    rd = trading_readiness(root)
    ok = bool(rd.get("ready"))
    checks = rd.get("checks") or []
    detail = " · ".join(f"{c.get('label')}: {'OK' if c.get('ok') else '—'}" for c in checks)
    return {
        "id": "ki_mode_ready",
        "ok": ok,
        "detail_de": detail or str(rd.get("mode")),
    }


def _check_live_outcome_bridge(root: Path) -> Dict[str, Any]:
    path = Path(root) / "evidence/live_execution_outcome_sync_latest.json"
    ok = path.is_file()
    detail = "Noch kein Sync — läuft nach Predict / Tages-Mark"
    if ok:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            detail = str(doc.get("message_de") or doc.get("generated_at_utc") or "OK")[:200]
            ok = bool(doc.get("ok", True))
        except (json.JSONDecodeError, OSError):
            pass
    return {"id": "live_outcome_bridge", "ok": ok, "detail_de": detail}


def evaluate_live_daily_task_preflight(
    root: Path,
    *,
    scheduled: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    doc = load_checklist_doc(root)
    required_ids = {
        str(i.get("id"))
        for i in (doc.get("items") or [])
        if i.get("required") is True and i.get("id")
    }

    checks = [
        _check_venv(root),
        _check_project_root(root),
        _check_live_policy(root),
        _check_rebalance_daily(root),
        _check_safety_no_auto_real_money(root),
        _check_safety_enqueue_only(scheduled=scheduled),
        _check_t212_readonly(root),
        _check_portfolio_csv(root),
        _check_champion_guard(root),
        _check_signal_fresh(root),
        _check_prediction_profile(root),
        _check_ki_mode(root),
        _check_live_outcome_bridge(root),
    ]
    by_id = {c["id"]: c for c in checks}

    blockers: List[str] = []
    warnings: List[str] = []
    items_out: List[Dict[str, Any]] = []

    for item in doc.get("items") or []:
        iid = str(item.get("id") or "")
        chk = by_id.get(iid) or {"id": iid, "ok": False, "detail_de": "Unbekannte Prüfung"}
        required = bool(item.get("required"))
        row = {
            "id": iid,
            "label": item.get("label"),
            "required": required,
            "ok": bool(chk.get("ok")),
            "detail_de": chk.get("detail_de", ""),
            "category": item.get("category"),
        }
        items_out.append(row)
        if not row["ok"]:
            msg = f"{iid}:{row['detail_de']}"
            if required or iid in required_ids:
                blockers.append(msg)
            else:
                warnings.append(msg)

    ok = len(blockers) == 0
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "ok": ok,
        "scheduled_enqueue_only": scheduled,
        "checklist_ref": str(CHECKLIST_REL),
        "items": items_out,
        "blockers": blockers,
        "warnings": warnings,
        "message_de": (
            "Checkliste OK — geplanter Mark-Lauf erlaubt."
            if ok
            else f"Checkliste blockiert ({len(blockers)} Pflichtpunkt(e))."
        ),
    }


def write_preflight_evidence(root: Path, report: Dict[str, Any]) -> Path:
    root = Path(root)
    out = root / EVIDENCE_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    txt = root / "evidence/live_trading_daily_task_preflight_latest.txt"
    try:
        from tools.live_daily_task_ui import format_preflight_report

        txt.write_text(format_preflight_report(report) + "\n", encoding="utf-8")
    except Exception:
        pass
    return out


def print_preflight_report(report: Dict[str, Any], *, human: bool = True, json_out: bool = False) -> None:
    if json_out:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    if human:
        from tools.live_daily_task_ui import format_preflight_report

        print(format_preflight_report(report))
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))


def record_scheduled_run(root: Path, *, exit_code: int, summary_de: str = "") -> None:
    from aa_safe_io import atomic_write_json

    payload = {
        "generated_at_utc": _utc_now(),
        "exit_code": int(exit_code),
        "mode": "daily_enqueue_only",
        "scheduled": True,
        "summary_de": summary_de[:500],
    }
    atomic_write_json(root / "evidence/live_trading_scheduled_run_latest.json", payload)


def enforce_or_exit(root: Path, *, scheduled: bool = True, human: bool = True) -> Dict[str, Any]:
    report = evaluate_live_daily_task_preflight(root, scheduled=scheduled)
    write_preflight_evidence(root, report)
    if not report.get("ok"):
        print_preflight_report(report, human=human, json_out=False)
        raise SystemExit(2)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Live daily task preflight checklist")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--scheduled", action="store_true", help="Assert enqueue-only scheduled mode")
    p.add_argument("--human", action="store_true", help="Readable report (default if not --json)")
    p.add_argument("--enforce", action="store_true", help="Exit 2 on blocker")
    p.add_argument("--json", dest="json_out", action="store_true", help="Machine-readable JSON only")
    args = p.parse_args(argv)
    report = evaluate_live_daily_task_preflight(args.root, scheduled=args.scheduled)
    write_preflight_evidence(args.root, report)
    print_preflight_report(report, human=not args.json_out, json_out=args.json_out)
    if args.enforce and not report.get("ok"):
        return 2
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
