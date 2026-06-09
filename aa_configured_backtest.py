"""In-process configured backtest for Marktanalyse launcher (single window)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional


def run_configured_backtest(root: Path, dashboard: Any = None) -> Any:
    from aa_config_env import build_backtest_argv, resolve_launcher_env
    from aa_ui_pump import pump_ui
    from aa_runtime import RunResult, execute_run, print_run_summary

    pump_ui(force=True)
    env = resolve_launcher_env(root)
    pump_ui(force=True)
    from aa_qt_render import configure_cpu_compute_env

    configure_cpu_compute_env()
    os.environ.update(env)
    os.environ["AA_LAUNCHER_READY"] = "1"
    os.environ["AA_GUI"] = "1"

    argv = build_backtest_argv({**os.environ, **env})
    old_argv = sys.argv
    sys.argv = argv
    try:
        from aa_config import BacktestConfig, apply_capital_curve_policy_to_config, enforce_reproducibility_inputs, parse_args

        args = parse_args()
        cfg = BacktestConfig.from_args(args)
        cfg = apply_capital_curve_policy_to_config(cfg)
        enforce_reproducibility_inputs(cfg)
        from aa_frozen import apply_frozen_runtime_config

        apply_frozen_runtime_config(cfg)
        out_dir = Path(cfg.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if dashboard is not None:
            dashboard.start(total_phases=5, out_dir=out_dir, title="Marktanalyse")
            dashboard.ok("Backtest-Pipeline startet …")
            pump_ui(force=True)
        if dashboard is None:
            from aa_dashboard_qt import create_dashboard, should_use_gui

            dashboard = create_dashboard(
                enabled=True,
                title="Marktanalyse",
                prefer_gui=should_use_gui(args),
            )
            dashboard.start(total_phases=5, out_dir=out_dir)

        from time import monotonic

        run_started = monotonic()
        result = execute_run(args, cfg, dashboard, out_dir=out_dir, run_started=run_started)
        print_run_summary(result)
        return result
    finally:
        sys.argv = old_argv
