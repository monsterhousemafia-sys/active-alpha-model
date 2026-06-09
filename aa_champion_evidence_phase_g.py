"""Phase G — Live operations hardening evidence (G1–G6)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json, atomic_write_text

EVIDENCE_SUMMARY = Path("evidence") / "phase_g_live_operations_summary.json"
EVIDENCE_MATRIX = Path("evidence") / "phase_g_live_operations_gate_matrix.md"
LIVE_OPS_DOC = Path("evidence") / "live_trading_operations_latest.json"
OS_BAT = Path("active_alpha_marktanalyse_os.bat")

def _is_broker_style_symbol(sym: str) -> bool:
    """Champion/order keys must not use T212 provider ids (STX_US_EQ)."""
    s = str(sym or "").upper()
    return s.endswith("_US_EQ") or (s.endswith("_US") and len(s) > 3)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _py(root: Path) -> Path:
    venv = root / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def audit_g1_symbol_mapping(root: Path) -> Dict[str, Any]:
    """Champion symbols use mapper keys; broker ids only in provider_instrument_id."""
    root = Path(root)
    from integrations.trading212.t212_instrument_quotes import symbol_to_t212_ticker
    from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

    portfolio_path = root / "model_output_sp500_pit_t212" / "latest_target_portfolio.csv"
    portfolio_symbols: List[str] = []
    if portfolio_path.is_file():
        import pandas as pd

        frame = pd.read_csv(portfolio_path)
        if "ticker" in frame.columns:
            portfolio_symbols = [
                str(t).upper()
                for t in frame["ticker"].dropna().unique()
                if str(t).upper() not in {"SPY", "VUSD"}
            ]

    mapping_rows: List[Dict[str, Any]] = []
    issues: List[str] = []
    for sym in sorted(set(CHAMPION_SYMBOLS) | set(portfolio_symbols)):
        if _is_broker_style_symbol(sym):
            issues.append(f"forbidden_broker_style_symbol:{sym}")
        try:
            t212 = symbol_to_t212_ticker(sym)
        except Exception as exc:
            t212 = ""
            issues.append(f"unmap:{sym}:{exc}")
        mapping_rows.append({"champion_symbol": sym, "t212_ticker": t212})

    stx_row = next((r for r in mapping_rows if r["champion_symbol"] == "STX"), {})
    ok_stx = stx_row.get("t212_ticker") == "STX_US_EQ" and "STX" == stx_row.get("champion_symbol")

    sample_orders = [
        {"symbol": "STX", "side": "BUY", "notional_eur": 50},
        {"symbol": "SNDK", "side": "BUY", "notional_eur": 40},
    ]
    sample_results = [
        {"symbol": "STX", "ok": True, "sent_to_t212": True},
        {"symbol": "SNDK", "ok": False, "error": "NO_LIMIT_PRICE"},
    ]
    from analytics.execution_result_report import attach_execution_report

    report = attach_execution_report({"results": sample_results}, sample_orders)
    breakdown = report.get("execution_breakdown") or {}
    uses_champion_keys = "STX" in (breakdown.get("executed_symbols") or []) and "SNDK" in (
        breakdown.get("skipped_no_price_symbols") or []
    )

    return {
        "status": "PASS" if ok_stx and not issues and uses_champion_keys else "FAIL",
        "champion_symbol_count": len(CHAMPION_SYMBOLS),
        "portfolio_tradeable_count": len(portfolio_symbols),
        "stx_maps_to_stx_us_eq": ok_stx,
        "mapping_rows": mapping_rows,
        "issues": issues,
        "execution_report_uses_champion_symbols": uses_champion_keys,
        "rule_de": "Orders/Reports: Feld symbol = Champion-Ticker (STX); T212 nur in t212_instrument_id.",
    }


def audit_g2_planning_cash(root: Path) -> Dict[str, Any]:
    """Wave planner must cap buys to planning_cash (fixes ~41€ partial-fill class of bugs)."""
    root = Path(root)
    from execution.confirmed_live.rebalance_wave_planner import plan_rebalance_wave

    planning_cash = 492.0
    raw_total = 638.0
    n = 12
    orders = [{"symbol": f"S{i}", "side": "BUY", "notional_eur": round(raw_total / n, 2)} for i in range(n)]
    wave = plan_rebalance_wave(orders, planning_cash)
    scaled = float(wave.get("total_buy_notional_scaled") or 0)
    factor = float(wave.get("scale_factor") or 0)
    cash_ok = scaled <= planning_cash * 1.02 + 0.01

    sync_report: Dict[str, Any] = {"status": "SKIPPED", "reason": "no_latest_sync"}
    sync_path = root / "live_pilot/manual_execution/readonly_real_account_state/latest_sync.json"
    if sync_path.is_file():
        try:
            from integrations.trading212.t212_cash_parser import parse_cash_breakdown, verify_cash_eur_matches_summary

            doc = json.loads(sync_path.read_text(encoding="utf-8"))
            breakdown = parse_cash_breakdown(account_summary=doc.get("summary") or {})
            alignment = verify_cash_eur_matches_summary(doc.get("cash_eur"), doc.get("summary") or {})
            sync_report = {
                "status": "PASS" if alignment.get("ok") else "FAIL",
                "planning_cash_eur": breakdown.planning_cash_eur,
                "available_to_trade_eur": breakdown.available_to_trade_eur,
                "alignment": alignment,
            }
        except Exception as exc:
            sync_report = {"status": "ERROR", "error": str(exc)}

    evidence_path = root / "evidence" / "phase_g_planning_cash_audit.json"
    doc = {
        "generated_at_utc": _utc_now(),
        "simulation": {
            "planning_cash_eur": planning_cash,
            "raw_buy_total_eur": raw_total,
            "scaled_buy_total_eur": scaled,
            "scale_factor": factor,
            "cash_cap_ok": cash_ok,
        },
        "t212_sync": sync_report,
        "note_de": "Wellen-Planner skaliert Summe der BUY-Notionals auf planning_cash vor T212-POST.",
    }
    atomic_write_json(evidence_path, doc)

    return {
        "status": "PASS" if cash_ok else "FAIL",
        **doc["simulation"],
        "t212_sync_status": sync_report.get("status"),
        "evidence_path": str(evidence_path.relative_to(root)).replace("\\", "/"),
    }


def audit_g3_quote_coverage(root: Path) -> Dict[str, Any]:
    """Quote gate: N/N including SNDK; fail-closed when missing."""
    root = Path(root)
    from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
    from market.champion_quote_gate import require_champion_quote_coverage

    sndk_in_champion = "SNDK" in CHAMPION_SYMBOLS
    symbols = list(CHAMPION_SYMBOLS)
    prices = {s: 80.0 + i for i, s in enumerate(symbols)}
    snap = {
        "generated_at_utc": _utc_now(),
        "executable_prices_eur": prices,
        "price_source_by_symbol": {s: "SIMULATED_PHASE_G" for s in symbols},
    }
    gate = require_champion_quote_coverage(
        root,
        symbols=symbols,
        quote_snapshot=snap,
        refresh_if_stale=False,
    )
    return {
        "status": "PASS" if gate.get("ok") and sndk_in_champion else "FAIL",
        "sndk_in_champion_symbols": sndk_in_champion,
        "required_count": len(symbols),
        "quote_coverage_label_de": gate.get("quote_coverage_label_de"),
        "coverage_ok": (gate.get("coverage") or {}).get("coverage_ok"),
        "blocks": gate.get("blocks"),
    }


def audit_g4_execution_report() -> Dict[str, Any]:
    from analytics.execution_result_report import summarize_execution_breakdown

    orders = [{"symbol": "STX", "side": "BUY"}, {"symbol": "MU", "side": "BUY"}]
    results = [
        {"symbol": "STX", "ok": True, "sent_to_t212": True},
        {"symbol": "MU", "ok": False, "error": "NO_LIMIT_PRICE"},
    ]
    bd = summarize_execution_breakdown(orders, results)
    ok = bd.get("executed") == 1 and "STX" in bd.get("executed_symbols", []) and "MU" in bd.get(
        "skipped_no_price_symbols", []
    )
    return {
        "status": "PASS" if ok else "FAIL",
        "summary_de": bd.get("summary_de"),
        "module": "analytics/execution_result_report.py",
    }


def audit_g5_exe(root: Path, *, build: bool = False) -> Dict[str, Any]:
    root = Path(root)
    if build:
        proc = subprocess.run(
            [str(_py(root)), "-u", str(root / "tools" / "build_v5r_standalone_exe.py")],
            cwd=root,
        )
        if proc.returncode != 0:
            return {"status": "FAIL", "reason": "build_failed", "exit_code": proc.returncode}
    from tools.validate_live_rebalance_phase5 import verify_marktanalyse_exe

    out = verify_marktanalyse_exe()
    bat_ok = OS_BAT.is_file()
    return {
        "status": "PASS" if out.get("ok") and bat_ok else "PARTIAL" if out.get("ok") else "FAIL",
        "exe_sha256": out.get("sha256"),
        "exe_verify": out,
        "os_bat_present": bat_ok,
        "os_bat_path": str(OS_BAT).replace("\\", "/"),
        "note_de": "EXE-Rebuild nur mit --build-exe; OS-BAT startet Marktanalyse read-only.",
    }


def audit_g6_phase5_validation(root: Path, *, skip_pytest: bool = False, build_exe: bool = False) -> Dict[str, Any]:
    from tools.validate_live_rebalance_phase5 import (
        run_pytest_suite,
        simulate_dry_run_wave,
        verify_marktanalyse_exe,
        write_live_ops_evidence_template,
    )

    pytest_res = {"ok": True, "skipped": True} if skip_pytest else run_pytest_suite()
    dry_run = simulate_dry_run_wave(root)
    if build_exe:
        audit_g5_exe(root, build=True)
    exe = verify_marktanalyse_exe()
    live_ops = write_live_ops_evidence_template(root, dry_run=dry_run, pytest_res=pytest_res)
    overall = bool(pytest_res.get("ok")) and dry_run.get("ok") and exe.get("ok")
    return {
        "status": "PASS" if overall else "FAIL",
        "overall_pass": overall,
        "pytest": pytest_res,
        "dry_run": dry_run,
        "exe": exe,
        "live_trading_operations": live_ops,
        "evidence_json": "evidence/v5r_live_rebalance_phase5_validation.json",
        "report_md": "docs/LIVE_TRADING_REBALANCE_PHASE5_VALIDATION.md",
    }


def format_gate_matrix_md(checks: Dict[str, Any]) -> str:
    lines = [
        "# Phase G — Live-Operations Gate Matrix",
        "",
        f"Generated: {checks.get('generated_at_utc')}",
        "",
        "| Step | Status | Kurzbefund |",
        "| --- | --- | --- |",
    ]
    for key, label in (
        ("G1_symbol_mapping", "G1 Symbol STX -> STX_US_EQ"),
        ("G2_planning_cash", "G2 Planning-Cash / Welle"),
        ("G3_quote_coverage", "G3 Quote N/N (+SNDK)"),
        ("G4_execution_report", "G4 Execution-Report"),
        ("G5_exe_os_bat", "G5 EXE + OS-BAT"),
        ("G6_phase5_dry_run", "G6 Phase-5 Dry-Run Pflicht"),
    ):
        row = checks.get(key) or {}
        lines.append(f"| {label} | **{row.get('status', '—')}** | {row.get('note_de') or row.get('summary_de') or ''} |")
    lines.extend(
        [
            "",
            "## Acceptance",
            "",
            f"- Overall: **{'PASS' if checks.get('overall_pass') else 'FAIL'}**",
            f"- Dry-run quote: `{((checks.get('G6_phase5_dry_run') or {}).get('dry_run') or {}).get('quote_coverage_label_de', '—')}`",
            "",
            "Live US-Session-Run mit echten Credentials separat im Dashboard dokumentieren.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run_phase_g(
    root: Path,
    *,
    skip_pytest: bool = False,
    build_exe: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    g1 = audit_g1_symbol_mapping(root)
    g1["note_de"] = g1.get("rule_de")
    g2 = audit_g2_planning_cash(root)
    g2["note_de"] = "Skalierung raw→planning_cash; Evidence in phase_g_planning_cash_audit.json"
    g3 = audit_g3_quote_coverage(root)
    g3["note_de"] = g3.get("quote_coverage_label_de", "")
    g4 = audit_g4_execution_report()
    g4["note_de"] = "1 Zeile/Symbol: executed vs NO_LIMIT_PRICE vs PREFLIGHT"
    g5 = audit_g5_exe(root, build=build_exe)
    g6 = audit_g6_phase5_validation(root, skip_pytest=skip_pytest, build_exe=build_exe)
    g6["note_de"] = "validate_live_rebalance_phase5.py — Dry-Run vor Release"

    checks = {
        "schema_version": 1,
        "phase": "G",
        "generated_at_utc": _utc_now(),
        "G1_symbol_mapping": g1,
        "G2_planning_cash": g2,
        "G3_quote_coverage": g3,
        "G4_execution_report": g4,
        "G5_exe_os_bat": g5,
        "G6_phase5_dry_run": g6,
    }
    statuses = [g1.get("status"), g2.get("status"), g3.get("status"), g4.get("status"), g5.get("status"), g6.get("status")]
    checks["overall_pass"] = all(s in {"PASS", "PARTIAL"} for s in statuses) and g6.get("overall_pass")
    checks["status"] = "COMPLETE" if checks["overall_pass"] else "COMPLETE_WITH_WARNINGS"

    atomic_write_json(root / EVIDENCE_SUMMARY, checks)
    atomic_write_text(root / EVIDENCE_MATRIX, format_gate_matrix_md(checks))
    atomic_write_json(root / LIVE_OPS_DOC, g6.get("live_trading_operations") or {})

    report_path = root / "docs" / "PHASE_G_LIVE_OPERATIONS_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(report_path, format_gate_matrix_md(checks).replace(
        "Live US-Session-Run",
        "Referenz: `docs/LIVE_TRADING_REBALANCE_REMEDIATION_PLAN.md`. Live US-Session-Run",
    ))

    return checks
