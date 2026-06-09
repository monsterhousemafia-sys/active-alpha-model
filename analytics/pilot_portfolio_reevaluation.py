"""Periodic live portfolio vs champion — v2 uses full CSV regime/exposure (advisory only)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json
from analytics.human_vs_base_comparison import human_portfolio_from_broker
from analytics.pilot_investment_plan import CHAMPION_ID, CASH_BUFFER_PCT
from analytics.pilot_today_pick import BLOCKED_SYMBOLS

_POLICY_REL = Path("control/pilot_portfolio_reevaluation.json")
_EVIDENCE_REL = Path("evidence/pilot_portfolio_reevaluation_latest.json")
_STATE_REL = Path("live_pilot/confirmed_execution/pilot_reevaluation_state.json")
_CSV_REL = Path("model_output_sp500_pit_t212/latest_target_portfolio.csv")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_policy() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "enabled": True,
        "interval_minutes": 30,
        "interval_minutes_us_open": 5,
        "quote_max_age_seconds_us_open": 120,
        "min_drift_pct_to_flag": 4.0,
        "min_trade_eur": 12.0,
        "min_priority_score": 8.0,
        "cash_buffer_pct": CASH_BUFFER_PCT,
        "max_action_rows": 8,
        "max_model_symbols": 15,
        "portfolio_exposure_tolerance_pct": 5.0,
        "require_fresh_quotes_in_us_session": True,
    }


def load_policy(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import policy_section

    pol = policy_section(Path(root), "reevaluation")
    return _harmonize_reeval_with_prediction_ops(Path(root), pol)


def _harmonize_reeval_with_prediction_ops(root: Path, pol: Dict[str, Any]) -> Dict[str, Any]:
    """Gleiche min_drift/min_trade wie live_trading + prediction_operations (daily_alpha_h1)."""
    try:
        from analytics.prediction_operations import load_prediction_operations

        ops = load_prediction_operations(root)
        if str(ops.get("active_profile") or "") != "daily_alpha_h1":
            return pol
        out = dict(pol)
        rebal = ops.get("rebalance") or {}
        budget = ops.get("budget") or {}
        if rebal.get("min_weight_gap_pct") is not None:
            out["min_drift_pct_to_flag"] = float(rebal["min_weight_gap_pct"])
        if budget.get("min_position_eur") is not None:
            out["min_trade_eur"] = max(
                float(out.get("min_trade_eur") or 5.0),
                float(budget["min_position_eur"]),
            )
        from analytics.prediction_operations import budget_config

        out["cash_buffer_pct"] = float(budget_config(root).get("cash_buffer_pct") or 0.0)
        out["harmonized_from"] = "prediction_operations.daily_alpha_h1"
        return out
    except Exception:
        return pol


def _us_session_open() -> bool:
    from analytics.pilot_day_trading_facade import us_session_open

    return us_session_open()


def effective_interval_minutes(pol: Dict[str, Any]) -> int:
    if _us_session_open():
        return int(pol.get("interval_minutes_us_open") or 5)
    return int(pol.get("interval_minutes") or 30)


def _normalize_ticker(raw: str) -> str:
    t = str(raw or "").upper().strip()
    if t.endswith("_EQ"):
        t = t[:-3]
    if t.endswith("L") and len(t) > 1:
        t = t[:-1]
    return t


def _load_prognosis_regime(root: Path) -> str:
    for name in ("pilot_today_prognosis_latest.json", "pilot_today_prognosis_20260601.json"):
        path = Path(root) / "evidence" / name
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return str(doc.get("regime") or "")
        except (json.JSONDecodeError, OSError):
            continue
    return ""


def load_champion_portfolio_model(root: Path) -> Dict[str, Any]:
    """Read frozen champion CSV — meta row + per-symbol model fields."""
    path = Path(root) / _CSV_REL
    if not path.is_file():
        return {"status": "MISSING", "meta": {}, "symbols": {}}
    try:
        import pandas as pd

        df = pd.read_csv(path)
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc), "meta": {}, "symbols": {}}
    if df.empty or "ticker" not in df.columns:
        return {"status": "EMPTY", "meta": {}, "symbols": {}}

    meta_row = df.iloc[0]
    meta = {
        "signal_date": str(meta_row.get("signal_date", ""))[:10],
        "risk_on": bool(meta_row.get("risk_on", True)),
        "target_exposure": float(meta_row.get("target_exposure") or 0),
        "portfolio_exposure": float(meta_row.get("portfolio_exposure") or 0),
        "portfolio_beta": float(meta_row.get("portfolio_beta") or 0),
        "effective_max_portfolio_beta": float(meta_row.get("effective_max_portfolio_beta") or 0),
        "avg_alpha_lcb": float(meta_row.get("avg_alpha_lcb") or 0),
        "n_positions": int(meta_row.get("n_positions") or 0),
    }
    symbols: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        sym = str(row.get("ticker", "")).upper().strip()
        if not sym or sym in BLOCKED_SYMBOLS:
            continue
        symbols[sym] = {
            "symbol": sym,
            "target_weight": float(row.get("target_weight") or 0),
            "mu_hat": float(row.get("mu_hat") or 0),
            "alpha_lcb": float(row.get("alpha_lcb") or 0),
            "rank_score": float(row.get("rank_score") or 0),
            "selection_score": float(row.get("selection_score") or 0),
            "eligible": bool(row.get("eligible", True)),
            "sector": str(row.get("sector") or ""),
            "risk_on": bool(row.get("risk_on", meta["risk_on"])),
        }
    return {"status": "OK", "meta": meta, "symbols": symbols}


def _model_targets_from_champion(
    champion: Dict[str, Any],
    *,
    account_eur: float,
    buffer_pct: float,
    pol: Dict[str, Any],
    root: Optional[Path] = None,
    buffer_already_applied: bool = False,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Map CSV target_weight to EUR on account; respect model target_exposure."""
    meta = champion.get("meta") or {}
    sym_rows: Dict[str, Dict[str, Any]] = dict(champion.get("symbols") or {})
    eff_buffer = 0.0 if buffer_already_applied else float(buffer_pct)
    investable = round(max(0.0, account_eur * (1.0 - eff_buffer / 100.0)), 2)
    target_exp = float(meta.get("target_exposure") or 1.0)
    port_exp = float(meta.get("portfolio_exposure") or target_exp) or 1.0
    model_capital = round(investable * min(1.0, max(0.0, target_exp)), 2)

    ranked = sorted(
        sym_rows.values(),
        key=lambda r: (float(r.get("rank_score") or 0), float(r.get("alpha_lcb") or 0)),
        reverse=True,
    )[: int(pol.get("max_model_symbols") or 15)]
    weight_sum = sum(float(r.get("target_weight") or 0) for r in ranked) or port_exp

    targets: Dict[str, Dict[str, Any]] = {}
    for r in ranked:
        sym = str(r["symbol"])
        tw = float(r.get("target_weight") or 0)
        if tw <= 0:
            continue
        share = tw / weight_sum if weight_sum > 0 else 0.0
        target_gross = round(model_capital * share, 2)
        target_eur = target_gross
        fee_row: Dict[str, Any] = {}
        if root is not None and target_gross > 0:
            from analytics.t212_broker_economics import apply_buy_target_fee_adjustment

            fee_row = apply_buy_target_fee_adjustment(target_gross, root)
            target_eur = float(fee_row.get("target_eur") or target_gross)
        targets[sym] = {
            "symbol": sym,
            "model_weight_pct": round(100.0 * tw / port_exp if port_exp > 0 else 0, 2),
            "target_eur": target_eur,
            "target_eur_gross": fee_row.get("target_eur_gross", target_gross),
            "estimated_one_way_cost_eur": fee_row.get("estimated_one_way_cost_eur"),
            "alpha_lcb": float(r.get("alpha_lcb") or 0),
            "mu_hat": float(r.get("mu_hat") or 0),
            "rank_score": float(r.get("rank_score") or 0),
            "eligible": bool(r.get("eligible", True)),
            "sector": r.get("sector") or "",
        }
    scaling = {
        "investable_eur": investable,
        "model_capital_eur": model_capital,
        "target_exposure_pct": round(100.0 * target_exp, 1),
        "portfolio_exposure_model_pct": round(100.0 * port_exp, 1),
        "weight_sum": round(weight_sum, 4),
        "cash_buffer_pct_applied": eff_buffer,
        "buffer_already_in_account": buffer_already_applied,
    }
    return targets, scaling


