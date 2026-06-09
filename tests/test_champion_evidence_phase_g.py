"""Phase G live-operations evidence checks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_champion_evidence_phase_g import (
    audit_g1_symbol_mapping,
    audit_g2_planning_cash,
    audit_g3_quote_coverage,
    audit_g4_execution_report,
    run_phase_g,
)


def test_g1_stx_maps_to_provider_id_not_champion_key():
    out = audit_g1_symbol_mapping(Path("."))
    assert out["status"] == "PASS"
    assert out["stx_maps_to_stx_us_eq"] is True
    rows = {r["champion_symbol"]: r["t212_ticker"] for r in out["mapping_rows"]}
    assert rows.get("STX") == "STX_US_EQ"
    assert rows.get("SNDK") == "SNDK_US_EQ"


def test_g2_wave_caps_to_planning_cash(tmp_path: Path):
    out = audit_g2_planning_cash(tmp_path)
    assert out["status"] == "PASS"
    assert out["cash_cap_ok"] is True
    assert (tmp_path / "evidence" / "phase_g_planning_cash_audit.json").is_file()


def test_g3_full_champion_quote_coverage(tmp_path: Path):
    out = audit_g3_quote_coverage(tmp_path)
    assert out["status"] == "PASS"
    assert out["sndk_in_champion_symbols"] is True
    assert out["coverage_ok"] is True
    assert "14" in str(out.get("quote_coverage_label_de", "")) or out["required_count"] == 14


def test_g4_execution_report_breakdown():
    out = audit_g4_execution_report()
    assert out["status"] == "PASS"
    assert "1/2" in out["summary_de"] and "MU" in out["summary_de"]


def test_run_phase_g_skip_pytest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fake_g6(root: Path, **kwargs):
        return {
            "status": "PASS",
            "overall_pass": True,
            "dry_run": {"ok": True, "quote_coverage_label_de": "14/14"},
            "live_trading_operations": {"ok": True},
        }

    monkeypatch.setattr(
        "aa_champion_evidence_phase_g.audit_g6_phase5_validation",
        fake_g6,
    )

    def fake_g5(root: Path, *, build: bool = False):
        return {"status": "PASS", "exe_sha256": "abc", "os_bat_present": True}

    monkeypatch.setattr("aa_champion_evidence_phase_g.audit_g5_exe", fake_g5)

    summary = run_phase_g(tmp_path, skip_pytest=True)
    assert summary["overall_pass"] is True
    assert (tmp_path / "evidence" / "phase_g_live_operations_summary.json").is_file()
    doc = json.loads((tmp_path / "evidence" / "phase_g_live_operations_summary.json").read_text(encoding="utf-8"))
    assert doc["phase"] == "G"
