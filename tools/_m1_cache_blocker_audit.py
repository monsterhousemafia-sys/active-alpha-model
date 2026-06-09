"""One-shot audit: prediction cache trust + M1 seal blockers."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RUN_DIR = ROOT / "validation_runs" / "20260605T125544Z_M1_MOM_BLEND_MATCHED_CONTROLS"
META = RUN_DIR / "prediction_cache_meta.json"
PKL = RUN_DIR / "prediction_cache.pkl"


def main() -> int:
    print("=== PREDICTION CACHE (Phase 3) ===")
    if not META.is_file() or not PKL.is_file():
        print("BLOCKER: prediction cache files missing in run dir")
        return 1
    meta = json.loads(META.read_text(encoding="utf-8"))
    ok = (
        meta.get("coverage_status") == "complete"
        and int(meta.get("rebalances", 0)) == int(meta.get("expected_rebalances", 0))
    )
    print(f"  schema_version: {meta.get('schema_version')}")
    print(f"  rebalances: {meta.get('rebalances')} / {meta.get('expected_rebalances')}")
    print(f"  coverage_status: {meta.get('coverage_status')} -> {'TRUST OK' if ok else 'BLOCKER: incomplete'}")
    print(f"  pkl_size_mb: {PKL.stat().st_size / (1024*1024):.1f}")

    log = RUN_DIR / "validation_run.log"
    if log.is_file():
        first = log.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        if "--reuse-prediction-cache" in first:
            print("  launch_cmd: --reuse-prediction-cache YES")
        elif "--force-rebuild-predictions" in first:
            print("  BLOCKER: launch uses --force-rebuild-predictions (cache ignored)")
        if "--no-naive-momentum-baseline" in first:
            print("  fast_flags: VALIDATION_FAST_FLAGS present")

    print("\n=== PATH SIM OUTPUT (Phase 4 -> CSV) ===")
    strat = RUN_DIR / "strategy_daily_returns.csv"
    if strat.is_file():
        n = sum(1 for _ in strat.open(encoding="utf-8")) - 1
        print(f"  strategy_daily_returns.csv: YES rows={n}")
        print(f"  BLOCKER: none (ready for seal if integrity PASS)")
    else:
        print("  strategy_daily_returns.csv: NO")
        print("  BLOCKER: path simulation not finished (no checkpoint/resume in codebase)")

    print("\n=== AUTOSEAL GATE ===")
    from tools._m1_autoseal import complete_dirs, is_sealed, _fast_seal

    for v in ("R0_LEGACY_ENSEMBLE", "R3_w075_q065_noexit", "M1_MOM_BLEND_MATCHED_CONTROLS"):
        cds = complete_dirs(v)
        print(f"  {v}: {'OK ' + str(cds[0][1]) + ' rows' if cds else 'WAIT'}")
    print(f"  fast_seal: {_fast_seal()}")
    print(f"  m1_sealed: {is_sealed()}")

    print("\n=== OFFICIAL M1 SEAL VERIFY ===")
    r = subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "seal_r0_migration_phase.py"),
         "--phase", "M1", "--verify-only", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(r.stdout)
        blockers = data.get("verification", {}).get("blockers") or data.get("blockers") or []
        print(f"  blockers: {blockers if blockers else 'none listed'}")
    except Exception:
        print(f"  output: {(r.stdout or r.stderr)[:400]}")

    print("\n=== SUMMARY ===")
    blockers = []
    if not ok:
        blockers.append("prediction_cache_incomplete")
    if not strat.is_file():
        blockers.append("strategy_daily_returns_missing (path_sim_running)")
    if blockers:
        print("ACTIVE BLOCKERS:", ", ".join(blockers))
    else:
        print("No blockers - ready to seal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
