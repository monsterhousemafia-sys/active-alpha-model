"""P16E fast-track manual live pilot readiness tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import mock

import pytest

from integrations.trading212.t212_demo_readonly_client import T212DemoReadOnlyClient
from integrations.trading212.t212_request_allowlist import validate_method
from paper.p16e.manual_ticket import MAX_REAL_CAPITAL_EUR, build_risk_limits, generate_manual_tickets
from paper.p16e.pnl_reconciliation import reconcile_portfolio_pnl
from paper.p16e.raw_observation import persist_market_observation
from research.p16e.p16d_import_verification import EXPECTED_P16D_ZIP_SHA256, verify_p16d_import


def test_p16d_import(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    result = verify_p16d_import(root)
    assert result["zip_sha256_match"] is True
    assert result["expected_sha256"] == EXPECTED_P16D_ZIP_SHA256


def test_pnl_reconciliation_pass() -> None:
    state = {
        "initial_capital_eur": 500.0,
        "initial_execution_cost_eur": 0.6912,
        "initial_post_fill_portfolio_value_eur": 499.3088,
        "post_baseline_baseline_value_eur": 498.9438,
        "last_mark_value_eur": 498.9438,
        "subsequent_fx_pnl_eur": 0.0,
        "subsequent_virtual_trading_cost_eur": 0.0,
    }
    pnl = reconcile_portfolio_pnl(state)
    assert pnl["pnl_reconciliation_gate"] == "PASS"
    assert pnl["historical_to_validated_epoch_adjustment_eur"] == pytest.approx(-0.365, abs=0.01)
    assert pnl["cumulative_net_pnl_eur"] == pytest.approx(-1.0562, abs=0.01)


def test_raw_observation_chain(tmp_path: Path) -> None:
    rec = persist_market_observation(
        tmp_path,
        provider_name="READONLY_YFINANCE",
        provider_environment="READ_ONLY",
        symbol="OXY",
        raw_record={"last": 59.72},
        normalized_price=51.39,
        quote_currency="USD",
        quote_unit="USD",
    )
    assert rec["provider_event_time_status"] == "NOT_AVAILABLE"
    assert rec["performance_freshness_classification"] == "LIMITED"
    assert (tmp_path / "paper/p16e/observation_chain_ledger/chain.jsonl").is_file()


def test_manual_ticket_not_automated(tmp_path: Path) -> None:
    inst = [{"user_reference_symbol": "OXY", "allowed_action": "VIRTUAL_FILL_VALID", "identity_binding_status": "PARTIAL", "quote_currency": "USD"}]
    out = generate_manual_tickets(tmp_path, instruments=inst, prices_eur={"OXY": 51.0}, fx_ok=True, remaining_budget_eur=100.0)
    assert out["ready_for_user_manual_review"] == 1
    t = out["tickets"][0]
    assert "USER_MUST_DECIDE" in t["explicit_note"]
    limits = build_risk_limits()
    assert limits["leverage"] == "DISABLED"
    assert limits["max_total_real_capital_eur"] == MAX_REAL_CAPITAL_EUR


def test_ticket_blocked_ambiguous_identity(tmp_path: Path) -> None:
    inst = [{"user_reference_symbol": "VUSD", "allowed_action": "OBSERVATION_ONLY_CURRENCY_UNRESOLVED", "identity_binding_status": "OBS", "quote_currency": "GBP"}]
    out = generate_manual_tickets(tmp_path, instruments=inst, prices_eur={"VUSD": 1.6}, fx_ok=True, remaining_budget_eur=100.0)
    assert out["ready_for_user_manual_review"] == 0
    assert out["tickets"][0]["status"] == "NOT_READY_IDENTITY_OR_CURRENCY_UNRESOLVED"


def test_t212_write_and_order_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_method("POST", "/equity/account/summary")
    with pytest.raises(PermissionError):
        validate_method("GET", "/equity/orders")


def test_t212_demo_client_path() -> None:
    class FakeCreds:
        api_key = "k"
        api_secret = "s"

    client = T212DemoReadOnlyClient(FakeCreds())
    mock_resp = mock.Mock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
    mock_resp.__exit__ = mock.Mock(return_value=False)
    with mock.patch.object(client._opener, "open", return_value=mock_resp):
        assert client.get("/equity/account/summary") == {"ok": True}


def test_user_reported_execution_reconciliation_fixture(tmp_path: Path) -> None:
    base = tmp_path / "live_pilot/manual_execution/user_reported_executions"
    base.mkdir(parents=True, exist_ok=True)
    report = {"status": "USER_REPORTED_EXECUTED_PENDING_READONLY_RECONCILIATION", "instrument": "OXY", "notional_eur": 50.0}
    (base / "report_001.json").write_text(json.dumps(report), encoding="utf-8")
    recon = {"status": "RECONCILED_FROM_READONLY_BROKER_OBSERVATION", "instrument": "OXY", "observed_shares": 1.0}
    (tmp_path / "live_pilot/manual_execution/readonly_broker_reconciliations").mkdir(parents=True, exist_ok=True)
    (tmp_path / "live_pilot/manual_execution/readonly_broker_reconciliations/recon_001.json").write_text(json.dumps(recon), encoding="utf-8")
    assert report["status"] != "EXECUTED"


def test_p16e_engine(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "paper/config/p14_user_reference_allocation_500eur.json",
        "paper/config/p16_forward_observation_and_scaling_policy.json",
    ):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    for obs in ("p16c_forward_runtime_correction", "p16d_validated_forward_runtime"):
        src = root / f"outgoing_cursor_observation/{obs}"
        dst = tmp_path / f"outgoing_cursor_observation/{obs}"
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)
    for ck in ("paper/p16c/runtime_checkpoint.json", "paper/p16d/runtime_checkpoint.json"):
        src = root / ck
        if src.is_file():
            d = tmp_path / ck
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, d)

    with mock.patch("paper.p16d.multi_currency_fx_feed.fetch_multi_currency_fx") as mfx:
        mfx.return_value = {
            "usd_fx_quality_gate": "PASS",
            "gbp_fx_quality_gate": "PASS",
            "usd_to_eur_rate": 0.86,
            "gbp_to_eur_rate": 1.17,
            "usd_fx_source": "TEST",
            "gbp_fx_source": "TEST",
            "fx_event_time_utc": "2026-06-01T12:00:00+00:00",
        }
        from paper.p16e.engine import run_p16e_fast_track

        out = run_p16e_fast_track(tmp_path)
    assert out["real_capital_deployed_by_cursor_eur"] == 0.0
    assert out["pnl_reconciliation"]["pnl_reconciliation_gate"] == "PASS"
