"""Phase S7 — rollout orchestration and matrix smoke (read-only)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aa_sector_reference import clear_reference_cache, lookup_sector, update_sector_reference_from_records
from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
from tools.check_sector_matrix_smoke import check_matrix_smoke


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_matrix_smoke_passes_with_mapped_champion_weights(tmp_path: Path) -> None:
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    rows = [{"ticker": sym, "target_weight": 1.0 / len(CHAMPION_SYMBOLS)} for sym in CHAMPION_SYMBOLS]
    pd.DataFrame(rows).to_csv(out / "latest_target_portfolio.csv", index=False)
    records = [
        {"ticker": sym, "sector_coarse": "Technology", "sector_gics": "IT", "source": "test"}
        for sym in CHAMPION_SYMBOLS
    ]
    update_sector_reference_from_records(
        records,
        tmp_path / "sector_reference.csv",
        valid_from="2024-01-01",
        source_detail="s7",
        root=tmp_path,
    )
    report = check_matrix_smoke(tmp_path, max_sector=0.55)
    assert report["pass"] is True
    assert report["max_unknown_sector_weight"] == 0.0


def test_matrix_smoke_fails_when_champion_unknown_in_portfolio(tmp_path: Path) -> None:
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    pd.DataFrame([{"ticker": "CIEN", "target_weight": 0.6}]).to_csv(out / "latest_target_portfolio.csv", index=False)
    report = check_matrix_smoke(tmp_path, max_sector=0.55)
    assert report["pass"] is False
    assert float(report["max_unknown_sector_weight"]) > 0.55


def test_lookup_cien_after_yfinance_style_record(tmp_path: Path) -> None:
    update_sector_reference_from_records(
        [{"ticker": "CIEN", "sector_coarse": "Communication", "sector_gics": "Communication Services", "source": "yfinance_fallback"}],
        tmp_path / "sector_reference.csv",
        valid_from="2026-06-04",
        source_detail="test",
        root=tmp_path,
    )
    assert lookup_sector("CIEN", root=tmp_path) == "Communication"