def _resolve_broker_from_r3_t212(root: Path, broker: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Live T212-Kontostand — nur trusted Sync als Berechnungsbasis."""
    merged = dict(broker or {})
    if merged.get("cash_eur") is not None and merged.get("source") == "t212_live_sync":
        return merged
    try:
        from analytics.r3_live_capital import sync_live_capital_basis

        cap = sync_live_capital_basis(root, force=False)
        if cap.get("ok"):
            rb = dict(cap.get("broker") or {})
            merged.update(rb)
            merged["r3_investable_eur"] = cap.get("investable_eur")
            merged["r3_planning_cash_eur"] = cap.get("planning_cash_eur")
            merged["source"] = "t212_live_sync"
            return merged
    except Exception:
        pass
    bond_path = Path(root) / "evidence/r3_t212_api_bond_latest.json"
    if bond_path.is_file():
        try:
            from analytics.r3_closed_loop import load_r3_account_for_engine

            acct = load_r3_account_for_engine(root)
            if acct.get("ok"):
                rb = dict(acct.get("broker") or {})
                if rb.get("cash_eur") is not None:
                    merged.update(rb)
                    merged["r3_investable_eur"] = acct.get("investable_eur")
                    merged["r3_planning_cash_eur"] = acct.get("planning_cash_eur")
                    merged["source"] = rb.get("source") or "r3_t212_api_bond"
        except Exception:
            pass
    return merged


def _account_eur_for_targets(broker: Dict[str, Any], human: Dict[str, Any]) -> float:
    """Kontobasis für Modell-Skalierung — Live-Depot (Cash+Positionen) hat Vorrang."""
    plan_cap = broker.get("r3_plan_capital_eur")
    if plan_cap is not None:
        try:
            pc = float(plan_cap)
            if pc > 0:
                return round(pc, 2)
        except (TypeError, ValueError):
            pass
    if broker.get("r3_planning_cash_eur") is not None or broker.get("source") == "r3_t212_api_bond":
        planning = broker.get("r3_planning_cash_eur")
        if planning is None:
            planning = (broker.get("cash_breakdown") or {}).get("planning_cash_eur")
        try:
            if planning is not None and float(planning) > 0:
                return round(float(planning), 2)
        except (TypeError, ValueError):
            pass
        try:
            cash = broker.get("cash_eur")
            if cash is not None and float(cash) > 0:
                return round(float(cash), 2)
        except (TypeError, ValueError):
            pass
    return _deployable_total_eur(broker, human)


def _capital_basis_label(
    account_eur: float,
    broker: Dict[str, Any],
    economics: Dict[str, Any],
    *,
    deployable_eur: float | None = None,
) -> str:
    basis = str(broker.get("calculation_basis") or "")
    if basis == "t212_total_account_live":
        label = f"Berechnungsbasis: {account_eur:.0f} € Gesamtdepot (Cash+Positionen, ohne Puffer)"
    elif broker.get("source") == "t212_live_sync":
        label = f"Berechnungsbasis: {account_eur:.0f} € live T212 (ohne Puffer)"
    else:
        label = f"Berechnungsbasis: {account_eur:.0f} €"
    if deployable_eur is not None and abs(float(deployable_eur) - account_eur) > 0.5:
        label = f"{label} · Modell deployable {float(deployable_eur):.0f} € (nach target_exposure)"
    fee_de = (economics.get("fees") or {}).get("summary_de")
    if fee_de:
        label = f"{label} · {fee_de}"
    return label


def _deployable_total_eur(broker: Dict[str, Any], human: Dict[str, Any]) -> float:
    bd = broker.get("cash_breakdown") or {}
    total = bd.get("total_account_value_eur")
    if total is None:
        total = human.get("total_value_eur")
    try:
        tv = float(total or 0)
    except (TypeError, ValueError):
        tv = 0.0
    if tv <= 0:
        try:
            tv = float(broker.get("cash_eur") or 0) + float(human.get("invested_eur") or 0)
        except (TypeError, ValueError):
            tv = 0.0
    return round(max(0.0, tv), 2)


def _held_by_symbol(human: Dict[str, Any]) -> Dict[str, float]:
    held: Dict[str, float] = {}
    for h in human.get("holdings") or []:
        sym = _normalize_ticker(str(h.get("symbol") or ""))
        if sym:
            held[sym] = float(h.get("value_eur") or 0)
    return held


def _signal_priority(row: Dict[str, Any]) -> float:
    rs = float(row.get("rank_score") or 0)
    al = float(row.get("alpha_lcb") or 0)
    mu = float(row.get("mu_hat") or 0)
    return round(rs * 0.45 + al * 35.0 + mu * 10.0, 4)


def _check_quotes_for_session(
    quote_snapshot: Optional[Dict[str, Any]],
    pol: Dict[str, Any],
    *,
    required_symbols: Optional[List[str]] = None,
) -> Tuple[bool, str, bool]:
    """Return ok, reason, us_session_open."""
    us_open = _us_session_open()
    if quote_snapshot is None:
        if us_open and pol.get("require_fresh_quotes_in_us_session"):
            return False, "Keine Live-Kurse — während US-Session erforderlich.", us_open
        return True, "", us_open
    from integrations.trading212.t212_instrument_quotes import champion_quote_coverage
    from market.live_quote_engine import classify_freshness, require_fresh_for_calculation

    max_age = None
    if us_open:
        max_age = int(pol.get("quote_max_age_seconds_us_open") or 120)
    fresh = quote_snapshot.get("freshness") or classify_freshness(
        quote_snapshot, max_age_s=max_age
    )
    snap = {**quote_snapshot, "freshness": fresh}
    ok, reason = require_fresh_for_calculation(snap)
    if us_open and pol.get("require_fresh_quotes_in_us_session") and not ok:
        return False, reason, us_open
    if us_open and fresh.get("status") != "FRESH":
        return False, str(fresh.get("reason") or "Kurse nicht frisch genug für US-Session."), us_open

    req = [str(s).upper() for s in (required_symbols or []) if s]
    if us_open and req:
        prices = snap.get("executable_prices_eur") or {}
        cov = champion_quote_coverage(prices, required_symbols=req)
        if not cov.get("coverage_ok"):
            missing = cov.get("missing_symbols") or []
            miss = ", ".join(str(s) for s in missing[:6])
            extra = f" (+{len(missing) - 6})" if len(missing) > 6 else ""
            return (
                False,
                (
                    f"Live-Kurse unvollständig "
                    f"({cov.get('covered_count')}/{cov.get('required_count')}) — "
                    f"fehlend: {miss}{extra}"
                ),
                us_open,
            )
    return True, "", us_open


def _action_for_gap(
    *,
    root: Path,
    gap_eur: float,
    weight_gap_pct: float,
    pol: Dict[str, Any],
    signals_ok: bool,
    risk_on: bool,
    eligible: bool,
    held: bool,
) -> Tuple[str, str, float]:
    min_eur = float(pol.get("min_trade_eur") or 12)
    min_drift = float(pol.get("min_drift_pct_to_flag") or 4)

    if not signals_ok:
        if abs(gap_eur) >= min_eur or abs(weight_gap_pct) >= min_drift:
            return "BEOBACHTEN", "Signale veraltet — nur beobachten", 0.0
        return "HALTEN", "Halten (Signale veraltet)", 0.0

    if held and not eligible:
        return "ABBAUEN", "Nicht mehr im Modell-Universum — Position prüfen", round(abs(gap_eur) * 1.1, 2)

    if not risk_on:
        if gap_eur <= -min_eur:
            return "REDUZIEREN", "Risk-off — Übergewicht abbauen", round(abs(gap_eur) * 1.2, 2)
        if gap_eur >= min_eur:
            return "HALTEN", "Risk-off — kein Nachkauf empfohlen", 0.0
        return "HALTEN", "Risk-off — Cash/Defensive", 0.0

    if gap_eur >= min_eur and eligible:
        from integrations.trading212.t212_fee_economics import is_notional_worth_trading

        worth, fee_reason = is_notional_worth_trading(gap_eur, root)
        if not worth:
            return "HALTEN", f"Zu klein für T212-Gebühren — {fee_reason}", 0.0
        from integrations.trading212.t212_fee_economics import (
            is_notional_worth_trading_stress,
            load_fee_economics_policy,
        )

        if load_fee_economics_policy(root).get("require_stress_pass_for_trade", True):
            worth_s, fee_s = is_notional_worth_trading_stress(gap_eur, root)
            if not worth_s:
                return "HALTEN", f"Stress-Kosten — {fee_s}", 0.0
        material = weight_gap_pct >= min_drift or gap_eur >= min_eur * 2
        if material:
            score = gap_eur * (1.0 + max(0.0, weight_gap_pct) / 10.0)
            if not held:
                return "KAUFEN", f"Kauf ~{gap_eur:.0f} € — lohnend nach Gebühren", round(score, 2)
            return "NACHKAUF", f"Nachkauf ~{gap_eur:.0f} € empfohlen", round(score, 2)
    if gap_eur <= -min_eur and weight_gap_pct <= -min_drift:
        from integrations.trading212.t212_fee_economics import is_notional_worth_trading

        sell_notional = abs(gap_eur)
        worth, fee_reason = is_notional_worth_trading(sell_notional, root)
        if not worth:
            return "HALTEN", f"Verkauf zu klein — Gebühren überwiegen ({fee_reason})", 0.0
        from integrations.trading212.t212_fee_economics import (
            is_notional_worth_trading_stress,
            load_fee_economics_policy,
        )

        if load_fee_economics_policy(root).get("require_stress_pass_for_trade", True):
            worth_s, fee_s = is_notional_worth_trading_stress(sell_notional, root)
            if not worth_s:
                return "HALTEN", f"Verkauf Stress-Kosten — {fee_s}", 0.0
        score = abs(gap_eur) * (1.0 + abs(weight_gap_pct) / 10.0)
        return "REDUZIEREN", f"Übergewicht ~{abs(gap_eur):.0f} € — Gewicht prüfen", round(score * 0.85, 2)
    if gap_eur >= min_eur * 0.5 and eligible:
        return "LEICHT_UNTER", f"Leicht untergewichtet ({gap_eur:+.0f} €)", round(gap_eur * 0.5, 2)
    return "HALTEN", "Im Toleranzbereich", 0.0


def _portfolio_exposure_check(
    human: Dict[str, Any],
    meta: Dict[str, Any],
    pol: Dict[str, Any],
) -> Dict[str, Any]:
    total = float(human.get("total_value_eur") or 0)
    invested = float(human.get("invested_eur") or 0)
    cash_pct = float(human.get("cash_weight_pct") or 0)
    invested_pct = round(100.0 * invested / total, 1) if total > 0 else 0.0
    model_pct = round(100.0 * float(meta.get("target_exposure") or 0), 1)
    tol = float(pol.get("portfolio_exposure_tolerance_pct") or 5.0)
    gap = round(model_pct - invested_pct, 1)
    return {
        "invested_pct": invested_pct,
        "model_target_invested_pct": model_pct,
        "cash_weight_pct": cash_pct,
        "exposure_gap_pct": gap,
        "over_invested": gap < -tol,
        "under_invested": gap > tol,
        "risk_on": bool(meta.get("risk_on")),
    }


def evaluate_live_portfolio_vs_champion(
    root: Path,
    *,
    broker: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    quote_snapshot: Optional[Dict[str, Any]] = None,
    champion_guard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    pol = load_policy(root)
    us_open = _us_session_open()
    if not pol.get("enabled"):
        return {
            "status": "DISABLED",
            "trade_required": False,
            "urgency": "NONE",
            "summary_de": "Portfolio-Check deaktiviert.",
            "generated_at_utc": _utc_now(),
            "us_session_open": us_open,
        }

    broker = _resolve_broker_from_r3_t212(root, broker)
    try:
        from analytics.t212_live_portfolio_basis import enrich_broker_from_live_picture

        broker = enrich_broker_from_live_picture(root, broker)
    except Exception:
        pass
    if not broker or broker.get("cash_eur") is None:
        return {
            "status": "NOT_EVALUABLE",
            "trade_required": False,
            "urgency": "NONE",
            "summary_de": "Kein Broker-Sync — zuerst «Aktualisieren».",
            "generated_at_utc": _utc_now(),
            "us_session_open": us_open,
        }

    guard = champion_guard or {}
    signals_ok = bool(guard.get("signals_ok", True))
    champion_ok = bool(guard.get("champion_ok", True))

    champion = load_champion_portfolio_model(root)
    if champion.get("status") != "OK":
        return {
            "status": "MODEL_CSV_MISSING",
            "trade_required": False,
            "urgency": "NONE",
            "summary_de": "Champion-Portfolio-CSV fehlt — kein Modell-Vergleich möglich.",
            "generated_at_utc": _utc_now(),
            "us_session_open": us_open,
        }

    meta = champion["meta"]
    risk_on = bool(meta.get("risk_on"))
    regime = _load_prognosis_regime(root) or ("RISK_ON" if risk_on else "RISK_OFF")

    human = human_portfolio_from_broker(
        {
            "cash_eur": broker.get("cash_eur"),
            "positions": broker.get("positions") or [],
            "credentials_configured": True,
        }
    )
    try:
        from analytics.r3_closed_loop import resolve_r3_plan_capital_eur

        cap_basis = resolve_r3_plan_capital_eur(
            root,
            broker,
            float(broker.get("r3_planning_cash_eur") or broker.get("cash_eur") or 0),
        )
        if int(cap_basis.get("positions_count") or 0) > 0:
            broker["r3_plan_capital_eur"] = cap_basis.get("plan_capital_eur")
            broker["r3_total_account_eur"] = cap_basis.get("total_account_value_eur")
            broker["r3_invested_eur"] = cap_basis.get("invested_eur")
            broker["calculation_basis"] = cap_basis.get("basis")
    except Exception:
        cap_basis = {}
    account_eur = _account_eur_for_targets(broker, human)
    buffer_pct = float(pol.get("cash_buffer_pct") or CASH_BUFFER_PCT)
    buffer_applied = broker.get("r3_plan_capital_eur") is not None
    targets, scaling = _model_targets_from_champion(
        champion,
        account_eur=account_eur,
        buffer_pct=buffer_pct,
        pol=pol,
        root=root,
        buffer_already_applied=buffer_applied,
    )
    broker_economics: Dict[str, Any] = {}
    try:
        from analytics.t212_broker_economics import build_broker_economics_context

        broker_economics = build_broker_economics_context(
            root, broker, plan_capital_eur=account_eur
        )
    except Exception:
        pass
    held = _held_by_symbol(human)
    exposure = _portfolio_exposure_check(human, meta, pol)

    if plan is None:
        from analytics.pilot_investment_plan import build_investment_plan

        inv = broker.get("r3_investable_eur")
        plan = build_investment_plan(
            root,
            float(broker.get("cash_eur") or account_eur),
            investable_eur=float(inv) if inv is not None else None,
            budget_source="r3_t212_investable" if inv is not None else None,
        )

    deployable = float(scaling.get("model_capital_eur") or 0)
    all_syms = sorted(set(targets) | set(held))
    quote_required = [
        s
        for s in all_syms
        if s in targets
        and (
            float(targets[s].get("target_eur") or 0) > 0
            or s in held
            or bool(targets[s].get("eligible"))
        )
    ]
    quote_ok, quote_reason, _ = _check_quotes_for_session(
        quote_snapshot,
        pol,
        required_symbols=quote_required,
    )
    from analytics.pilot_pick_rationale import explain_symbol_from_model_row, rationale_one_liner

    rows: List[Dict[str, Any]] = []
    drift_l1 = 0.0
    for sym in all_syms:
        tgt = targets.get(sym)
        sym_meta = (champion.get("symbols") or {}).get(sym) or {}
        target_eur = float(tgt["target_eur"]) if tgt else 0.0
        target_w = float(tgt["model_weight_pct"]) if tgt else 0.0
        eligible = bool(tgt.get("eligible", sym_meta.get("eligible", True)) if tgt else sym_meta.get("eligible", False))
        current_eur = float(held.get(sym, 0))
        current_w = round(100.0 * current_eur / account_eur, 2) if account_eur > 0 else 0.0
        gap_eur = round(target_eur - current_eur, 2)
        drift_pct = round(current_w - target_w, 2)
        weight_gap_pct = round(target_w - current_w, 2)
        drift_l1 += abs(drift_pct)
        action_code, action_de, priority = _action_for_gap(
            root=root,
            gap_eur=gap_eur,
            weight_gap_pct=weight_gap_pct,
            pol=pol,
            signals_ok=signals_ok and champion_ok,
            risk_on=risk_on,
            eligible=eligible,
            held=sym in held,
        )
        if action_code == "NACHKAUF" and tgt:
            priority = round(priority * (1.0 + _signal_priority(tgt) / 2.0), 2)
        if exposure.get("over_invested") and action_code == "NACHKAUF":
            action_code = "HALTEN"
            action_de = "Konto über Modell-Exposure — zuerst abbauen"
            priority = 0.0
        fee_note_de = ""
        trade_notional = abs(gap_eur) if action_code in ("NACHKAUF", "REDUZIEREN", "ABBAUEN") else 0.0
        if trade_notional > 0:
            from integrations.trading212.t212_fee_economics import (
                estimate_round_trip_cost_eur,
                is_notional_worth_trading,
                load_fee_economics_policy,
                trade_fee_hurdle_eur,
            )

            est = estimate_round_trip_cost_eur(
                trade_notional, policy=load_fee_economics_policy(root)
            )
            worth, _ = is_notional_worth_trading(trade_notional, root)
            hurdle = trade_fee_hurdle_eur(root, notional_eur=trade_notional)
            fee_note_de = (
                f"RT ~{est['round_trip_cost_eur']:.2f} € ({est['round_trip_pct']:.2f} %) · "
                f"Hürde {hurdle:.0f} € · {'OK' if worth else 'zu klein'}"
            )
        pick_rat = explain_symbol_from_model_row(
            sym_meta if sym_meta else (tgt or {}),
            meta,
            symbol=sym,
        )
        live_px = None
        if quote_ok and quote_snapshot:
            from market.live_quote_engine import price_for_symbol

            raw = price_for_symbol(quote_snapshot, sym)
            if raw and float(raw) > 0:
                live_px = round(float(raw), 2)
        rows.append(
            {
                "symbol": sym,
                "current_eur": round(current_eur, 2),
                "target_eur": target_eur,
                "gap_eur": gap_eur,
                "live_price_eur": live_px,
                "current_weight_pct": current_w,
                "target_weight_pct": target_w,
                "drift_pct": drift_pct,
                "weight_gap_pct": weight_gap_pct,
                "alpha_lcb": float(tgt.get("alpha_lcb") if tgt else sym_meta.get("alpha_lcb") or 0),
                "rank_score": float(tgt.get("rank_score") if tgt else sym_meta.get("rank_score") or 0),
                "eligible": eligible,
                "action_code": action_code,
                "action_de": action_de,
                "fee_note_de": fee_note_de,
                "pick_rationale_de": rationale_one_liner(pick_rat, max_len=100),
                "priority_score": priority,
            }
        )

    rows.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)
    min_pri = float(pol.get("min_priority_score") or 8)
    flat_depot = int(human.get("positions_count") or 0) == 0
    actionable = [
        r
        for r in rows
        if r.get("action_code") in ("KAUFEN", "NACHKAUF", "REDUZIEREN", "ABBAUEN")
        and (
            flat_depot
            and r.get("action_code") in ("KAUFEN", "NACHKAUF")
            or float(r.get("priority_score") or 0) >= min_pri
        )
    ]
    worthwhile_buys = [r for r in actionable if r.get("action_code") in ("KAUFEN", "NACHKAUF")]
    worthwhile_sells = [r for r in actionable if r.get("action_code") in ("REDUZIEREN", "ABBAUEN")]

    trade_required = (
        bool(actionable)
        and signals_ok
        and champion_ok
        and quote_ok
        and (risk_on or any(a.get("action_code") in ("REDUZIEREN", "ABBAUEN") for a in actionable))
    )
    if us_open and not quote_ok:
        trade_required = False

    urgency = _urgency_from_state(
        actionable=actionable,
        signals_ok=signals_ok and champion_ok,
        quote_ok=quote_ok,
        risk_on=risk_on,
        us_open=us_open,
        exposure=exposure,
    )

    summary_de = _format_summary(
        actionable=actionable,
        urgency=urgency,
        drift_l1=drift_l1,
        scaling=scaling,
        signals_ok=signals_ok and champion_ok,
        quote_ok=quote_ok,
        quote_reason=quote_reason,
        plan=plan,
        meta=meta,
        regime=regime,
        exposure=exposure,
        us_open=us_open,
    )
    next_review = _next_review_hint(pol, us_open=us_open)

    cost_risk: Dict[str, Any] = dict((plan or {}).get("cost_risk") or {})
    primary_p = (plan or {}).get("primary_action") or {}
    if not cost_risk and primary_p.get("target_eur"):
        from analytics.pilot_integrated_refresh import estimate_cost_risk

        sym_p = str(primary_p.get("symbol") or "").upper()
        lim = 0.0
        if quote_ok and quote_snapshot and sym_p:
            from market.live_quote_engine import price_for_symbol
            from paper.p16d.quote_plausibility import sanitize_price_eur

            raw = price_for_symbol(quote_snapshot, sym_p)
            lp, _, _ = sanitize_price_eur(sym_p, float(raw) if raw else None)
            if lp and lp > 0:
                lim = float(lp)
        cost_risk = estimate_cost_risk(
            root,
            notional_eur=float(primary_p.get("target_eur") or 0),
            limit_price_eur=lim,
        )

    return {
        "status": "OK",
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "champion_id": plan.get("champion_id") or CHAMPION_ID,
        "signal_date": meta.get("signal_date") or plan.get("signal_date"),
        "regime": regime,
        "risk_on": risk_on,
        "model_meta": meta,
        "exposure_check": exposure,
        "scaling": scaling,
        "account_eur": account_eur,
        "deployable_eur": deployable,
        "allocation_drift_l1_pct": round(drift_l1, 2),
        "trade_required": trade_required,
        "urgency": urgency,
        "summary_de": summary_de,
        "next_review_de": next_review,
        "recommended_actions": actionable[: int(pol.get("max_action_rows") or 8)],
        "worthwhile_buys": worthwhile_buys[: int(pol.get("max_action_rows") or 8)],
        "worthwhile_sells": worthwhile_sells[: int(pol.get("max_action_rows") or 8)],
        "capital_basis_de": _capital_basis_label(
            account_eur, broker, broker_economics, deployable_eur=deployable
        ),
        "broker_economics": broker_economics,
        "currency_context": broker_economics.get("currency"),
        "fee_policy": broker_economics.get("fees"),
        "rows": rows[: int(pol.get("max_action_rows") or 8)],
        "human_snapshot": {
            "total_value_eur": human.get("total_value_eur"),
            "cash_weight_pct": human.get("cash_weight_pct"),
            "positions_count": human.get("positions_count"),
        },
        "quote_fresh": quote_ok,
        "quote_reason": quote_reason,
        "signals_ok": signals_ok,
        "champion_ok": champion_ok,
        "us_session_open": us_open,
        "optimal_mode": "US_REGULAR_ACTIVE" if us_open else "OFF_HOURS_WATCH",
        "live_context": {
            "quote_as_of_utc": (quote_snapshot or {}).get("fetched_at_utc")
            or (quote_snapshot or {}).get("freshness", {}).get("as_of_utc"),
            "freshness_status": ((quote_snapshot or {}).get("freshness") or {}).get("status"),
        },
        "cost_risk": cost_risk,
    }


def _urgency_from_state(
    *,
    actionable: List[Dict[str, Any]],
    signals_ok: bool,
    quote_ok: bool,
    risk_on: bool,
    us_open: bool,
    exposure: Dict[str, Any],
) -> str:
    if not signals_ok:
        return "WATCH_ONLY"
    if us_open and not quote_ok:
        return "STALE_QUOTES"
    if not risk_on and exposure.get("over_invested"):
        return "HIGH"
    if not actionable:
        return "NONE"
    top = actionable[0]
    score = float(top.get("priority_score") or 0)
    if us_open and score >= 35:
        return "HIGH"
    if score >= 40 or len(actionable) >= 3:
        return "HIGH"
    if score >= 20:
        return "MEDIUM"
    return "LOW"


def _format_summary(
    *,
    actionable: List[Dict[str, Any]],
    urgency: str,
    drift_l1: float,
    scaling: Dict[str, Any],
    signals_ok: bool,
    quote_ok: bool,
    quote_reason: str,
    plan: Dict[str, Any],
    meta: Dict[str, Any],
    regime: str,
    exposure: Dict[str, Any],
    us_open: bool,
) -> str:
    if not signals_ok:
        return "Modell-Signale veraltet — nur beobachten, keine Rendite-Trades."
    if us_open and not quote_ok:
        return f"US-Session: {quote_reason} — «Aktualisieren» für frische Kurse."
    regime_bit = f"Regime {regime}" + (" · Risk-on" if meta.get("risk_on") else " · Risk-off")
    exp_bit = (
        f"Investiert {exposure.get('invested_pct')}% "
        f"/ Modell-Ziel {exposure.get('model_target_invested_pct')}%"
    )
    if not bool(meta.get("risk_on")):
        return f"{regime_bit}. Risk-off aktiv — keine Nachkäufe; {exp_bit}."
    if not actionable:
        if exposure.get("under_invested"):
            return (
                f"{regime_bit}. Unter Modell-Exposure ({exp_bit}) — "
                f"Cash nutzen (Drift {drift_l1:.1f} %)."
            )
        return f"{regime_bit}. Kein dringender Trade — Drift {drift_l1:.1f} % · {exp_bit}."
    buys = [a for a in actionable if a.get("action_code") == "NACHKAUF"]
    sells = [a for a in actionable if a.get("action_code") in ("REDUZIEREN", "ABBAUEN")]
    parts = [f"{'US-Session' if us_open else 'Außerhalb US'} · Handlungsbedarf ({urgency}) · {regime_bit}."]
    if buys:
        parts.append(
            "Nachkäufe (Rang/ Alpha): "
            + ", ".join(f"{b['symbol']} +{b['gap_eur']:.0f}€" for b in buys[:3])
            + "."
        )
    if sells:
        parts.append(
            "Reduzieren: " + ", ".join(f"{s['symbol']}" for s in sells[:2]) + "."
        )
    parts.append(exp_bit + f" · Signal {plan.get('signal_date') or '—'}.")
    return " ".join(parts)


def _next_review_hint(pol: Dict[str, Any], *, us_open: bool) -> str:
    from integrations.trading212.t212_exchange_session import format_next_open_de

    interval = effective_interval_minutes(pol)
    if us_open:
        return (
            f"US-Regular aktiv — Auto-Check alle {interval} Min mit frischen Kursen "
            f"(max {pol.get('quote_max_age_seconds_us_open', 120)}s)."
        )
    return f"US-Session zu — nächste Eröffnung {format_next_open_de()} · Check alle {interval} Min."


def _report_fingerprint(report: Dict[str, Any]) -> str:
    payload = {
        "signal": report.get("signal_date"),
        "urgency": report.get("urgency"),
        "trade_required": report.get("trade_required"),
        "risk_on": report.get("risk_on"),
        "exposure_gap": (report.get("exposure_check") or {}).get("exposure_gap_pct"),
        "actions": [
            (a.get("symbol"), a.get("action_code"), a.get("gap_eur"))
            for a in report.get("recommended_actions") or []
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _load_state(root: Path) -> Dict[str, Any]:
    path = Path(root) / _STATE_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(root: Path, doc: Dict[str, Any]) -> None:
    path = Path(root) / _STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, doc)


def should_run_periodic_reevaluation(root: Path, *, force: bool = False) -> bool:
    if force:
        return True
    pol = load_policy(root)
    if not pol.get("enabled"):
        return False
    st = _load_state(root)
    last = st.get("last_run_utc")
    if not last:
        return True
    try:
        prev = datetime.fromisoformat(str(last))
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    interval = timedelta(minutes=effective_interval_minutes(pol))
    return datetime.now(timezone.utc) - prev >= interval


def run_periodic_reevaluation(
    root: Path,
    *,
    broker: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    quote_snapshot: Optional[Dict[str, Any]] = None,
    champion_guard: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    if not should_run_periodic_reevaluation(root, force=force):
        path = root / _EVIDENCE_REL
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "status": "SKIPPED",
            "summary_de": "Nächster Check nach Intervall.",
            "us_session_open": _us_session_open(),
        }

    report = evaluate_live_portfolio_vs_champion(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snapshot,
        champion_guard=champion_guard,
    )
    st = _load_state(root)
    st["last_run_utc"] = _utc_now()
    st["last_fingerprint"] = _report_fingerprint(report)
    st["last_urgency"] = report.get("urgency")
    st["last_trade_required"] = report.get("trade_required")
    st["last_us_session_open"] = report.get("us_session_open")
    _save_state(root, st)
    atomic_write_json(root / _EVIDENCE_REL, report)
    return report


def write_reevaluation_evidence(root: Path, report: Dict[str, Any]) -> Path:
    path = Path(root) / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, report)
