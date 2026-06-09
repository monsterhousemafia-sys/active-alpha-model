"""In sich geschlossener Trading-Kreislauf."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_desktop_view import load_desktop_status, run_r3_background_refresh
from analytics.r3_trading_cycle import evaluate_trading_cycle, run_trading_cycle


def _seed_cycle_evidence(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control").mkdir(exist_ok=True)
    files = {
        "r3_internet_latest.json": {"internet_ok": True, "confirmation_de": "OK"},
        "r3_t212_api_bond_latest.json": {"connected": True, "cash_eur": 500.0, "bonded": True},
        "r3_browser_ingest_latest.json": {"internet_ok": True, "ok": True, "price_latest": "2026-06-05"},
        "alpha_model_background_engine_latest.json": {
            "ok": True,
            "predict": {"signal_date": "2026-06-05"},
            "r3_display": {"ok": True},
        },
        "pilot_investment_plan_latest.json": {
            "investable_eur": 450,
            "plan_capital_eur": 450,
            "t212_live": {"positions_count": 0, "last_sync_utc": "2026-06-08T12:00:00+00:00"},
            "allocations": [{"symbol": "STX", "target_eur": 100.0}],
            "updated_at_utc": "2026-06-08T12:00:00+00:00",
        },
        "r3_t212_prognosis_latest.json": {"ok": True, "positions": 5, "signal_date": "2026-06-05"},
    }
    for name, body in files.items():
        (tmp_path / "evidence" / name).write_text(json.dumps(body), encoding="utf-8")
    (tmp_path / "control/r3_order_execution_policy.json").write_text(
        json.dumps({"status": "AUTHORITATIVE"}),
        encoding="utf-8",
    )


def test_evaluate_closed_cycle(tmp_path: Path) -> None:
    _seed_cycle_evidence(tmp_path)
    ev = evaluate_trading_cycle(tmp_path)
    assert ev.get("closed") is True
    assert ev.get("stages_ok") == 7


def test_run_cycle_persists(tmp_path: Path) -> None:
    _seed_cycle_evidence(tmp_path)
    with patch("analytics.r3_trading_cycle._run_cycle_steps") as mock_run:
        mock_run.return_value = {"ok": True, "steps": [{"id": "internet", "ok": True}]}
        doc = run_trading_cycle(tmp_path)
    assert (tmp_path / "evidence/r3_trading_cycle_latest.json").is_file()
    assert doc.get("closed") is True


def test_background_refresh_delegates_to_cycle(tmp_path: Path) -> None:
    with patch(
        "analytics.r3_trading_cycle.run_trading_cycle",
        return_value={
            "run_ok": True,
            "closed": True,
            "steps": [],
            "confirmation_de": "✓ Trading-Kreislauf geschlossen",
        },
    ):
        out = run_r3_background_refresh(tmp_path)
    assert out.get("closed") is True


def test_prognosis_failure_marks_run_not_ok(tmp_path: Path) -> None:
    _seed_cycle_evidence(tmp_path)
    with patch("analytics.r3_internet_requirement.probe_and_record_internet") as net, patch(
        "analytics.r3_quote_keepalive.tick_quote_keepalive",
        return_value={"ok": True, "skipped": True, "price_latest": "2026-06-09"},
    ), patch(
        "analytics.r3_t212_api_bond.sync_r3_t212_api_bond",
        return_value={"connected": True, "bonded": True, "confirmation_de": "OK"},
    ), patch(
        "integrations.trading212.t212_trust_gate.assess_t212_trust_from_root",
        return_value={"trusted": True},
    ), patch(
        "analytics.r3_prognosis_pipeline.ensure_r3_prognosis_fresh",
        return_value={"ok": False, "skipped": False},
    ), patch(
        "analytics.r3_trading_functions.build_r3_trading_functions",
        return_value={"functions": [], "functions_active": 0},
    ), patch(
        "analytics.r3_daily_postmortem.run_daily_postmortem",
        return_value={"ok": True, "bad_day": False},
    ), patch(
        "analytics.alpha_model_background_engine.tick_alpha_model_background",
        return_value={"ok": True, "steps_ok": 6, "predict": {"signal_date": "2026-06-05"}},
    ):
        net.return_value = {"internet_ok": True}
        from analytics.r3_trading_cycle import _run_cycle_steps

        out = _run_cycle_steps(tmp_path)
    assert out.get("ok") is False
    prog = next(s for s in out["steps"] if s["id"] == "prognosis")
    assert prog.get("ok") is False


def test_ingest_failure_marks_run_not_ok(tmp_path: Path) -> None:
    """Legacy name — cycle no longer runs ingest; prognosis failure covers this."""
    test_prognosis_failure_marks_run_not_ok(tmp_path)


def test_desktop_cycle_chip(tmp_path: Path) -> None:
    _seed_cycle_evidence(tmp_path)
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True, "runtime_closed": True, "confirmation_de": "✓ geschlossen"}),
        encoding="utf-8",
    )
    status = load_desktop_status(tmp_path)
    assert any(c.get("label_de") == "Kreislauf" for c in status.get("chips") or [])
