"""Phase S8 — acceptance runner and review zip."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.run_sector_reference_acceptance_s8 import run_acceptance


def test_acceptance_passes_with_seeded_reference(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    for name, content in {
        "active_alpha_marktanalyse_os.bat": "AA_SECTOR_REFERENCE_MODE=auto\n",
        "active_alpha_settings.bat": "AA_SECTOR_REFERENCE_MODE=auto\n",
        "1_live_daily_sync.bat": "active_alpha_marktanalyse_os.bat\nlive_trading_operations\n",
        "analytics/live_trading_operations.py": "ensure_sector_reference_fresh\nrun_daily_live_cycle\n",
        "ui/live_trading_dashboard/service.py": "Sector reference\n",
        "aa_constants.py": "from aa_sector_reference import lookup_sector\n",
        "build/decision_cockpit/Marktanalyse.spec": "aa_sector_reference\n",
        "AGENTS.md": "sector_reference.csv\nSECTOR_MAP\n",
    }.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
    from aa_sector_reference import update_sector_reference_from_records

    records = [
        {"ticker": sym, "sector_coarse": "Technology", "sector_gics": "IT", "source": "test"}
        for sym in CHAMPION_SYMBOLS
    ]
    update_sector_reference_from_records(
        records,
        tmp_path / "sector_reference.csv",
        valid_from="2024-01-01",
        source_detail="s8",
        root=tmp_path,
    )
    cache = tmp_path / "universe_snapshots"
    cache.mkdir(parents=True)
    import pandas as pd

    pd.DataFrame({"ticker": ["AAPL"], "sector_gics": ["IT"], "sector_coarse": ["Technology"]}).to_csv(
        cache / "sp500_latest.csv", index=False
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    for i in range(6):
        (tests_dir / f"test_sector_reference_s{i}.py").write_text("# stub\n", encoding="utf-8")

    report = run_acceptance(tmp_path, run_pytest=False)
    assert report["status"] == "PASS"
    assert all(c["pass"] for c in report["checks"])


def test_review_zip_lists_core_files() -> None:
    from tools.build_sector_reference_review_zip import INCLUDE

    assert "docs/SECTOR_REFERENCE_AUTOMATION_PLAN.md" in INCLUDE
    assert "tools/run_sector_reference_acceptance_s8.py" in INCLUDE


def test_acceptance_module_importable() -> None:
    from tools import run_sector_reference_acceptance_s8 as mod

    assert hasattr(mod, "main")
