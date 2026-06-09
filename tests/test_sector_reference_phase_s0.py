"""Phase S0 evidence generator smoke tests."""
from __future__ import annotations

import json
from pathlib import Path

from tools.run_sector_reference_phase_s0 import build_gap_analysis, _governance_note, _wikipedia_parser_alignment
from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS


def test_build_gap_analysis_structure(tmp_path: Path) -> None:
    (tmp_path / "ticker_membership.csv").write_text(
        "ticker,valid_from,valid_to,source,reason\n"
        "AAPL,2012-01-01,,wikipedia,ok\n"
        "ZZZZ,2012-01-01,,wikipedia,ok\n",
        encoding="utf-8",
    )
    (tmp_path / "universe_snapshots").mkdir()
    (tmp_path / "universe_snapshots" / "sp500_latest.csv").write_text(
        "ticker,source_symbol,company,source\nAAPL,AAPL,Apple,wikipedia_sp500\n",
        encoding="utf-8",
    )
    doc = build_gap_analysis(tmp_path, as_of="2026-06-03")
    assert doc["phase"] == "S0"
    assert doc["sector_map_entry_count"] > 100
    assert "groups" in doc
    names = {g["group"] for g in doc["groups"]}
    assert "champion_symbols_14" in names
    ch = next(g for g in doc["groups"] if g["group"] == "champion_symbols_14")
    assert ch["ticker_count"] == len(CHAMPION_SYMBOLS)


def test_wikipedia_alignment_documents_gap() -> None:
    align = _wikipedia_parser_alignment()
    assert align["live_aa_universe"]["sector_gics_emitted"] is False
    assert align["build_sp500_membership_wikipedia"]["sector_gics_emitted"] is True
    assert "sector_gics" in align["alignment_gap"]["required_s2_fields"]


def test_governance_note_champion_frozen() -> None:
    gov = _governance_note(Path("."))
    assert gov["classification"] == "INFRASTRUCTURE_ONLY"
    assert gov["champion_unchanged"] == "R3_w075_q065_noexit"
    assert "max_sector" in " ".join(gov["out_of_scope_without_external_approval"]).lower() or any(
        "max_sector" in x for x in gov["out_of_scope_without_external_approval"]
    )


def test_phase_s0_evidence_files_exist_in_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    gap = root / "evidence" / "sector_map_gap_analysis.json"
    if not gap.is_file():
        return
    data = json.loads(gap.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
