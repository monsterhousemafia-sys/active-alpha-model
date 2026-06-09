"""GUI preview harness — backend + offscreen dashboard smoke."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _offscreen_qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("AA_GUI_PREVIEW", "1")
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "1")


def _seed_evidence(root: Path) -> None:
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence/public_learning_report_latest.json").write_text(
        json.dumps(
            {
                "quality_score": {"score": 63, "grade": "C"},
                "evolution": {"stage_id": "sportwagen", "next_stage_id": "sport_plus"},
                "message_de": "Test",
                "capture": {"learning_healthy": True},
                "metrics": {"live": {"n_mature": 0}},
            }
        ),
        encoding="utf-8",
    )
    (root / "evidence/trading_day_latest.json").write_text(
        json.dumps(
            {
                "next_step_de": "② Test",
                "cockpit_lines_de": ["Kreis-Score 1/6", "Phase: TEST"],
                "circle_score": {"headline_de": "Kreis-Score 1/6 grün (17%)"},
                "h1": {"banner_de": "H1: TEST"},
            }
        ),
        encoding="utf-8",
    )
    (root / "control").mkdir(exist_ok=True)
    (root / "control/linux_operator_timers.json").write_text(
        json.dumps({"timers": [{"id": "t", "label_de": "Test", "schedule_de": "—", "command": "x"}]}),
        encoding="utf-8",
    )
    (root / "control/active_alpha_public_capabilities.json").write_text(
        json.dumps({"can_do_de": ["learn"], "cannot_do_de": ["autotrade"], "how_to_see_de": ["terminal"]}),
        encoding="utf-8",
    )
    (root / "control/linux_operator_scope.json").write_text(
        json.dumps({"approved_levels": ["A"], "max_level": "A", "levels": {}}),
        encoding="utf-8",
    )


def _fake_snap() -> dict:
    return {
        "traffic": "GELB",
        "broker": {"cash_eur": 500.0},
        "plan": {"allocations": [{"symbol": "AAPL", "weight": 0.1}], "signal_date": "2026-06-05"},
        "portfolio_orders": {
            "has_orders": True,
            "n_buys": 1,
            "quote_coverage_ok": True,
            "quote_coverage_label_de": "1/1",
            "lines_de": ["Test"],
        },
        "quote_coverage": {"ok": True, "quote_coverage_label_de": "1/1"},
        "rebalance_status": {"summary_de": "Rebalance Test", "is_due": True, "recorded_trading_days_since_rebalance": 5},
        "trading_readiness": {"ready": True, "orders_allowed": False, "checks": [{"label": "API", "ok": True}]},
        "public_learning": {"score": 63, "grade": "C", "stage_de": "Sportwagen", "next_stage_id": "sport_plus"},
        "today_action_de": "Test-Aktion",
        "n_positions": 2,
        "live_enabled": True,
        "venv_ok": True,
        "model_script_ok": True,
        "prediction_gate": {"ok": True},
        "sector_status": {"summary_de": "Sektoren OK", "traffic": "GRUEN"},
        "policy": {"order_execution_type": "limit"},
        "deferred": {"status_de": "—", "policy": {"user_armed": False}},
        "guard": {"signals_ok": True},
    }


def test_backend_preview_steps(tmp_path: Path, monkeypatch) -> None:
    _seed_evidence(tmp_path)
    monkeypatch.setattr(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        lambda: {"open": False},
    )
    from ui.live_trading_dashboard.gui_preview_harness import run_backend_preview

    steps = run_backend_preview(tmp_path, snap=_fake_snap())
    assert len(steps) >= 7
    assert all(s.get("id") for s in steps)
    assert sum(1 for s in steps if s.get("pass")) >= 6


def test_gui_preview_offscreen(tmp_path: Path, monkeypatch) -> None:
    _seed_evidence(tmp_path)
    monkeypatch.setattr(
        "execution.confirmed_live.trading_mode_policy.get_trading_mode",
        lambda r: "ai_assisted",
    )
    monkeypatch.setattr(
        "execution.confirmed_live.trading_mode_policy.trading_readiness",
        lambda r: {"ready": True, "orders_allowed": False, "checks": []},
    )
    try:
        from PySide6 import QtCore  # noqa: F401
    except ImportError:
        pytest.skip("PySide6 not installed")

    from ui.live_trading_dashboard.gui_preview_harness import run_gui_preview

    steps, probes, _ = run_gui_preview(tmp_path, _fake_snap())
    assert any(s["id"] == "gui_window" and s["pass"] for s in steps)
    assert any(s["id"] == "gui_apply_snapshot" and s["pass"] for s in steps)
    assert probes.get("status_banner")


def test_full_preview_writes_evidence(tmp_path: Path, monkeypatch) -> None:
    _seed_evidence(tmp_path)
    monkeypatch.setattr(
        "ui.live_trading_dashboard.gui_preview_harness._load_snap_for_gui",
        lambda root, snap, allow_refresh=True: snap or _fake_snap(),
    )
    monkeypatch.setattr(
        "ui.live_trading_dashboard.gui_preview_harness.run_backend_preview",
        lambda root, snap=None, allow_snapshot_refresh=True: [_step_ok()],
    )
    monkeypatch.setattr(
        "ui.live_trading_dashboard.gui_preview_harness.run_gui_preview",
        lambda root, snap, screenshot=False: ([_step_ok("gui")], {"x": 1}, None),
    )
    monkeypatch.setattr(
        "ui.live_trading_dashboard.gui_preview_harness.run_chat_preview_steps",
        lambda root, skip_chat=False: ([_step_ok("chat")], {"ok": True, "next_step_de": "test"}),
    )
    from ui.live_trading_dashboard.gui_preview_harness import run_full_gui_preview

    report = run_full_gui_preview(tmp_path, refresh_snap=False)
    assert (tmp_path / "evidence/gui_preview_latest.json").is_file()
    assert report.get("overall_pass")


def _step_ok(sid: str = "b") -> dict:
    return {"id": sid, "label_de": "T", "pass": True, "detail_de": "OK"}
