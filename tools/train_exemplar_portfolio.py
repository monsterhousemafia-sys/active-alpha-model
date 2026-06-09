"""Walk-forward ML training on real data for the 10k exemplar stock portfolio (no cash filler)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXEMPLAR_CAPITAL = "10000"


def main() -> int:
    from aa_config_env import build_backtest_argv, load_aa_env

    parser = argparse.ArgumentParser(description="Train exemplar portfolio on daily data")
    parser.add_argument(
        "--fictive",
        action="store_true",
        help="Use fictive tagesaktuelle OHLCV (AA_PRICE_DATA_SOURCE=fictive)",
    )
    parser.add_argument(
        "--internet",
        action="store_true",
        help="Force internet/yfinance download (AA_PRICE_DATA_SOURCE=internet)",
    )
    args = parser.parse_args()

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    env = load_aa_env(ROOT)
    if args.fictive:
        env["AA_PRICE_DATA_SOURCE"] = "fictive"
    elif args.internet:
        env["AA_PRICE_DATA_SOURCE"] = "internet"
    elif str(env.get("AA_PRICE_DATA_SOURCE", "")).strip().lower() not in {
        "fictive",
        "mock",
        "synthetic",
        "internet",
        "live",
    }:
        env.setdefault("AA_PRICE_DATA_SOURCE", "fictive")

    env["AA_RUN_MODE"] = "backtest"
    env["AA_EXEMPLAR_PORTFOLIO_CAPITAL"] = EXEMPLAR_CAPITAL
    env["AA_BACKTEST_CAPITAL"] = EXEMPLAR_CAPITAL
    env["AA_RESEARCH_BACKTEST_CAPITAL"] = EXEMPLAR_CAPITAL
    env["AA_CASH_FILLER_MODE"] = "off"
    env["AA_BENCHMARK_COMPLETION_MAX_WEIGHT"] = "0"
    env["AA_FORCE_REBUILD_PREDICTIONS"] = "1"
    env["AA_REUSE_PREDICTION_CACHE"] = "0"
    env["AA_REUSE_FEATURE_CACHE"] = env.get("AA_REUSE_FEATURE_CACHE", "1")
    env["AA_SKIP_DOWNLOAD_IF_CACHED"] = "0"

    source = str(env.get("AA_PRICE_DATA_SOURCE", "fictive"))
    print(f"Price data source: {source}")

    from aa_live_daily_sync import sync_live_daily_for_predictions

    print("Syncing daily OHLCV for portfolio + universe tickers …")
    sync = sync_live_daily_for_predictions(
        ROOT,
        env,
        force_prices=True,
        refresh_signal=False,
        log_print=True,
    )
    if not sync.ok:
        print("[WARN] Daily sync incomplete — training continues with best available cache")

    argv = build_backtest_argv(env)
    cmd = [str(py), str(ROOT / argv[0]), *argv[1:]]

    log_path = ROOT / "evidence" / "exemplar_portfolio_train.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Training exemplar portfolio (capital={EXEMPLAR_CAPITAL} USD, cash_filler=off)")
    print(f"Output: {env.get('AA_BACKTEST_OUT_DIR', 'model_output_sp500_pit_t212')}")
    print(f"Log: {log_path}")

    proc_env = os.environ.copy()
    proc_env.update(env)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(" ".join(cmd) + "\n\n")
        log.flush()
        proc = subprocess.run(cmd, cwd=ROOT, env=proc_env, stdout=log, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        print(f"Training failed with exit code {proc.returncode}")
        return proc.returncode
    print("Training completed.")

    from aa_operational_refinement import load_refinement_config, run_operational_refinement

    ref_cfg = load_refinement_config(ROOT)
    ref_cfg["force_prices"] = False
    ref_cfg["refresh_signal"] = True
    ref_cfg["run_background_research"] = False
    print("Post-training operational refinement (Signal + R3 + Cockpit) …")
    ref = run_operational_refinement(ROOT, env, cfg=ref_cfg, log_print=True)
    return 0 if ref.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
