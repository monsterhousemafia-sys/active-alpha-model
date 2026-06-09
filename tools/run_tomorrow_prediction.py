#!/usr/bin/env python3
"""Prepare tomorrow's stock signal: fresh prices + ML portfolio (profile-driven)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OPS_PATH = ROOT / "control" / "prediction_operations.json"
OUT_DIR = ROOT / "evidence" / "tomorrow_prediction"
PORTFOLIO_REL = Path("model_output_sp500_pit_t212") / "latest_target_portfolio.csv"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_champion_lineage(root: Path) -> Dict[str, Any]:
    """Align lineage + derived control artifacts with M9 strategic decision."""
    from analytics.strategic_governance import sync_strategic_governance

    return sync_strategic_governance(root)


def _load_ops(root: Path) -> Dict[str, Any]:
    if not OPS_PATH.is_file():
        raise FileNotFoundError(f"missing {OPS_PATH}")
    return json.loads(OPS_PATH.read_text(encoding="utf-8"))


def _top_picks(portfolio: Path, n: int = 15) -> List[Dict[str, Any]]:
    if not portfolio.is_file():
        return []
    import pandas as pd

    df = pd.read_csv(portfolio)
    weight_col = "target_weight" if "target_weight" in df.columns else df.columns[-1]
    ticker_col = "ticker" if "ticker" in df.columns else df.columns[0]
    df = df.sort_values(weight_col, ascending=False).head(n)
    return [
        {ticker_col: str(row[ticker_col]), weight_col: float(row[weight_col])}
        for _, row in df.iterrows()
    ]


def run_prediction(
    root: Path,
    *,
    profile: Optional[str] = None,
    force_prices: bool = True,
    allow_fallback: bool = True,
) -> Dict[str, Any]:
    from aa_config_env import load_aa_env
    from aa_operational_refinement import load_refinement_config, run_operational_refinement
    from aa_safe_io import atomic_write_json
    from tools.prediction_profiles import profile_env

    sync = sync_champion_lineage(root)
    ops = _load_ops(root)
    primary = profile or str(ops.get("active_profile") or "daily_alpha_h1")
    fallback = str(ops.get("fallback_profile") or "r3_w075_production")
    profiles_to_try = [primary]
    if allow_fallback and fallback not in profiles_to_try:
        profiles_to_try.append(fallback)

    last_error: Optional[str] = None
    used_profile: Optional[str] = None
    report: Dict[str, Any] = {}

    for prof in profiles_to_try:
        env = load_aa_env(root)
        env.update(profile_env(prof))
        if force_prices:
            env["AA_SKIP_DOWNLOAD_IF_CACHED"] = "0"
        cfg = load_refinement_config(root)
        cfg["force_prices"] = force_prices
        cfg["refresh_signal"] = True
        cfg["run_background_research"] = False
        try:
            ref_report = run_operational_refinement(root, env, cfg=cfg, log_print=True)
            report = ref_report.__dict__ if hasattr(ref_report, "__dict__") else {"ok": getattr(ref_report, "ok", False)}
            portfolio = root / PORTFOLIO_REL
            if ref_report.ok and portfolio.is_file():
                used_profile = prof
                break
            last_error = "refinement failed or portfolio missing"
        except Exception as exc:
            last_error = str(exc)
            continue

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    portfolio = root / PORTFOLIO_REL
    picks = _top_picks(portfolio)
    from aa_data_freshness import assess_daily_data

    data = assess_daily_data(root, load_aa_env(root))
    from analytics.live_profile_governance import sync_readiness_with_order_gate

    payload = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "ok": bool(used_profile and picks),
        "profile_used": used_profile,
        "profiles_attempted": profiles_to_try,
        "fallback_used": used_profile != primary if used_profile else False,
        "champion_sync": sync,
        "signal_date": data.signal_date.isoformat() if data.signal_date else None,
        "price_latest": data.price_latest.isoformat() if data.price_latest else None,
        "portfolio_path": str(PORTFOLIO_REL),
        "top_picks": picks,
        "last_error": last_error,
        "refinement": report,
        "disclaimer": "Research signal only — not investment advice; real-money gates unchanged.",
    }
    payload = sync_readiness_with_order_gate(root, payload)
    atomic_write_json(OUT_DIR / "latest.json", payload)
    atomic_write_json(ROOT / "control" / "prediction_readiness.json", payload)
    try:
        from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

        sync_live_execution_outcomes(root, refresh_history=True)
    except Exception:
        pass
    try:
        from analytics.competition_shadow import write_competition_shadow_snapshot

        write_competition_shadow_snapshot(root)
    except Exception:
        pass
    return payload


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Tomorrow prediction pipeline")
    p.add_argument("--profile", default=None, help="Override active profile")
    p.add_argument("--no-fallback", action="store_true")
    p.add_argument("--no-force-prices", action="store_true")
    args = p.parse_args()
    result = run_prediction(
        ROOT,
        profile=args.profile,
        force_prices=not args.no_force_prices,
        allow_fallback=not args.no_fallback,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
