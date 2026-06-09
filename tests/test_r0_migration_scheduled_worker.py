"""Scheduled M1 worker (dry-run)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_worker_dry_run():
    from tools.r0_migration_scheduled_worker import run_worker

    result = run_worker(ROOT, dry_run=True)
    assert result.get("action") in (
        "DONE_M1_SEALED",
        "SKIP_MATRIX_ALREADY_RUNNING",
        "FINISH_PUSH",
        "REFRESH_AND_SEAL",
    )
