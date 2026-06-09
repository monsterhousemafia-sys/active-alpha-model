#!/usr/bin/env python3
"""R5 matrix base (full backtest) + cost stress via complete path simulations."""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_alpha_vs_momentum import (  # noqa: E402
    AlphaMomentumThresholds,
    alpha_beats_momentum_significantly,
    extract_alpha_vs_momentum,
    parse_report_sections,
    score_alpha_vs_momentum,
)
from aa_subprocess_runner import noninteractive_env, run_logged_subprocess  # noqa: E402
from tools.run_r5_challenger_pipeline import (  # noqa: E402
    R5_BASE,
    R5_KEY,
    SHARED_CACHE,
    build_r5_command,
    write_control_files,
)

VALIDATION_ROOT = ROOT / "validation_runs"
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")

COST_SCENARIOS: List[Dict[str, str]] = [
    {"suffix": "cost_s2_i0", "slippage_bps": "2", "market_impact_bps": "0"},
    {"suffix": "cost_s5_i0", "slippage_bps": "5", "market_impact_bps": "0"},
    {"suffix": "cost_s10_i5", "slippage_bps": "10", "market_impact_bps": "5"},
    {"suffix": "cost_s20_i10", "slippage_bps": "20", "market_impact_bps": "10"},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_pass(out_dir: Path) -> bool:
    pointer = out_dir / "latest_validated_run.json"
    if not pointer.is_file():
        return False
    try:
        meta = json.loads(pointer.read_text(encoding="utf-8"))
        return str(meta.get("integrity_status", meta.get("status", ""))) == "PASS"
    except Exception:
        return False


def _scenario_dir(stamp: str, suffix: str) -> Path:
    if suffix == "base":
        return VALIDATION_ROOT / f"{stamp}_{R5_KEY}"
    return VALIDATION_ROOT / f"{stamp}_{R5_KEY}_{suffix}"


def run_full_scenario(
    *,
    stamp: str,
    suffix: str,
    variant: Dict[str, str],
    cpu_cores: int,
    price_source: str,
    skip_completed: bool,
) -> Dict[str, Any]:
    out_dir = _scenario_dir(stamp, suffix)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{R5_KEY}_{suffix}" if suffix != "base" else R5_KEY
    thresholds = AlphaMomentumThresholds()

    if skip_completed and _is_pass(out_dir):
        cmp = extract_alpha_vs_momentum(out_dir)
        beats, reason = alpha_beats_momentum_significantly(cmp, thresholds)
        sections = parse_report_sections(out_dir / "backtest_report.txt")
        return {
            "name": name,
            "suffix": suffix,
            "status": "SKIP",
            "integrity": "PASS",
            "beats_momentum": beats,
            "gate_reason": reason,
            "alpha_score": score_alpha_vs_momentum(cmp),
            "strategy_sharpe": sections.get("strategy", {}).get("sharpe_0rf"),
            "strategy_cagr": sections.get("strategy", {}).get("cagr"),
            "out_dir": str(out_dir),
        }

    cmd = build_r5_command(
        variant,
        out_dir=out_dir,
        cpu_cores=cpu_cores,
        price_source=price_source,
        full_reporting=True,
    )
    env = noninteractive_env({"AA_PRICE_DATA_SOURCE": price_source, "AA_CPU_CORES": str(cpu_cores)})
    print(f"[RUN] {name} slip={variant.get('slippage_bps')} impact={variant.get('market_impact_bps')}", flush=True)
    t0 = time.monotonic()
    rc = run_logged_subprocess(cmd, cwd=ROOT, out_dir=out_dir, is_complete=_is_pass, env=env)
    elapsed = time.monotonic() - t0
    integrity = "PASS" if _is_pass(out_dir) else "FAIL"
    cmp = extract_alpha_vs_momentum(out_dir)
    beats, reason = alpha_beats_momentum_significantly(cmp, thresholds)
    sections = parse_report_sections(out_dir / "backtest_report.txt")
    return {
        "name": name,
        "suffix": suffix,
        "status": "PASS" if integrity == "PASS" and rc == 0 else "FAIL",
        "returncode": rc,
        "integrity": integrity,
        "beats_momentum": beats,
        "gate_reason": reason,
        "alpha_score": score_alpha_vs_momentum(cmp),
        "alpha_vs_momentum": cmp.as_dict() if cmp else None,
        "strategy_sharpe": sections.get("strategy", {}).get("sharpe_0rf"),
        "strategy_cagr": sections.get("strategy", {}).get("cagr"),
        "elapsed_s": round(elapsed, 1),
        "out_dir": str(out_dir),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="R5 full matrix base + cost stress")
    p.add_argument("--stamp", default="", help="Stamp prefix for validation_runs dirs")
    p.add_argument("--internet", action="store_true", default=True)
    p.add_argument("--fictive", action="store_true")
    p.add_argument("--parallel-jobs", type=int, default=2)
    p.add_argument("--skip-completed", action="store_true", default=True)
    p.add_argument("--no-skip-completed", action="store_true")
    p.add_argument("--skip-base", action="store_true", help="Skip base if cost_s2_i0 already PASS")
    args = p.parse_args()

    skip = bool(args.skip_completed) and not args.no_skip_completed
    price_source = "fictive" if args.fictive else "internet"
    stamp = args.stamp.strip() or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parallel = max(1, min(int(args.parallel_jobs), 3))
    cpu_cores = max(4, 16 // parallel)

    if price_source == "internet" and not args.skip_base:
        from tools.run_r3_parallel_tuning import seed_r3_price_cache  # noqa: WPS433

        seed_r3_price_cache(price_source="internet")

    results: List[Dict[str, Any]] = []

    # Phase 1: matrix base (s2_i0 equivalent at default costs)
    base_variant = dict(R5_BASE)
    base_variant.update({"slippage_bps": "2", "market_impact_bps": "0"})
    if not args.skip_base:
        results.append(
            run_full_scenario(
                stamp=stamp,
                suffix="base",
                variant=base_variant,
                cpu_cores=cpu_cores,
                price_source=price_source,
                skip_completed=skip,
            )
        )

    # Phase 2: cost stress (full path re-simulation per scenario)
    scenarios = []
    for cs in COST_SCENARIOS:
        v = dict(R5_BASE)
        v.update(cs)
        scenarios.append((cs["suffix"], v))

    if parallel <= 1:
        for suffix, variant in scenarios:
            results.append(
                run_full_scenario(
                    stamp=stamp,
                    suffix=suffix,
                    variant=variant,
                    cpu_cores=cpu_cores,
                    price_source=price_source,
                    skip_completed=skip,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futs = {
                pool.submit(
                    run_full_scenario,
                    stamp=stamp,
                    suffix=suffix,
                    variant=variant,
                    cpu_cores=cpu_cores,
                    price_source=price_source,
                    skip_completed=skip,
                ): suffix
                for suffix, variant in scenarios
            }
            for fut in as_completed(futs):
                results.append(fut.result())

    passes = [r for r in results if r.get("integrity") == "PASS"]
    cost_passes = [r for r in passes if r.get("suffix") != "base"]
    payload = {
        "generated_at_utc": _utc_now(),
        "stamp": stamp,
        "price_source": price_source,
        "mode": "full_backtest",
        "matrix_base": next((r for r in results if r.get("suffix") == "base"), None),
        "cost_stress_results": [r for r in results if r.get("suffix") != "base"],
        "all_results": results,
        "cost_stress_pass_count": len(cost_passes),
        "cost_stress_total": len(COST_SCENARIOS),
        "target_met": len(cost_passes) == len(COST_SCENARIOS),
    }
    summary_path = VALIDATION_ROOT / "r5_challenger" / "r5_matrix_cost_stress_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    matrix_summary = VALIDATION_ROOT / f"{stamp}_summary.json"
    matrix_summary.write_text(
        json.dumps(
            {
                "stamp": stamp,
                "mode": "full_backtest",
                "runs": results,
                "pass_count": len(passes),
                "fail_count": len(results) - len(passes),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    status_path = ROOT / "control" / "r5_challenger_status.json"
    prior: Dict[str, Any] = {}
    if status_path.is_file():
        try:
            prior = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    merged = {
        **prior,
        "matrix_base_full": payload.get("matrix_base"),
        "cost_stress_full": payload,
        "cost_stress_stamp": stamp,
        "cost_stress_complete": payload["target_met"],
    }
    best_dir = (payload.get("matrix_base") or {}).get("out_dir") or prior.get("internet_validation", {}).get("out_dir", "")
    write_control_files(merged, best={"out_dir": best_dir})

    print(f"[OK] {summary_path}", flush=True)
    print(f"[OK] Cost stress PASS {len(cost_passes)}/{len(COST_SCENARIOS)}", flush=True)
    return 0 if payload["target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
