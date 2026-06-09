"""Phase S6 — coverage CLI, rollout evidence, extended regression hooks."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aa_sector_reference import (
    audit_sp500_snapshot_sector_columns,
    build_sector_rollout_summary,
    champion_sector_coverage,
    clear_reference_cache,
    load_sector_reference_status,
    update_sector_reference_from_records,
    write_sector_reference_status,
)
from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_champion_coverage_all_mapped_after_reference_seed(tmp_path: Path) -> None:
    records = [
        {"ticker": sym, "sector_coarse": "Technology", "sector_gics": "Information Technology", "source": "test"}
        for sym in CHAMPION_SYMBOLS
    ]
    update_sector_reference_from_records(
        records,
        tmp_path / "sector_reference.csv",
        valid_from="2024-01-01",
        source_detail="s6_test",
        root=tmp_path,
    )
    cov = champion_sector_coverage(tmp_path, CHAMPION_SYMBOLS)
    assert cov["ok"] is True
    assert cov["mapped_count"] == len(CHAMPION_SYMBOLS)
    assert cov["unknown_tickers"] == []


def test_build_rollout_summary_flags_pending_without_snapshot_sectors(tmp_path: Path) -> None:
    cache = tmp_path / "universe_snapshots"
    cache.mkdir(parents=True)
    pd.DataFrame({"ticker": ["AAPL"], "company": ["Apple"], "source": ["t"]}).to_csv(
        cache / "sp500_latest.csv", index=False
    )
    summary = build_sector_rollout_summary(tmp_path)
    assert summary["schema_version"] == 1
    assert summary["acceptance"]["snapshot_has_sector_gics"] is False
    assert summary["rollout_status"] == "PENDING_ROLLOUT"


def test_audit_sp500_snapshot_detects_sector_columns(tmp_path: Path) -> None:
    cache = tmp_path / "universe_snapshots"
    cache.mkdir(parents=True)
    pd.DataFrame(
        {
            "ticker": ["NVDA"],
            "sector_gics": ["Information Technology"],
            "sector_coarse": ["Technology"],
        }
    ).to_csv(cache / "sp500_latest.csv", index=False)
    audit = audit_sp500_snapshot_sector_columns(tmp_path)
    assert audit["has_sector_gics"] is True
    assert audit["has_sector_coarse"] is True


def test_verify_tool_writes_evidence(tmp_path: Path) -> None:
    import sys
    from unittest.mock import patch

    records = [
        {"ticker": sym, "sector_coarse": "Energy", "sector_gics": "Energy", "source": "test"}
        for sym in CHAMPION_SYMBOLS
    ]
    update_sector_reference_from_records(
        records,
        tmp_path / "sector_reference.csv",
        valid_from="2024-01-01",
        source_detail="s6_evidence",
        root=tmp_path,
    )
    from tools.verify_sector_reference_coverage import EVIDENCE_REL, main

    with patch.object(sys, "argv", ["verify", "--root", str(tmp_path), "--write-evidence"]):
        exit_code = main()
    path = tmp_path / EVIDENCE_REL
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["champion_coverage"]["ok"] is True
    assert exit_code == 0


def test_status_roundtrip(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    write_sector_reference_status(tmp_path, {"status": "OK", "source": "pytest"})
    st = load_sector_reference_status(tmp_path)
    assert st.get("status") == "OK"
    assert "updated_at_utc" in st
