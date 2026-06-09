"""Phase S4 — Dashboard, live-ops, EXE wiring for sector reference."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aa_sector_reference import clear_reference_cache, format_sector_dashboard_status
from ui.live_trading_dashboard import service as dash


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_format_sector_dashboard_status_missing_is_gelb(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    st = format_sector_dashboard_status(tmp_path)
    assert st["traffic"] == "GELB"
    assert "Sektoren" in st["summary_de"]


def test_write_dashboard_txt_includes_sector_block(tmp_path: Path) -> None:
    snap = {
        "traffic": "GRUEN",
        "sector_status": {"summary_de": "Sektoren: Stand 2026-06-03 · Champion 14/14", "traffic": "GRUEN"},
        "today_action_de": "NUR MARK",
        "rebalance_status": {"summary_de": "ok"},
        "broker": {},
        "guard": {},
        "plan": {"allocations": []},
        "reevaluation": {},
        "deferred": {},
        "n_positions": 0,
    }
    text = dash.write_dashboard_txt(tmp_path, snap).read_text(encoding="utf-8")
    assert "Sector reference" in text
    assert "Champion 14/14" in text


def test_run_daily_live_cycle_calls_sector_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def _fake_ensure(root: Path, env: dict) -> dict:
        called.append("yes")
        return {"refreshed": False, "message_de": "Sektoren: Test"}

    monkeypatch.setattr(
        "aa_sector_reference.ensure_sector_reference_fresh",
        _fake_ensure,
    )
    monkeypatch.setattr(
        "analytics.live_trading_operations.sync_broker_and_quotes",
        lambda *a, **k: {"broker": {"credentials_configured": True, "cash_eur": 0}},
    )
    monkeypatch.setattr(
        "analytics.live_trading_operations.record_daily_mark",
        lambda *a, **k: {"recorded": False, "reason": "ALREADY_MARKED_TODAY"},
    )
    monkeypatch.setattr(
        "analytics.live_trading_operations.load_policy",
        lambda *a, **k: {
            "auto_enable_on_startup": False,
            "rebalance_every_trading_days": 5,
            "auto_enqueue_on_rebalance_due": False,
        },
    )
    monkeypatch.setattr(
        "analytics.live_trading_operations.rebalance_status",
        lambda *a, **k: {
            "is_due": False,
            "recorded_trading_days_since_rebalance": 1,
            "rebalance_every_trading_days": 5,
            "summary_de": "Mark OK",
        },
    )
    monkeypatch.setattr(
        "execution.confirmed_live.live_trading_enablement.ensure_live_trading_enabled",
        lambda *a, **k: None,
    )
    monkeypatch.setattr("analytics.live_trading_operations.atomic_write_json", lambda *a, **k: None)

    from analytics.live_trading_operations import run_daily_live_cycle

    out = run_daily_live_cycle(tmp_path)
    assert called == ["yes"]
    assert out["sector_refresh"]["message_de"] == "Sektoren: Test"
    assert "Sektoren: Test" in out["summary_de"]


def test_run_ops_refresh_records_sector_meta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "model_out"
    out.mkdir()
    env = {
        "AA_BACKTEST_OUT_DIR": str(out),
        "AA_AUTO_OPS_REFRESH": "1",
        "AA_SKIP_DOWNLOAD_IF_CACHED": "0",
    }
    monkeypatch.setattr("aa_ops_refresh.refresh_price_panel_with_retry", lambda *a, **k: True)
    monkeypatch.setattr("aa_ops_refresh.refresh_universe_if_needed", lambda *a, **k: False)
    monkeypatch.setattr(
        "aa_sector_reference.ensure_sector_reference_fresh",
        lambda *a, **k: {"refreshed": True, "message_de": "Sektoren OK"},
    )
    from aa_data_freshness import DailyDataReport, last_expected_market_date

    ref = last_expected_market_date()
    monkeypatch.setattr(
        "aa_ops_refresh.assess_daily_data",
        lambda *a, **k: DailyDataReport(
            reference_date=ref,
            price_current=True,
            signal_current=True,
            ok=True,
        ),
    )
    from aa_ops_refresh import read_ops_meta, run_ops_refresh

    run_ops_refresh(tmp_path, env, log=lambda _: None, force=True, include_signal=False)
    meta = read_ops_meta(out)
    assert meta.get("sector_reference_refreshed") is True


def test_marktanalyse_spec_lists_sector_hiddenimport() -> None:
    spec = Path(__file__).resolve().parents[1] / "build" / "decision_cockpit" / "Marktanalyse.spec"
    text = spec.read_text(encoding="utf-8")
    assert "aa_sector_reference" in text
