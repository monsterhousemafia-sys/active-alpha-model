"""Phase H — Operator transparency panels for Decision Cockpit."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion

CHARTER_PATH = Path("control") / "champion_decision_charter.md"
CANONICAL_JSON = Path("evidence") / "canonical_model_comparison.json"
CANONICAL_MD = Path("evidence") / "canonical_model_comparison.md"
CHALLENGER_CONTROL = Path("control") / "challenger_report.json"
BLOCKED_REBALANCE_SYMBOLS = frozenset({"SPY", "VUSD"})


def _read_json(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.is_file():
        return {}, "MISSING"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "OK"
    except Exception:
        return {}, "UNPARSEABLE"


def _role_label(variant_id: str, roles: Dict[str, str]) -> str:
    return roles.get(variant_id) or ""


def build_h1_model_comparison_de(root: Path) -> Dict[str, Any]:
    """Table from canonical_model_comparison (matrix + intersection frames)."""
    root = Path(root)
    canonical, st = _read_json(root / CANONICAL_JSON)
    lines: List[str] = []
    if st != "OK":
        return {
            "status": "MISSING",
            "lines_de": ["Canonical Comparison fehlt — Phase C ausführen: tools/build_canonical_model_comparison.py"],
            "source_ref": str(CANONICAL_JSON).replace("\\", "/"),
        }

    headline = canonical.get("headline") or {}
    roles = {v.get("variant_id"): v.get("role") for v in canonical.get("variants") or [] if v.get("variant_id")}
    locked = resolve_locked_champion(root)

    lines.extend(
        [
            "Modell-Vergleich (Research) — read-only",
            f"Champion (freigegeben): {locked}",
            f"Matrix-Sharpe-Führer: {headline.get('matrix_embedded_sharpe_leader', '—')}",
            f"Champion Matrix-Rang: {headline.get('champion_sharpe_rank_matrix', '—')}",
            "",
            "Rangliste — Matrix embedded (~1860d):",
        ]
    )
    for row in canonical.get("rankings", {}).get("sharpe_matrix_embedded") or []:
        vid = str(row.get("variant_id") or "")
        sharpe = row.get("sharpe_0rf")
        role = _role_label(vid, roles)
        tag = " [CHAMPION]" if vid == locked else ""
        lines.append(f"  {row.get('rank', '?'):>2}. {vid} ({role}) — Sharpe {sharpe:.4f}{tag}" if sharpe is not None else f"  {row.get('rank')}. {vid}")

    aligned = canonical.get("rankings", {}).get("sharpe_aligned_intersection") or []
    if aligned:
        lines.extend(["", "Rangliste — Aligned intersection (MOM/research CSVs):"])
        for row in aligned:
            vid = str(row.get("variant_id") or "")
            sharpe = row.get("sharpe_0rf")
            role = _role_label(vid, roles)
            lines.append(f"  {row.get('rank', '?'):>2}. {vid} ({role}) — Sharpe {sharpe:.4f}" if sharpe is not None else f"  {row.get('rank')}. {vid}")

    if headline.get("do_not_cross_compare_frames"):
        lines.extend(
            [
                "",
                "WARNUNG: Matrix-embedded Sharpe ≠ MOM-Intersection-Sharpe vermischen.",
                f"Vollständig: {CANONICAL_MD.as_posix()}",
            ]
        )

    return {
        "status": "OK",
        "lines_de": lines,
        "source_ref": str(CANONICAL_JSON).replace("\\", "/"),
        "markdown_ref": str(CANONICAL_MD).replace("\\", "/"),
        "matrix_leader": headline.get("matrix_embedded_sharpe_leader"),
        "champion_is_sharpe_leader": headline.get("champion_is_sharpe_leader"),
    }


def _charter_excerpt(root: Path, *, max_lines: int = 28) -> List[str]:
    path = root / CHARTER_PATH
    if not path.is_file():
        return ["Charter fehlt — control/champion_decision_charter.md"]
    raw = path.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    for line in raw:
        if line.startswith("#") and len(out) > 3:
            if len(out) >= max_lines:
                break
        out.append(line.rstrip())
        if len(out) >= max_lines:
            out.append("… (gekürzt — vollständig in control/champion_decision_charter.md)")
            break
    return out


def _resolve_last_signal_date(root: Path) -> Tuple[str, str]:
    """Best-effort signal date from portfolio CSV or live sync manifest."""
    root = Path(root)
    try:
        from aa_config_env import resolve_launcher_env

        env = resolve_launcher_env(root, frozen=False)
        out_dir = root / str(env.get("AA_BACKTEST_OUT_DIR") or "model_output_sp500_pit_t212")
    except Exception:
        out_dir = root / "model_output_sp500_pit_t212"

    if not out_dir.is_dir():
        return "n/a", "output_dir_missing"

    try:
        from aa_dashboard_result import load_target_portfolio

        portfolio, _ = load_target_portfolio(out_dir)
        if not portfolio.empty and "signal_date" in portfolio.columns:
            return str(portfolio["signal_date"].iloc[0]), "latest_target_portfolio.csv"
    except Exception:
        pass

    try:
        from aa_live_daily_sync import read_sync_manifest

        sync = read_sync_manifest(out_dir)
        if sync.get("signal_date"):
            return str(sync["signal_date"]), "live_daily_sync.json"
        if sync.get("price_latest"):
            return str(sync["price_latest"]), "live_daily_sync.json"
    except Exception:
        pass

    return "n/a", "not_found"


def build_h2_champion_status_de(root: Path) -> Dict[str, Any]:
    """Charter summary + last signal date + Phase-E operational status."""
    root = Path(root)
    locked = resolve_locked_champion(root)
    signal_date, signal_source = _resolve_last_signal_date(root)
    ops, ops_st = _read_json(root / "control" / "champion_operational_status.json")
    strat = ops.get("strategic_decision") if ops_st == "OK" else None

    lines = [
        f"Produktiv-Champion: {locked}",
        f"Letztes Signal-Datum: {signal_date} ({signal_source})",
        f"Auto-Promotion: DISABLED",
    ]
    if strat:
        lines.append(f"Phase-E-Entscheidung: {strat} — {ops.get('operational_champion', locked)}")
    lines.extend(["", "--- Charter (Auszug) ---", *_charter_excerpt(root)])

    return {
        "status": "OK" if (root / CHARTER_PATH).is_file() else "PARTIAL",
        "lines_de": lines,
        "authoritative_champion": locked,
        "last_signal_date": signal_date,
        "last_signal_source": signal_source,
        "charter_ref": str(CHARTER_PATH).replace("\\", "/"),
        "strategic_decision": strat,
    }


def build_h3_rebalance_precheck_de(root: Path) -> Dict[str, Any]:
    """Planned buys, cash wave scale, quote coverage, blocked symbols."""
    root = Path(root)
    from aa_config_env import resolve_launcher_env
    from execution.confirmed_live.rebalance_wave_planner import plan_rebalance_wave
    from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
    from market.champion_quote_gate import require_champion_quote_coverage

    env = resolve_launcher_env(root, frozen=False)
    out_dir = root / str(env.get("AA_BACKTEST_OUT_DIR") or "model_output_sp500_pit_t212")
    planning_cash = 492.0
    sync_path = root / "live_pilot/manual_execution/readonly_real_account_state/latest_sync.json"
    if sync_path.is_file():
        try:
            from integrations.trading212.t212_cash_parser import parse_cash_breakdown

            doc = json.loads(sync_path.read_text(encoding="utf-8"))
            planning_cash = float(parse_cash_breakdown(account_summary=doc.get("summary") or {}).planning_cash_eur)
        except Exception:
            pass

    planned_symbols: List[str] = []
    blocked: List[str] = []
    if out_dir.is_dir():
        try:
            import pandas as pd

            pf = out_dir / "latest_target_portfolio.csv"
            if pf.is_file():
                frame = pd.read_csv(pf)
                if "ticker" in frame.columns:
                    for t in frame["ticker"].dropna().unique():
                        sym = str(t).upper()
                        if sym in BLOCKED_REBALANCE_SYMBOLS:
                            blocked.append(sym)
                        elif sym not in planned_symbols:
                            planned_symbols.append(sym)
        except Exception:
            pass

    if not planned_symbols:
        planned_symbols = [s for s in CHAMPION_SYMBOLS if s not in BLOCKED_REBALANCE_SYMBOLS]

    buy_symbols = [s for s in planned_symbols if s not in BLOCKED_REBALANCE_SYMBOLS]
    raw_total = min(planning_cash * 0.95, 470.0) if planning_cash else 470.0
    each = round(raw_total / max(len(buy_symbols), 1), 2)
    orders = [{"symbol": s, "side": "BUY", "notional_eur": each} for s in buy_symbols]
    wave = plan_rebalance_wave(orders, planning_cash)
    scaled_orders = list(wave.get("orders") or [])

    gate = require_champion_quote_coverage(
        root,
        symbols=buy_symbols,
        refresh_if_stale=False,
    )

    lines = [
        "Rebalance-Vorcheck (read-only, keine T212-POSTs)",
        f"Planning-Cash: {planning_cash:,.2f} EUR",
        f"Roh-Summe BUY (vor Welle): {raw_total:,.2f} EUR",
        f"Skaliert (nach Welle): {float(wave.get('total_buy_notional_scaled') or 0):,.2f} EUR",
        f"Scale-Faktor: {wave.get('scale_factor')}",
        f"Quote-Coverage (geplante Käufe): {gate.get('quote_coverage_label_de', '—')}",
        f"Geplante BUY-Orders: {len(scaled_orders)}",
    ]
    if blocked:
        lines.append(f"Blockiert (kein Live-BUY): {', '.join(sorted(blocked))}")
    if not gate.get("ok"):
        lines.append(f"Hinweis: {gate.get('message_de', 'Kurse unvollständig')}")
    lines.append("")
    lines.append("Top-Positionen (nach Skalierung):")
    for row in scaled_orders[:12]:
        lines.append(f"  {row.get('symbol')}: {float(row.get('notional_eur', 0)):,.2f} EUR")
    if len(scaled_orders) > 12:
        lines.append(f"  … +{len(scaled_orders) - 12} weitere")

    cash_ok = float(wave.get("total_buy_notional_scaled") or 0) <= planning_cash * 1.02 + 0.01
    return {
        "status": "PASS" if cash_ok and gate.get("ok") else "WARN",
        "lines_de": lines,
        "planning_cash_eur": planning_cash,
        "cash_cap_ok": cash_ok,
        "quote_coverage_ok": bool((gate.get("coverage") or {}).get("coverage_ok")),
        "quote_coverage_label_de": gate.get("quote_coverage_label_de"),
        "blocked_symbols": sorted(blocked),
        "planned_buy_count": len(scaled_orders),
        "scale_factor": wave.get("scale_factor"),
    }


def build_h4_pointer_drift_de(root: Path) -> Dict[str, Any]:
    """FAILSAFE when challenger_report champion ≠ locked champion."""
    root = Path(root)
    locked = resolve_locked_champion(root)
    observations: List[Dict[str, str]] = []

    def _observe(path: Path, field: str) -> None:
        doc, st = _read_json(path)
        if st != "OK":
            observations.append({"source": str(path.relative_to(root)).replace("\\", "/"), "value": "", "status": st})
            return
        val = str(doc.get(field) or doc.get("variant_id") or doc.get("operational_champion") or "").strip()
        observations.append({"source": str(path.relative_to(root)).replace("\\", "/"), "value": val, "status": "OK"})

    _observe(root / CHALLENGER_CONTROL, "champion_variant_id")
    try:
        from aa_config_env import resolve_launcher_env

        env = resolve_launcher_env(root, frozen=False)
        out_name = str(env.get("AA_BACKTEST_OUT_DIR") or "model_output_sp500_pit_t212")
    except Exception:
        out_name = "model_output_sp500_pit_t212"
    _observe(root / out_name / "challenger_report.json", "champion_variant_id")
    _observe(root / Path(out_name) / "latest_validated_run.json", "variant_id")

    mismatches = [o for o in observations if o.get("status") == "OK" and o.get("value") and o["value"] != locked]
    missing = [o for o in observations if o.get("status") != "OK"]
    drift = bool(mismatches)

    lines: List[str] = [
        f"Locked Champion (Policy): {locked}",
        f"Pointer-Drift: {'JA — FAILSAFE' if drift else 'nein'}",
        "",
        "Beobachtete Pointer:",
    ]
    for o in observations:
        mark = " *** DRIFT ***" if o.get("value") and o["value"] != locked else ""
        lines.append(f"  {o['source']}: {o.get('value') or o.get('status')}{mark}")
    if missing:
        lines.append("")
        lines.append("Fehlende Quellen (fail-closed bei Konflikt, hier nur Info):")
        for o in missing:
            lines.append(f"  {o['source']}: {o['status']}")

    failsafe_banner = (
        f"FAILSAFE: Challenger-Pointer weicht von {locked} ab — keine Promotion / kein Champion-Wechsel."
        if drift
        else None
    )
    return {
        "status": "FAIL" if drift else "PASS",
        "drift_detected": drift,
        "failsafe_active": drift,
        "failsafe_banner_de": failsafe_banner,
        "locked_champion": locked,
        "mismatches": mismatches,
        "observations": observations,
        "lines_de": lines,
    }


def build_operator_transparency_de(root: Path) -> Dict[str, Any]:
    """Aggregate H1–H4 for Decision Cockpit viewmodel."""
    root = Path(root)
    h1 = build_h1_model_comparison_de(root)
    h2 = build_h2_champion_status_de(root)
    h3 = build_h3_rebalance_precheck_de(root)
    h4 = build_h4_pointer_drift_de(root)

    return {
        "schema_version": 1,
        "phase": "H",
        "h1_model_comparison": h1,
        "h2_champion_status": h2,
        "h3_rebalance_precheck": h3,
        "h4_pointer_drift": h4,
        "authoritative_champion": h2.get("authoritative_champion") or AUTHORITATIVE_CHAMPION,
        "pointer_drift_active": h4.get("drift_detected", False),
        "failsafe_banner_de": h4.get("failsafe_banner_de"),
        "last_signal_date": h2.get("last_signal_date"),
    }
