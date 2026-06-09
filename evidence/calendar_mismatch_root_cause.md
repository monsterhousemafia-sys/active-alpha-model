# Calendar mismatch root cause (Phase A3)

Generated: 2026-06-08T13:50:42+00:00

## Summary

- **Locked champion (code):** `R0_LEGACY_ENSEMBLE`
- **Matrix R3 run (`validation_runs/..._R3_w075_q065_noexit`):** 1860 trading days
- **`model_output_sp500_pit_t212` returns:** MISSING trading days
- **`validation_runs/` on disk:** True (gitignored=True)

## Primary finding

Insufficient local return files to compare calendars (see variant_run_inventory.json).

## P11 cost_stress_comparison.csv (label check)

Rows labeled `R3_w075_q065_noexit` in P11 show Sharpe ~0.883 and MaxDD ~−54% — consistent with
**longer/different** return series (same order of magnitude as `model_output` ~2450 days), **not** matrix R3 (~1860 days, MaxDD ~−26%).

| Source | Approx. n_days | Typical MaxDD (from reports) |
|--------|----------------|----------------------------|
| Matrix R3 | 1860 | ~−26% |
| model_output_sp500_pit_t212 | ? | varies |
| P11 row R3 (cost stress) | ~2450 (implicit) | ~−54% |

## Phase B remediation (forward reference)

- Point `latest_validated_run.json` `run_dir` / `run_id` to the matrix PASS R3 folder only.
- Stop writing non-R3 variant full backtests into `model_output_sp500_pit_t212/`.
- Rebuild `challenger_report` from `validation_runs/` only for champion metrics.
