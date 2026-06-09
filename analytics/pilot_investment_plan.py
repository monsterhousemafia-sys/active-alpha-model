"""Investment plan from champion model, scaled to Trading 212 cash."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from analytics.pilot_pick_rationale import METHODOLOGY_DE, explain_primary_pick, rationale_one_liner
from analytics.pilot_today_pick import BLOCKED_SYMBOLS, _load_portfolio_picks, _out_dir
from analytics.prediction_operations import (
    budget_config,
    format_plan_summary_de,
    plan_metadata,
    resolve_operational_signal_id,
)

CHAMPION_ID = "R3_w075_q065_noexit"
CASH_BUFFER_PCT = 5.0  # legacy default; live plans use budget_config(root)


def resolve_plan_signal_id(root: Path) -> str:
    """Operational signal identity for live portfolio scaling."""
    try:
        return resolve_operational_signal_id(root)
    except Exception:
        return CHAMPION_ID


def _load_allocation_config(root: Path) -> List[Dict[str, Any]]:
    path = root / "paper/config/p16c_cost_adjusted_initial_allocation_500eur.json"
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows: List[Dict[str, Any]] = []
    for pos in doc.get("positions") or []:
        sym = str(pos.get("symbol_reference") or "").upper().strip()
        if not sym or sym in BLOCKED_SYMBOLS:
            continue
        w = float(pos.get("normalized_weight_pct") or pos.get("displayed_weight_pct") or 0)
        rows.append(
            {
                "symbol": sym,
                "model_weight_pct": round(w, 2),
                "reference_target_eur": float(pos.get("cost_adjusted_target_eur") or 0),
            }
        )
    return rows


def build_investment_plan(
    root: Path,
    available_cash_eur: float,
    *,
    investable_eur: float | None = None,
    budget_source: str | None = None,
) -> Dict[str, Any]:
    """Scale model weights to T212 cash; prefer explicit R3 investable when provided."""
    root = Path(root)
    cash = max(0.0, float(available_cash_eur or 0))
    bcfg = budget_config(root)
    buffer_pct = float(bcfg.get("cash_buffer_pct", 5.0))
    min_pos = float(bcfg.get("min_position_eur") or 0)
    excluded = set(BLOCKED_SYMBOLS) | set(bcfg.get("exclude_symbols") or [])
    signal_id = resolve_plan_signal_id(root)
    try:
        from analytics.pilot_day_trading_policy import policy_section

        max_sym = int(policy_section(root, "reevaluation").get("max_model_symbols") or 50)
    except Exception:
        max_sym = 50
    picks = _load_portfolio_picks(root, max_symbols=max_sym)
    if not picks:
        picks = [
            {
                "symbol": str(r["symbol"]),
                "model_weight_pct": float(r["model_weight_pct"]),
                "alpha_lcb": 0.0,
                "signal_date": "",
            }
            for r in _load_allocation_config(root)
        ]

    signal_date = ""
    if picks:
        signal_date = str(picks[0].get("signal_date") or "")[:10]
    if not signal_date:
        meta = _out_dir(root) / "latest_target_portfolio.csv"
        if meta.is_file():
            try:
                import pandas as pd

                df = pd.read_csv(meta, nrows=1)
                if "signal_date" in df.columns:
                    signal_date = str(df.iloc[0]["signal_date"])[:10]
            except Exception:
                pass

    if investable_eur is not None:
        investable = round(max(0.0, float(investable_eur)), 2)
        basis = budget_source or "r3_investable"
    else:
        investable = round(cash * (1.0 - buffer_pct / 100.0), 2)
        basis = budget_source or "T212_availableToTrade"
    total_w = sum(float(p.get("model_weight_pct") or 0) for p in picks)
    allocations: List[Dict[str, Any]] = []
    for p in picks:
        sym = str(p.get("symbol") or "").upper()
        if not sym or sym in excluded:
            continue
        share = (float(p.get("model_weight_pct") or 0) / total_w) if total_w > 0 else 0.0
        target_gross = round(investable * share, 2) if investable > 0 else 0.0
        from integrations.trading212.t212_fee_economics import (
            is_notional_worth_trading,
            net_buy_target_after_costs,
        )

        fee_adj = net_buy_target_after_costs(target_gross, root)
        target = float(fee_adj["net_target_eur"])
        worth, _ = is_notional_worth_trading(target, root)
        if not worth:
            continue
        if min_pos > 0 and target < min_pos:
            continue
        rationale = explain_primary_pick(
            root,
            symbol=sym,
            plan_row={
                "symbol": sym,
                "model_weight_pct": float(p.get("model_weight_pct") or 0),
                "target_eur": target,
                "alpha_lcb": float(p.get("alpha_lcb") or 0),
            },
        )
        allocations.append(
            {
                "symbol": sym,
                "model_weight_pct": float(p.get("model_weight_pct") or 0),
                "target_eur": target,
                "target_eur_gross": target_gross,
                "estimated_one_way_cost_eur": fee_adj.get("estimated_one_way_cost_eur"),
                "alpha_lcb": float(p.get("alpha_lcb") or 0),
                "signal_date": signal_date,
                "side": "BUY",
                "pick_rationale": rationale,
                "rationale_de": rationale_one_liner(rationale, max_len=160),
            }
        )

    primary = allocations[0] if allocations else {}
    if primary:
        primary.setdefault(
            "rationale_de",
            (primary.get("pick_rationale") or {}).get("summary_de") or "",
        )
    meta = plan_metadata(root, available_cash_eur=cash, investable_eur=investable)
    summary_de = format_plan_summary_de(
        root,
        n_symbols=len(allocations),
        investable_eur=investable,
        cash_eur=cash,
    )
    return {
        "champion_id": signal_id,
        "signal_profile": meta.get("prediction_profile"),
        "budget_mode": meta.get("budget_mode"),
        "budget_source": meta.get("budget_source"),
        "signal_date": signal_date,
        "available_cash_eur": round(cash, 2),
        "planning_basis": basis,
        "r3_investable": investable_eur is not None,
        "investable_eur": investable,
        "cash_buffer_pct": buffer_pct,
        "methodology_de": METHODOLOGY_DE,
        "summary_de": summary_de,
        "strategy_de": summary_de,
        "prediction_meta": meta,
        "primary_rationale_de": (primary.get("rationale_de") or "") if primary else "",
        "primary_action": primary,
        "allocations": allocations,
        "executable": bool(primary.get("symbol")) and investable >= 10.0,
    }


def ensure_plan_symbols_in_scope(root: Path, plan: Dict[str, Any]) -> bool:
    """Add plan + full champion universe to managed scope (incl. MU) so orders are not blocked."""
    from execution.confirmed_live.managed_scope_service import load_managed_scope, set_managed_scope
    from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

    root = Path(root)
    syms = [str(a.get("symbol") or "").upper() for a in (plan.get("allocations") or []) if a.get("symbol")]
    syms = sorted(set(syms) | set(CHAMPION_SYMBOLS))
    if not syms:
        return False
    sc = load_managed_scope(root)
    existing = [str(x).upper() for x in (sc.get("managed_instruments") or [])]
    merged = sorted(set(existing) | set(syms))
    if merged == existing:
        return False
    set_managed_scope(
        root,
        managed_instruments=merged,
        authorized_capital_eur=float(sc.get("authorized_capital_eur") or 0),
    )
    return True


def _merge_plan_pipeline_metadata(root: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """King/T212-Pipeline-Felder erhalten — kein Überschreiben durch Legacy-Refresh."""
    path = Path(root) / "evidence/pilot_investment_plan_latest.json"
    if not path.is_file():
        return plan
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return plan
    if not isinstance(prior, dict):
        return plan
    preserve_keys = (
        "t212_live",
        "t212_last_sync_utc",
        "plan_capital_eur",
        "plan_capital_basis",
        "plan_pipeline_de",
        "pipeline_run_id",
        "pipeline_synced",
        "pipeline_partial",
        "pipeline_warnings",
        "king_plan_merged",
        "king_boost_applied",
        "king_merged_at_utc",
        "rebalanced_to_t212",
        "t212_positions_count",
        "t212_rebalanced_at_utc",
        "rebalance_mode_de",
    )
    out = dict(plan)
    for key in preserve_keys:
        if out.get(key) is None and prior.get(key) is not None:
            out[key] = prior[key]
    return out


def write_plan_evidence(root: Path, plan: Dict[str, Any]) -> Path:
    from aa_safe_io import atomic_write_json

    root = Path(root)
    path = root / "evidence/pilot_investment_plan_latest.json"
    atomic_write_json(path, _merge_plan_pipeline_metadata(root, plan))
    return path
