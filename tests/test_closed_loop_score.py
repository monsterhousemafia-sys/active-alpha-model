"""Closed-loop (Kreis) score for Superprogramm health."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.closed_loop_score import (
    build_closed_loop_score,
    format_circle_lines_de,
    write_closed_loop_score,
)


def _minimal_snap() -> dict:
    return {
        "broker": {"cash_eur": 100.0},
        "quote_coverage": {"ok": False, "n_ok": 0, "n_total": 12, "quote_coverage_label_de": "0/12"},
        "rebalance_status": {"is_due": True},
        "prediction_gate": {"ok": True},
        "traffic": "GELB",
    }


def _minimal_warnings(*, critical: int = 0) -> dict:
    return {
        "count": critical,
        "critical_count": critical,
        "must_resolve_before_trading": critical > 0,
        "headline_de": "OK" if critical == 0 else f"{critical} kritisch",
    }


def test_build_six_stages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        lambda: {"open": False},
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/public_learning_report_latest.json").write_text(
        json.dumps(
            {
                "capture": {"learning_healthy": True},
                "metrics": {"live": {"n_mature": 0}},
                "quality_score": {"score": 63, "grade": "C"},
                "evolution": {"stage_id": "sportwagen", "next_stage_id": "sport_plus"},
                "message_de": "Lernen läuft",
            }
        ),
        encoding="utf-8",
    )
    doc = build_closed_loop_score(tmp_path, snap=_minimal_snap(), warnings=_minimal_warnings())
    assert doc["total"] == 6
    assert len(doc["stages"]) == 6
    assert doc["headline_de"].startswith("Kreis-Score")
    assert doc["tag"] in ("START", "AUFBAU", "AUFBLUHEN", "SUPERPROGRAMM_GESCHLOSSEN")


def test_format_circle_lines(tmp_path: Path) -> None:
    doc = {
        "headline_de": "Kreis-Score 2/6 grün (33%)",
        "summary_de": "Kern läuft",
        "green": 2,
        "total": 6,
        "bottleneck_de": "Handeln: Live-Fills",
        "stages": [
            {"ok": True, "partial": False, "label_de": "Beobachten", "detail_de": "OK"},
            {"ok": False, "partial": False, "label_de": "Handeln", "detail_de": "0/3"},
        ],
    }
    lines = format_circle_lines_de(doc)
    assert lines[0].startswith("Kreis-Score")
    assert any("Engpass" in ln for ln in lines)


def test_decide_ok_when_weekend_warnings_dampened(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        lambda: {"open": False},
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/public_learning_report_latest.json").write_text(
        json.dumps(
            {
                "capture": {"learning_healthy": True},
                "metrics": {"live": {"n_mature": 0}},
                "quality_score": {"score": 63, "grade": "C"},
                "evolution": {"stage_id": "sportwagen"},
            }
        ),
        encoding="utf-8",
    )
    warnings = {
        "critical_count": 0,
        "critical_count_raw": 3,
        "dampened_off_hours": ["PARTIAL_QUOTE_COVERAGE", "UNDER_INVESTED_CASH"],
        "must_resolve_before_trading": False,
    }
    doc = build_closed_loop_score(tmp_path, snap=_minimal_snap(), warnings=warnings)
    decide = next(s for s in doc["stages"] if s["id"] == "decide")
    assert decide["ok"] is True
    assert "US zu" in decide["detail_de"]


def test_act_partial_when_freigabe_package_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        lambda: {"open": False},
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/public_learning_report_latest.json").write_text(
        json.dumps(
            {
                "capture": {"learning_healthy": True},
                "metrics": {"live": {"n_mature": 0}},
                "quality_score": {"score": 63, "grade": "C"},
                "evolution": {"stage_id": "sportwagen"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_freigabe_latest.json").write_text(
        json.dumps({"freigabe_ready": True, "buy_count": 12}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True, "cycle_pct": 100}),
        encoding="utf-8",
    )
    doc = build_closed_loop_score(tmp_path, snap=_minimal_snap(), warnings=_minimal_warnings())
    act = next(s for s in doc["stages"] if s["id"] == "act")
    assert act["partial"] is True
    assert "Paket bereit" in act["detail_de"]


def test_write_persists_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        lambda: {"open": False},
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/public_learning_report_latest.json").write_text("{}", encoding="utf-8")
    doc = build_closed_loop_score(tmp_path, snap=_minimal_snap(), warnings=_minimal_warnings(critical=1))
    path = write_closed_loop_score(tmp_path, doc)
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["green"] == doc["green"]
    assert loaded["stages"][1]["id"] == "decide"
