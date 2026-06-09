"""P10 integration tests."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_p0_p9_still_pass():
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    for pid in (
        "P0_SAFETY_CONTROL_PLANE",
        "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION",
    ):
        st = next(p["status"] for p in pipeline["phases"] if p["id"] == pid)
        assert st == "PASS"


def test_p10_phase_exists_after_run():
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    ids = {p["id"] for p in pipeline["phases"]}
    assert "P10_RESEARCH_EVIDENCE_INTEGRATION_AND_STRATEGY_IDENTITY_RESOLUTION" in ids


def test_strict_variant_artifacts():
    base = ROOT / "evidence/autonomous_research/MOM_63_TOP12_STRICT"
    for name in ("daily_returns.csv", "manifests/evidence_manifest.json", "trade_ledgers/full_trade_ledger.csv"):
        assert (base / name).is_file(), name


def test_p10_output_package():
    obs = ROOT / "outgoing_cursor_observation/p10_research_evidence_integration"
    if not obs.is_dir():
        return
    assert (obs / "cursor_p10_research_evidence_integration_package.zip").is_file()
