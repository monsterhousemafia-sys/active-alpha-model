"""Strategic M1 bootstrap dry-run."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_strategic_bootstrap_dry_run():
    from tools.run_r0_migration_strategic_bootstrap import run_bootstrap

    r = run_bootstrap(ROOT, dry_run=True)
    assert r.get("action") in ("DRY_RUN", "M1_ALREADY_SEALED")
