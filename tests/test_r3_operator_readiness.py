"""R3 Operator-Readiness — Prozent außerhalb /r3."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_operator_readiness import build_r3_operator_readiness, sync_r3_operator_readiness
from analytics.r3_mirror_view import render_results_panel


def _seed_operator_evidence(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/series_readiness_latest.json").write_text(
        json.dumps({"series_ready": True, "readiness_pct": 100}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_operational_checklist_latest.json").write_text(
        json.dumps({"checklist_ok": True, "items_ok": 37, "items_total": 37}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True, "cycle_pct": 100}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_local_growth_latest.json").write_text(
        json.dumps({"growth_pct": 100}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_flow_latest.json").write_text(
        json.dumps(
            {
                "fluidity_pct": 80,
                "channels_ok": 4,
                "channels_total": 5,
                "message_de": "Aufbau · 80% flüssig · 4/5 Kanäle",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_closed_loop_score_latest.json").write_text(
        json.dumps({"pct": 33, "headline_de": "2/6 grün"}),
        encoding="utf-8",
    )


def test_operator_readiness_100_when_critical_gates_ok(tmp_path: Path) -> None:
    _seed_operator_evidence(tmp_path)
    doc = build_r3_operator_readiness(tmp_path, persist=True)
    assert doc.get("operational_pct") == 100
    assert doc.get("operational_ok") is True
    assert (tmp_path / "evidence/r3_operator_readiness_latest.json").is_file()


def test_r3_mirror_html_has_no_percent_operator_chips(tmp_path: Path) -> None:
    from tests.r3_order_fixtures import seed_orders_stack

    seed_orders_stack(tmp_path)
    _seed_operator_evidence(tmp_path)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"bonded": True, "connected": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_freigabe_latest.json").write_text(
        json.dumps({"updated_at_utc": "2026-06-08T00:53:00+00:00", "prep_steps": []}),
        encoding="utf-8",
    )
    html = render_results_panel(tmp_path)
    assert "r3-pipeline-facts" not in html
    assert "r3-system-facts" not in html
    assert "r3-cycle-facts" not in html
    assert "r3-local-banner" not in html
    assert "Kanäle" not in html
    assert "Fluss" not in html
    assert "SR " not in html


def test_sync_persists_without_repair(tmp_path: Path) -> None:
    _seed_operator_evidence(tmp_path)
    doc = sync_r3_operator_readiness(tmp_path, persist=True, repair=False)
    assert doc.get("operational_pct") == 100
