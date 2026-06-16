#!/usr/bin/env python3
"""500-EUR pilot preflight — governance, EXE, market data, T212 live, learning."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.is_file():
    PY = Path(sys.executable)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(name: str, ok: bool, **extra: Any) -> Dict[str, Any]:
    return {"name": name, "pass": ok, **extra}


def verify_governance(root: Path) -> Dict[str, Any]:
    import yaml

    cfg_path = root / "promotion_gate_config.yaml"
    doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
    flags = {
        "auto_research_enabled": doc.get("auto_research_enabled"),
        "auto_promote_paper_enabled": doc.get("auto_promote_paper_enabled"),
        "auto_promote_signal_enabled": doc.get("auto_promote_signal_enabled"),
        "auto_execute_real_money_enabled": doc.get("auto_execute_real_money_enabled"),
    }
    bad = [k for k, v in flags.items() if v is not False]
    from execution.confirmed_live.p17_review_mode_guard import review_mode_active
    from execution.confirmed_live.p17_review_mode_preferences import apply_saved_review_mode_to_environment
    from execution.confirmed_live.pilot_live_trading_policy import is_pilot_live_trading_enabled

    apply_saved_review_mode_to_environment(root)
    review = review_mode_active()
    pilot_live = is_pilot_live_trading_enabled(root)
    safety_ok = review or pilot_live
    ok = not bad and safety_ok
    return _step(
        "governance",
        ok,
        flags=flags,
        p17_review_mode=review,
        pilot_live_trading=pilot_live,
        active_champion="R3_w075_q065_noexit",
        reason=None if ok else f"unsafe flags or neither review nor pilot live: {bad}",
    )


def verify_exe_integrity(root: Path) -> Dict[str, Any]:
    from aa_build_integrity import authenticode_status, verify_exe_hash_consistency

    exe = root / "Marktanalyse.exe"
    verify = verify_exe_hash_consistency(root=root)
    signing = authenticode_status(exe) if exe.is_file() else {"status": "exe_missing"}
    ok = bool(verify.get("ok")) and exe.is_file()
    return _step(
        "exe_integrity",
        ok,
        sha256=verify.get("actual_sha256"),
        hash_sidecar_match=verify.get("ok"),
        authenticode=signing,
        exe_exists=exe.is_file(),
    )


def verify_market_data(root: Path, *, force: bool) -> Dict[str, Any]:
    from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout
    from market.live_quote_engine import ensure_live_quotes_fresh

    ensure_marktanalyse_runtime_layout(root)
    try:
        snap = ensure_live_quotes_fresh(root, force=force, owner="king_ops")
        fresh = snap.get("freshness") or {}
        status = str(fresh.get("status") or "UNKNOWN")
        allowed = bool(fresh.get("calculation_allowed"))
        prices = snap.get("executable_prices_eur") or {}
        ok = allowed and len(prices) >= 4
        return _step(
            "market_data",
            ok,
            freshness_status=status,
            calculation_allowed=allowed,
            symbol_count=len(prices),
            reason=fresh.get("reason"),
        )
    except Exception as exc:
        return _step("market_data", False, error=str(exc)[:300])


def verify_t212_live(root: Path, *, force_sync: bool) -> Dict[str, Any]:
    from integrations.trading212.t212_credentials_loader import load_credentials
    from integrations.trading212.t212_readonly_connection_service import (
        connection_status_summary,
        sync_readonly_account,
    )

    creds = load_credentials()
    if not creds or not creds.configured:
        cached = connection_status_summary(root, force_sync=False)
        if cached.credentials_configured and cached.status.startswith("LIVE"):
            return _step(
                "t212_live",
                True,
                mode="cached_sync",
                status=cached.status,
                cash_eur=cached.cash_eur,
                positions_count=cached.positions_count,
                last_sync_utc=cached.last_successful_sync_utc,
                note="Credentials not in this process; using cached broker snapshot from prior GUI sync.",
            )
        return _step(
            "t212_live",
            False,
            mode="awaiting_user_setup",
            status="NOT_CONFIGURED",
            user_action=[
                "setup_t212_credentials.bat ausführen (empfohlen)",
                "Oder: .env mit TRADING212_API_KEY/SECRET füllen, dann run_persist_t212_credentials.bat",
                "Oder: Marktanalyse → Trading 212 → Sicher speichern aktivieren",
                "Danach: run_pilot_preflight.bat",
            ],
        )

    broker = sync_readonly_account(root) if force_sync else connection_status_summary(root, force_sync=True)
    ok = broker.status in (
        "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "DEMO_READONLY_CONNECTED",
        "CONNECTED_READONLY_OK",
    )
    return _step(
        "t212_live",
        ok,
        mode="live_sync",
        status=broker.status,
        cash_eur=broker.cash_eur,
        positions_count=broker.positions_count,
        last_sync_utc=broker.last_successful_sync_utc,
        last_error=broker.last_error,
    )


def verify_learning(root: Path) -> Dict[str, Any]:
    from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout
    from market.learning_pipeline import run_learning_capture_cycle

    ensure_marktanalyse_runtime_layout(root)
    out = run_learning_capture_cycle(root, live_snapshot=None, broker={}, cash={}, force_eod=True)
    readiness = out.get("readiness") or {}
    ok = bool(readiness.get("learning_collection_active")) and not readiness.get("capture_errors")
    return _step(
        "learning_capture",
        ok,
        learning_collection_active=readiness.get("learning_collection_active"),
        learning_healthy=readiness.get("learning_healthy"),
        capture_errors=readiness.get("capture_errors") or [],
        intraday_rows=readiness.get("intraday_observations"),
        eod_rows=readiness.get("eod_close_observations"),
    )


def verify_pilot_config(root: Path) -> Dict[str, Any]:
    cfg = root / "paper/config/p16c_cost_adjusted_initial_allocation_500eur.json"
    gap = root / "paper/config/pilot_gap_targets_eur.json"
    ok = cfg.is_file() and gap.is_file()
    capital = None
    if cfg.is_file():
        try:
            capital = json.loads(cfg.read_text(encoding="utf-8")).get("initial_capital_eur")
        except (json.JSONDecodeError, OSError):
            ok = False
    return _step(
        "pilot_500eur_config",
        ok and capital == 500.0,
        initial_capital_eur=capital,
        allocation_config=str(cfg.relative_to(root)).replace("\\", "/") if cfg.is_file() else None,
        gap_targets_config=str(gap.relative_to(root)).replace("\\", "/") if gap.is_file() else None,
    )


def verify_exe_matrix(root: Path, *, skip: bool) -> Dict[str, Any]:
    if skip:
        return _step("exe_function_matrix", True, skipped=True)
    proc = subprocess.run(
        [str(PY), str(root / "tools/run_exe_full_function_test.py")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=600,
    )
    report: Dict[str, Any] = {}
    try:
        doc = json.loads(proc.stdout or "{}")
        report = doc.get("exe_matrix", {}).get("report") or {}
    except json.JSONDecodeError:
        pass
    ok = proc.returncode == 0 and report.get("overall") == "PASS"
    return _step(
        "exe_function_matrix",
        ok,
        total=report.get("total"),
        passed=report.get("passed"),
        exit_code=proc.returncode,
    )


def verify_eod_task_registered() -> Dict[str, Any]:
    if sys.platform != "win32":
        return _step("learning_eod_task", True, skipped=True, reason="not_windows")
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", "Marktanalyse Learning EOD Catchup", "/FO", "LIST"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stdout or ""
    ok = proc.returncode == 0 and "Marktanalyse Learning EOD Catchup" in out
    return _step(
        "learning_eod_task",
        ok,
        task_name="Marktanalyse Learning EOD Catchup",
        scheduled_time_local="22:15",
        registered=proc.returncode == 0,
    )


def run_verification(
    root: Path,
    *,
    force_market: bool,
    force_t212: bool,
    skip_matrix: bool,
) -> Dict[str, Any]:
    steps = [
        verify_governance(root),
        verify_exe_integrity(root),
        verify_pilot_config(root),
        verify_market_data(root, force=force_market),
        verify_t212_live(root, force_sync=force_t212),
        verify_learning(root),
        verify_eod_task_registered(),
        verify_exe_matrix(root, skip=skip_matrix),
    ]
    blockers = [s["name"] for s in steps if not s["pass"]]
    t212 = next(s for s in steps if s["name"] == "t212_live")
    pilot_operational = all(s["pass"] for s in steps if s["name"] != "t212_live")
    return {
        "generated_at_utc": _utc_now(),
        "pilot_day1_ready": pilot_operational and t212["pass"],
        "pilot_operational_without_t212": pilot_operational,
        "overall_pass": not blockers,
        "blockers": blockers,
        "steps": steps,
        "next_actions": t212.get("user_action") or [],
    }


def write_evidence(root: Path, report: Dict[str, Any]) -> Path:
    out_dir = root / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = out_dir / f"pilot_live_verification_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest = out_dir / "pilot_live_verification_latest.json"
    latest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    p = argparse.ArgumentParser(description="500-EUR pilot live preflight")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--force-market", action="store_true", help="Force live quote refresh")
    p.add_argument("--force-t212", action="store_true", help="Force T212 account sync")
    p.add_argument("--skip-matrix", action="store_true", help="Skip EXE full-function matrix (~30s)")
    args = p.parse_args()
    root = Path(args.root)
    from integrations.trading212.t212_startup_bootstrap import bootstrap_trading212_credentials

    bootstrap_trading212_credentials(root)
    report = run_verification(
        root,
        force_market=args.force_market,
        force_t212=args.force_t212,
        skip_matrix=args.skip_matrix,
    )
    out = write_evidence(root, report)
    report["evidence_path"] = str(out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["pilot_day1_ready"]:
        return 0
    if report["pilot_operational_without_t212"]:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
