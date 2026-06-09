"""Phase S1 — sector reference module."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aa_constants import SECTOR_MAP, ticker_to_sector
from aa_sector_reference import (
    clear_reference_cache,
    gics_to_coarse,
    lookup_sector,
    parse_sector_gics_from_row,
    update_sector_reference_from_records,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_gics_parse_from_row_columns() -> None:
    row = {"Symbol": "NVDA", "GICS Sector": "Information Technology", "Security": "NVIDIA"}
    assert parse_sector_gics_from_row(row, columns=row.keys()) == "Information Technology"


def test_coarse_mapping() -> None:
    assert gics_to_coarse("Information Technology") == "Technology"
    assert gics_to_coarse("Health Care") == "Healthcare"
    assert gics_to_coarse("") == "Unknown"
    assert gics_to_coarse("Not A Real GICS Sector Name XYZ") == "Unknown"


def test_update_appends_valid_from(tmp_path: Path) -> None:
    path = tmp_path / "sector_reference.csv"
    records = [{"ticker": "AAPL", "sector_gics": "Information Technology", "source": "test"}]
    r1 = update_sector_reference_from_records(
        records, path, valid_from="2020-01-01", source_detail="test_wikipedia"
    )
    assert r1["added"] == 1
    df = pd.read_csv(path)
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "AAPL"
    assert df.iloc[0]["sector_coarse"] == "Technology"
    assert str(df.iloc[0]["valid_from"]) == "2020-01-01"


def test_pit_closes_old_row_on_sector_change(tmp_path: Path) -> None:
    path = tmp_path / "sector_reference.csv"
    update_sector_reference_from_records(
        [{"ticker": "XYZ", "sector_gics": "Energy", "source": "t"}],
        path,
        valid_from="2020-01-01",
        source_detail="t",
    )
    update_sector_reference_from_records(
        [{"ticker": "XYZ", "sector_gics": "Utilities", "source": "t"}],
        path,
        valid_from="2021-06-01",
        source_detail="t",
    )
    df = pd.read_csv(path)
    assert len(df) == 2
    old = df[df["valid_to"].astype(str).str.len() > 0].iloc[0]
    new = df[df["valid_to"].fillna("").astype(str).str.len() == 0].iloc[0]
    assert old["sector_coarse"] == "Energy"
    assert str(old["valid_to"]) == "2021-05-31"
    assert new["sector_coarse"] == "Utilities"
    assert lookup_sector("XYZ", as_of="2020-12-31", root=tmp_path) == "Energy"
    assert lookup_sector("XYZ", as_of="2021-06-01", root=tmp_path) == "Utilities"


def test_lookup_falls_back_to_sector_map(tmp_path: Path) -> None:
    assert lookup_sector("NVDA", root=tmp_path) == SECTOR_MAP["NVDA"]


def test_lookup_unknown_when_unmapped(tmp_path: Path) -> None:
    assert lookup_sector("ZZNOTICKER999", root=tmp_path) == "Unknown"


def test_load_sector_reference_status_missing(tmp_path: Path) -> None:
    from aa_sector_reference import load_sector_reference_status

    st = load_sector_reference_status(tmp_path)
    assert st.get("status") == "MISSING"


def test_ticker_to_sector_delegates_to_reference(tmp_path: Path) -> None:
    path = tmp_path / "sector_reference.csv"
    update_sector_reference_from_records(
        [{"ticker": "ZZTEST", "sector_coarse": "Software", "sector_gics": "Software", "source": "t"}],
        path,
        valid_from="2024-01-01",
        source_detail="t",
        root=tmp_path,
    )
    import os

    old = os.environ.get("AA_SECTOR_REFERENCE_FILE")
    os.environ["AA_PROJECT_ROOT"] = str(tmp_path)
    os.environ["AA_SECTOR_REFERENCE_FILE"] = "sector_reference.csv"
    try:
        clear_reference_cache()
        assert ticker_to_sector("ZZTEST") == "Software"
        assert ticker_to_sector("NVDA") == "Semiconductors"
    finally:
        clear_reference_cache()
        if old is None:
            os.environ.pop("AA_SECTOR_REFERENCE_FILE", None)
        else:
            os.environ["AA_SECTOR_REFERENCE_FILE"] = old
        os.environ.pop("AA_PROJECT_ROOT", None)


def test_seed_tool_writes_map(tmp_path: Path) -> None:
    from aa_constants import SECTOR_MAP as _map
    from aa_sector_reference import resolve_reference_path, update_sector_reference_from_records

    path = resolve_reference_path(tmp_path)
    records = [
        {"ticker": tk, "sector_coarse": sec, "sector_gics": sec, "source": "legacy_map_seed"}
        for tk, sec in sorted(_map.items())
    ]
    update_sector_reference_from_records(
        records, path, valid_from="2012-01-01", source_detail="legacy_map_seed", root=tmp_path
    )
    assert path.is_file()
    df = pd.read_csv(path)
    assert len(df) >= len(SECTOR_MAP)
    assert lookup_sector("AAPL", root=tmp_path) == "Technology"
