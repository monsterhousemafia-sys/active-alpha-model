#!/usr/bin/env python3
"""Refresh latest_target_portfolio.csv using current AA_* config (signal mode)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from time import monotonic

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

os.environ.setdefault("AA_GUI", "0")
os.environ.setdefault("AA_NO_PLOT", "1")


def main() -> int:
    from aa_dashboard import RunDashboard
    from aa_config import BacktestConfig, apply_capital_curve_policy_to_config, enforce_reproducibility_inputs, parse_args
    from aa_config_env import build_backtest_argv, resolve_launcher_env
    from aa_live_daily_sync import sync_live_daily_for_predictions
    from aa_runtime import execute_run, print_run_summary

    env = resolve_launcher_env(_ROOT)
    os.environ.update(env)
    sync_live_daily_for_predictions(
        _ROOT,
        env,
        force_prices=False,
        refresh_signal=False,
        log_print=True,
    )
    argv = build_backtest_argv({**os.environ, **env})
    idx = argv.index("--mode")
    argv[idx + 1] = "signal"
    sys.argv = argv

    args = parse_args()
    cfg = BacktestConfig.from_args(args)
    cfg = apply_capital_curve_policy_to_config(cfg)
    enforce_reproducibility_inputs(cfg)
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dashboard = RunDashboard(enabled=False, title="Signal-Refresh", use_rich=False)
    result = execute_run(args, cfg, dashboard, out_dir=out_dir, run_started=monotonic())
    print_run_summary(result)
    portfolio = out_dir / "latest_target_portfolio.csv"
    if portfolio.is_file():
        print(f"[OK] Portfolio: {portfolio.resolve()}")
    else:
        print("[ERROR] latest_target_portfolio.csv fehlt", file=sys.stderr)
        return 1
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
