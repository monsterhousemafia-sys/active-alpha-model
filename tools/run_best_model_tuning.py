#!/usr/bin/env python3
"""Run a focused model-tuning matrix and apply the best variant to user config."""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_robustness_tests import (  # noqa: E402
    DEFAULT_SHARED_CACHE,
    RESULTS_DIR,
    VARIANTS,
    partition_variants,
    score,
    variant_is_complete,
    variant_output_dir,
)
from aa_subprocess_runner import run_logged_subprocess  # noqa: E402

TUNING_BASE = [
    sys.executable,
    "active_alpha_model.py",
    "--mode",
    "backtest",
    "--ticker-source",
    "sp500_pit",
    "--membership-file",
    "ticker_membership.csv",
    "--membership-mode",
    "strict",
    "--benchmark",
    "SPY",
    "--start",
    "2012-01-01",
    "--universe-mode",
    "diy_pit_liquidity",
    "--fee-model",
    "trading212_us",
    "--backtest-capital",
    "100000",
    "--research-backtest-capital",
    "100000",
    "--execution-policy-mode",
    "capital_curve",
    "--max-gross-exposure",
    "1.0",
    "--n-jobs",
    "auto",
    "--cpu-cores",
    "16",
    "--system-ram-gb",
    "64",
    "--parallel-profile",
    "high",
    "--parallel-backtest-backend",
    "thread",
    "--reuse-feature-cache",
    "--reuse-prediction-cache",
    "--skip-download-if-cached",
    "--no-naive-momentum-baseline",
    "--no-statistical-diagnostics",
    "--no-custom-benchmarks",
    "--skip-feature-parquet-write",
    "--no-plot",
    "--no-naive-overlap",
    "--plain-progress",
    "--no-gui",
    "--cluster-mode",
    "static",
    "--risk-off-selection-mode", "mom_blend_blend",
    "--risk-off-momentum-variant", "mom_blend_top12",
    "--risk-off-momentum-weight", "0.70",
    "--risk-off-gate-mode", "momentum_rescue",
    "--risk-off-momentum-rescue-quantile", "0.70",
]

# High-impact variants within the existing architecture (no new ML backends).
DEFAULT_ONLY = (
    "core_alpha_return_staticcluster_spycompletion_k15_pos12,"
    "threshold_tail005_fx0_slip2_top100_beta125_k12,"
    "_ml_only,_gbm_only,_rank_only,_elastic_only,"
    "_k8,_k20,_k30,"
    "tune_trainyears"
)

TRAIN_YEARS_VARIANTS: List[Dict[str, Any]] = [
    {
        "name": "tune_trainyears5_ensemble_k15",
        "policy": "threshold",
        "fx": 0,
        "slip": 2,
        "topn": 100,
        "beta": 1.25,
        "top_k": 15,
        "max_position": 0.12,
        "model_mode": "ensemble",
        "tail_prune": True,
        "residual_floor": 0.005,
        "soft_cap": 35,
        "hard_cap": 45,
        "description": "Tuning: train_years=5, ensemble, k15.",
        "extra_args": ["--train-years", "5"],
    },
    {
        "name": "tune_trainyears9_ensemble_k15",
        "policy": "threshold",
        "fx": 0,
        "slip": 2,
        "topn": 100,
        "beta": 1.25,
        "top_k": 15,
        "max_position": 0.12,
        "model_mode": "ensemble",
        "tail_prune": True,
        "residual_floor": 0.005,
        "soft_cap": 35,
        "hard_cap": 45,
        "description": "Tuning: train_years=9, ensemble, k15.",
        "extra_args": ["--train-years", "9"],
    },
]


def build_tuning_command(v: Dict[str, object], shared_cache_dir: Path) -> List[str]:
    cmd = list(TUNING_BASE)
    name = str(v["name"])
    out_dir = RESULTS_DIR / name
    cmd += ["--trading212-policy", str(v.get("policy", "threshold"))]
    cmd += ["--trading212-fx-bps", str(v.get("fx", 0))]
    cmd += ["--slippage-bps", str(v.get("slip", 2))]
    cmd += ["--market-impact-bps", str(v.get("impact", 0))]
    cmd += ["--universe-top-n", str(v.get("topn", 100))]
    cmd += ["--max-portfolio-beta", str(v.get("beta", 1.25))]
    cmd += ["--beta-cap-mode", str(v.get("beta_cap_mode", "dynamic"))]
    cmd += ["--cluster-constraint-mode", str(v.get("cluster_constraint_mode", "static_only"))]
    cmd += ["--cash-filler-mode", str(v.get("cash_filler_mode", "benchmark_completion"))]
    cmd += ["--benchmark-completion-ticker", str(v.get("benchmark_completion_ticker", "SPY"))]
    cmd += ["--benchmark-completion-max-weight", str(v.get("benchmark_completion_max_weight", 0.25))]
    cmd += ["--top-k", str(v.get("top_k", 15))]
    cmd += ["--alpha-model-mode", str(v.get("model_mode", "ensemble"))]
    cmd += ["--shared-cache-dir", str(shared_cache_dir)]
    cmd += ["--out-dir", str(out_dir)]
    if "max_position" in v:
        cmd += ["--max-position", str(v["max_position"])]
    if bool(v.get("tail_prune", False)):
        cmd += [
            "--tail-prune-enabled",
            "--residual-weight-floor",
            str(v.get("residual_floor", 0.005)),
            "--max-n-positions-soft",
            str(v.get("soft_cap", 35)),
            "--max-n-positions-hard",
            str(v.get("hard_cap", 45)),
        ]
    for arg in v.get("extra_args", []):
        cmd.append(str(arg))
    return cmd


