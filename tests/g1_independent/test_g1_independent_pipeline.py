"""G1 independent research tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_authority_files_exist_after_run():
    auth = ROOT / "incoming_user_directives/g1_independent"
    assert (auth / "USER_DIRECTIVE_INDEPENDENT_CURSOR_G1_DEVELOPMENT.md").is_file()
    assert (auth / "G1_INDEPENDENT_CURSOR_INPUT_MANIFEST.json").is_file()


def test_data_contract_schema():
    path = ROOT / "docs/development/G1_INDEPENDENT_NEXT_LEVEL/G1_DATA_CONTRACT.json"
    if not path.is_file():
        pytest.skip("Run tools/run_g1_independent_evidence.py first")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("champion_id", "challenger_id", "control_id", "input_dataset_hashes"):
        assert key in data


def test_challenger_turnover_evidence():
    turnover = ROOT / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/turnover/rebalance_turnover.csv"
    if not turnover.is_file():
        pytest.skip("Challenger evidence not generated yet")
    text = turnover.read_text(encoding="utf-8")
    assert "rebalance_date" in text.splitlines()[0]
    assert "turnover" in text.splitlines()[0]


def test_observation_package():
    obs = ROOT / "outgoing_cursor_observation/g1_independent_next_level"
    required = [
        "cursor_g1_independent_next_level_development_package.zip",
        "CURSOR_G1_NEXT_LEVEL_EXECUTION_REPORT.md",
    ]
    if not all((obs / n).is_file() for n in required):
        pytest.skip("Observation package not built yet")
    assert (obs / "cursor_g1_independent_next_level_development_package.zip.sha256").is_file()


def test_safety_no_operational_flags():
    snap_path = ROOT / "control/review_snapshot/g1_independent_research_snapshot.json"
    if not snap_path.is_file():
        pytest.skip("G1 snapshot not written yet")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    track = snap.get("g1_independent_track") or {}
    assert track.get("operational_status") == "NOT_AUTHORIZED"
    assert track.get("live_trading") == "NOT_AUTHORIZED"
    assert track.get("external_sealed") is False
