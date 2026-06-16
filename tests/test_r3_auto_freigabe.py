"""R3 technische Vorbereitung — /desktop und Submit."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.desktop_shell_cache import get_desktop_html_for_hub
from analytics.r3_freigabe import (
    FREIGABE_GOVERNANCE_NOTE_DE,
    auto_prepare_freigabe_for_desktop,
    freigabe_governance_note_de,
    package_ready,
)
from tests.r3_order_fixtures import seed_orders_stack


@patch("analytics.r3_t212_account_identity.assess_account_confirmation")
@patch("analytics.r3_freigabe.refresh_order_surface")
@patch("analytics.live_trading_operations.sync_broker_and_quotes")
@patch("analytics.r3_t212_api_bond.sync_r3_t212_api_bond")
def test_auto_prepare_runs_t212_quotes_orders(
    mock_bond, mock_sync, mock_surface, mock_acct, tmp_path: Path
) -> None:
    seed_orders_stack(tmp_path)
    mock_acct.return_value = {"needs_confirmation": False, "message_de": "Konto OK"}
    mock_bond.return_value = {"bonded": True, "connected": True, "confirmation_de": "T212 ok"}
    mock_sync.return_value = {
        "quote_snapshot": {
            "executable_prices_eur": {"STX": 85.0},
            "_quote_gate_ok": True,
            "_us_session_open": True,
        }
    }
    mock_surface.return_value = {"buy_count": 2, "initial_package": {"active": True, "notional_eur": 640.93}}

    doc = auto_prepare_freigabe_for_desktop(tmp_path)

    mock_bond.assert_called_once()
    mock_sync.assert_called_once()
    mock_surface.assert_called_once()
    assert doc.get("auto_prepared") is True
    assert doc.get("package_ready") is True
    assert len(doc.get("auto_bootstrap") or []) == 4
    assert (tmp_path / "evidence/r3_freigabe_latest.json").is_file()
    assert doc.get("governance_note_de") == FREIGABE_GOVERNANCE_NOTE_DE
    saved = json.loads((tmp_path / "evidence/r3_freigabe_latest.json").read_text(encoding="utf-8"))
    assert saved.get("governance_note_de") == FREIGABE_GOVERNANCE_NOTE_DE


@patch("analytics.r3_t212_account_identity.assess_account_confirmation")
@patch("analytics.r3_freigabe.refresh_order_surface")
@patch("analytics.live_trading_operations.sync_broker_and_quotes")
@patch("analytics.r3_t212_api_bond.sync_r3_t212_api_bond")
def test_auto_prepare_coalesces_within_45s(mock_bond, mock_sync, mock_surface, mock_acct, tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    mock_acct.return_value = {"needs_confirmation": False, "message_de": "Konto OK"}
    mock_bond.return_value = {"bonded": True, "connected": True, "confirmation_de": "T212 ok"}
    mock_sync.return_value = {"quote_snapshot": {"executable_prices_eur": {"STX": 85.0}}}
    mock_surface.return_value = {"buy_count": 2, "initial_package": {"active": True, "notional_eur": 640.93}}
    auto_prepare_freigabe_for_desktop(tmp_path)
    doc = auto_prepare_freigabe_for_desktop(tmp_path)
    assert doc.get("coalesced") is True
    assert mock_bond.call_count == 1
    assert mock_sync.call_count == 1


def test_governance_note_honest_about_auto_execute() -> None:
    note = freigabe_governance_note_de()
    assert "auto_execute_real_money" in note
    assert "24/7" in note
    assert "einmal in R3" in note


def test_package_ready_requires_active_buys(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    with patch(
        "integrations.trading212.t212_trust_gate.assess_t212_trust_from_root",
        return_value={"orders_allowed": True, "trusted": True},
    ), patch(
        "analytics.r3_t212_account_identity.assess_account_confirmation",
        return_value={"needs_confirmation": False},
    ):
        assert package_ready(tmp_path)["ready"] is True
        orders = json.loads((tmp_path / "evidence/r3_stock_orders_latest.json").read_text())
        orders["initial_package"]["active"] = False
        (tmp_path / "evidence/r3_stock_orders_latest.json").write_text(json.dumps(orders), encoding="utf-8")
        assert package_ready(tmp_path)["ready"] is False


@patch("analytics.r3_freigabe.auto_prepare_freigabe_for_desktop")
def test_desktop_hub_live_prep_before_render(mock_auto, tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_ubuntu_shell.json").write_text(
        json.dumps({"section_title_de": "R3", "features": []}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_surface_identity.json").write_text(
        json.dumps({"title_de": "R3"}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "top_picks": []}),
        encoding="utf-8",
    )
    mock_auto.return_value = {"package_ready": True}

    body = get_desktop_html_for_hub(tmp_path, live_prep=True, allow_stale=False)
    mock_auto.assert_called_once()
    assert b"r3-desktop" in body


def test_resolve_limit_price_prefers_live_snapshot(tmp_path: Path) -> None:
    from analytics.r3_stock_orders import _resolve_limit_price

    row = {"limit_price_eur": 10.0}
    snap = {
        "executable_prices_eur": {"STX": 88.5},
        "price_source_by_symbol": {"STX": "YAHOO"},
    }
    with patch(
        "execution.confirmed_live.us_equity_deferred_intents.limit_price_for_symbol",
        return_value=88.5,
    ):
        assert _resolve_limit_price(tmp_path, "STX", row, quote_snapshot=snap) == 88.5
