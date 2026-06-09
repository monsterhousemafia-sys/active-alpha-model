#!/usr/bin/env python3
"""CLI entry for Phase C background jobs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_background_jobs import JOB_NAMES, run_job  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Run one Active Alpha background job")
    p.add_argument("job", choices=JOB_NAMES, help="Job name")
    p.add_argument("--root", type=Path, default=ROOT, help="Project root")
    args = p.parse_args()
    result = run_job(args.job, args.root)
    print(f"[{result.finished_at_utc}] {result.job}: {result.status} — {result.message}")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