def _row_from_variant(v: Dict[str, object], shared_cache_dir: Path, *, returncode: int) -> Dict[str, object]:
    from run_robustness_tests import parse_benchmark_comparison, parse_factor_regression, parse_report

    name = str(v["name"])
    out_dir = RESULTS_DIR / name
    cmd = build_tuning_command(v, shared_cache_dir)
    row: Dict[str, object] = {
        "name": name,
        "description": v.get("description", ""),
        "returncode": returncode,
        "policy": v.get("policy", ""),
        "fx_bps": v.get("fx", ""),
        "slippage_bps": v.get("slip", ""),
        "universe_top_n": v.get("topn", ""),
        "max_portfolio_beta": v.get("beta", ""),
        "top_k": v.get("top_k", ""),
        "alpha_model_mode": v.get("model_mode", "ensemble"),
        "tail_prune": bool(v.get("tail_prune", False)),
        "max_position": v.get("max_position", ""),
        "out_dir": str(out_dir),
        "command": " ".join(cmd),
    }
    row.update(parse_report(out_dir / "backtest_report.txt"))
    row.update(parse_benchmark_comparison(out_dir / "benchmark_comparison.csv"))
    row.update(parse_factor_regression(out_dir / "factor_proxy_regression.csv"))
    sc, flag = score(row)
    row["robustness_score"] = sc
    row["status"] = "FAIL" if returncode != 0 else flag
    return row


def _terminate_proc_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def _wait_for_tuning_proc(
    proc: subprocess.Popen,
    out_dir: Path,
    *,
    grace_seconds: int = 45,
    poll_seconds: float = 5.0,
) -> int:
    """Wait for backtest subprocess; avoid hanging forever on stale worker processes."""
    while True:
        rc = proc.poll()
        if rc is not None:
            return int(rc)
        if variant_is_complete(out_dir):
            try:
                return int(proc.wait(timeout=grace_seconds))
            except subprocess.TimeoutExpired:
                print(
                    f"[WARN] {out_dir.name}: outputs complete but process hung; terminating tree",
                    flush=True,
                )
                _terminate_proc_tree(proc)
                return 0
        time.sleep(poll_seconds)


def run_tuning_variant(v: Dict[str, object], shared_cache_dir: Path) -> Dict[str, object]:
    name = str(v["name"])
    out_dir = RESULTS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_tuning_command(v, shared_cache_dir)
    print(f"[RUN] {name}", flush=True)
    returncode = run_logged_subprocess(cmd, cwd=ROOT, out_dir=out_dir, is_complete=variant_is_complete)
    return _row_from_variant(v, shared_cache_dir, returncode=returncode)


def select_variants(only: str) -> List[Dict[str, Any]]:
    needles = [x.strip().lower() for x in only.split(",") if x.strip()]
    selected = list(VARIANTS) + list(TRAIN_YEARS_VARIANTS)
    if needles:
        selected = [v for v in selected if any(n in str(v.get("name", "")).lower() for n in needles)]
    # de-dupe by name
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for v in selected:
        name = str(v["name"])
        if name in seen:
            continue
        seen.add(name)
        out.append(v)
    return out


