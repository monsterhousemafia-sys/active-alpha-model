#!/usr/bin/env python3
"""Post-build smoke checks for canonical Marktanalyse.exe (onefile at repo root)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fail(msg: str) -> int:
    print(f"[SMOKE FAIL] {msg}", file=sys.stderr)
    return 1


def main() -> int:
    from aa_paths import canonical_marktanalyse_exe

    exe = canonical_marktanalyse_exe(ROOT)
    if not exe.is_file():
        return _fail(f"Marktanalyse.exe fehlt: {exe}")

    exe_mb = exe.stat().st_size // 1_000_000
    if exe_mb < 80:
        return _fail(f"EXE zu klein ({exe_mb} MB): {exe}")

    print(f"[SMOKE OK] Canonical Marktanalyse.exe ({exe_mb} MB) @ {exe}")

    from aa_version import APP_TITLE, APP_VERSION, MODEL_PROFILE

    print(f"[SMOKE OK] {APP_TITLE} ({APP_VERSION}, {MODEL_PROFILE})")

    from aa_eta_calibration import build_backtest_budgets, estimate_backtest_remaining

    budgets = build_backtest_budgets()
    eta = estimate_backtest_remaining(budgets)
    print(f"[SMOKE OK] ETA calibration keys={len(eta)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
