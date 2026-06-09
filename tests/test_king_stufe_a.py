"""Stufe A — KPIs, Evidence-RAG, Orchestrator."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.king_evidence_rag import build_evidence_rag
from analytics.king_stufe_a import evaluate_stufe_a_kpis, resolve_growth_phase_from_kpis


def test_build_evidence_rag_from_fixtures(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/king_stufe_a_policy.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "evidence_rag_paths": ["evidence/king_network_pulse_latest.json"],
                "evidence_rag_max_chars": 2000,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text(
        json.dumps({"phase": "ready", "beat": 8, "headline_de": "OK"}),
        encoding="utf-8",
    )
    doc = build_evidence_rag(tmp_path, persist=False)
    assert doc.get("chunk_count") == 1
    assert "ready" in str(doc.get("rag_text"))


def test_kpis_wachstum_with_h1_and_prediction(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/king_stufe_a_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "h1_backtest_status": "COMPLETE"}),
        encoding="utf-8",
    )
    (tmp_path / "control/h1_governance_status.json").write_text(
        json.dumps({"status": "COMPLETE", "metrics_strategy": {"sharpe_0rf": 0.78}}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_prognosis_latest.json").write_text(
        json.dumps({"updated_at_utc": "2099-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/public_learning_report_latest.json").write_text(
        json.dumps({"quality_score": {"total": 55}}),
        encoding="utf-8",
    )
    kpis = evaluate_stufe_a_kpis(tmp_path)
    assert kpis.get("wachstum_ok") is True
    assert resolve_growth_phase_from_kpis(kpis, ollama_ok=True) in ("wachstum", "forschung_reif")


def test_resolve_growth_phase_keim_without_ollama(tmp_path: Path) -> None:
    kpis = {"wachstum_ok": False, "forschung_reif_ok": False}
    assert resolve_growth_phase_from_kpis(kpis, ollama_ok=False) == "keim"


def test_forschung_prefers_stufe_a_phase(tmp_path: Path) -> None:
    from analytics.king_32b_forschung import resolve_growth_phase

    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/king_stufe_a_latest.json").write_text(
        json.dumps({"growth_phase": "wachstum"}),
        encoding="utf-8",
    )
    growth = resolve_growth_phase(tmp_path)
    assert growth.get("phase") == "wachstum"