def collect_completed_rows(variants: List[Dict[str, Any]], shared_cache_dir: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for v in variants:
        out_dir = variant_output_dir(str(v["name"]))
        if not variant_is_complete(out_dir):
            continue
        rows.append(_row_from_variant(v, shared_cache_dir, returncode=0))
    return rows


def rank_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    ok = [r for r in rows if int(r.get("returncode", 1)) == 0]
    return sorted(ok, key=lambda r: float(r.get("robustness_score", -999)), reverse=True)


def apply_best_to_user_config(best: Dict[str, object], *, user_config: Path) -> None:
    from aa_config_env import load_aa_env

    mapping = {
        "AA_TRADING212_POLICY": str(best.get("policy", "threshold")),
        "AA_ALPHA_MODEL_MODE": str(best.get("alpha_model_mode", "ensemble")),
        "AA_TOP_K": str(int(float(best.get("top_k", 15)))),
        "AA_UNIVERSE_TOP_N": str(int(float(best.get("universe_top_n", 100)))),
        "AA_MAX_PORTFOLIO_BETA": str(best.get("max_portfolio_beta", "1.25")),
        "AA_SLIPPAGE_BPS": str(int(float(best.get("slippage_bps", 2)))),
        "AA_TRADING212_FX_BPS": str(int(float(best.get("fx_bps", 0)))),
    }
    if best.get("max_position") is not None:
        mapping["AA_MAX_POSITION"] = str(best.get("max_position"))
    cmd = str(best.get("command", ""))
    m = re.search(r"--train-years\s+(\d+)", cmd)
    if m:
        mapping["AA_TRAIN_YEARS"] = m.group(1)
    if str(best.get("tail_prune", "")).lower() in {"true", "1"} or best.get("tail_prune") is True:
        mapping["AA_TAIL_PRUNE_ENABLED"] = "J"
    text = user_config.read_text(encoding="utf-8", errors="ignore")
    for key, val in mapping.items():
        needle = f'set "{key}='
        replaced = False
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith(needle):
                lines[i] = f'set "{key}={val}"'
                replaced = True
                break
        text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        if not replaced:
            text += f'\nset "{key}={val}"'
    if mapping.get("AA_ALPHA_MODEL_MODE") or mapping.get("AA_TRAIN_YEARS"):
        if 'set "AA_FORCE_REBUILD_PREDICTIONS=' in text:
            text = re.sub(
                r'^set "AA_FORCE_REBUILD_PREDICTIONS=.*"$',
                'set "AA_FORCE_REBUILD_PREDICTIONS=1"',
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            text += '\nset "AA_FORCE_REBUILD_PREDICTIONS=1"'
    user_config.write_text(text, encoding="utf-8")
    _ = load_aa_env  # keep import validated


def write_summary(rows: List[Dict[str, object]], path: Path) -> None:
    ranked = rank_rows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in ranked:
            w.writerow(r)
    txt = path.with_suffix(".txt")
    lines = ["Model tuning summary", "====================", ""]
    for r in ranked[:10]:
        lines.append(
            f"- {r.get('name')}: score={float(r.get('robustness_score', 0)):.4f}, "
            f"CAGR={float(r.get('strategy_cagr', 0)):.2%}, IR={float(r.get('information_ratio', 0)):.3f}, "
            f"DD={float(r.get('strategy_max_drawdown', 0)):.2%}, mode={r.get('alpha_model_mode')}, top_k={r.get('top_k')}"
        )
    txt.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Focused Active Alpha model tuning within existing architecture.")
    p.add_argument("--only", default=DEFAULT_ONLY, help="Comma-separated variant name substrings.")
    p.add_argument("--parallel-jobs", type=int, default=2)
    p.add_argument("--skip-completed", action="store_true", default=True)
    p.add_argument("--apply", action="store_true", help="Write best variant into active_alpha_user_config.bat")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--shared-cache-dir", default=str(DEFAULT_SHARED_CACHE))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    selected = select_variants(args.only)
    pending, skipped = partition_variants(selected, skip_completed=bool(args.skip_completed))
    shared = Path(args.shared_cache_dir)
    shared.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] selected={len(selected)} pending={len(pending)} skipped={len(skipped)}", flush=True)
    if args.dry_run:
        for v in pending:
            print(" ".join(build_tuning_command(v, shared)))
        return 0
    rows: List[Dict[str, object]] = []
    jobs = max(1, min(int(args.parallel_jobs), 4))
    if pending:
        if jobs == 1 or len(pending) == 1:
            rows.extend(run_tuning_variant(v, shared) for v in pending)
        else:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                futs = {pool.submit(run_tuning_variant, v, shared): v for v in pending}
                for fut in as_completed(futs):
                    rows.append(fut.result())
    rows.extend(collect_completed_rows(skipped, shared))
    summary = RESULTS_DIR / "model_tuning_summary.csv"
    write_summary(rows, summary)
    ranked = rank_rows(rows)
    if not ranked:
        print("[ERROR] No successful tuning runs.", flush=True)
        return 1
    best = ranked[0]
    print(f"[OK] Best: {best.get('name')} score={float(best.get('robustness_score', 0)):.4f}", flush=True)
    print(f"[OK] Summary: {summary}", flush=True)
    if args.apply:
        cfg = ROOT / "active_alpha_user_config.bat"
        apply_best_to_user_config(best, user_config=cfg)
        print(f"[OK] Applied best variant to {cfg}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
