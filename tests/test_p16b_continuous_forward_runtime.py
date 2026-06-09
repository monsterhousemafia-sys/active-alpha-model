"""P16B continuous forward runtime tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from integrations.trading212.t212_demo_readonly_client import T212DemoReadOnlyClient
from integrations.trading212.t212_environment_guard import assert_demo_url
from paper.p16b.engine import run_p16b_continuous_forward
from paper.p16b.fx_readonly_feed import convert_usd_to_eur
from paper.p16b.portfolio_state_store import execute_initial_allocation, load_state, mark_to_market
from paper.p16b.valuation_engine import value_quote
from research.p16b.p16_import_verification import EXPECTED_P16_ZIP_SHA256, verify_p16_import


def test_usd_never_used_as_eur_directly() -> None:
    fx = {"usd_to_eur_rate": 0.9, "fx_quality_gate": "PASS", "fx_event_time_utc": "2026-01-01T00:00:00+00:00", "fx_source": "test"}
    val = value_quote(symbol="OXY", raw_price=100.0, quote_currency="USD", fx_obs=fx)
    assert val["converted_price_eur"] == 90.0
    assert val["quote_currency"] == "USD"


def test_fx_gate_fail_blocks_conversion() -> None:
    with pytest.raises(ValueError):
        convert_usd_to_eur(100.0, {"fx_quality_gate": "FAIL", "usd_to_eur_rate": 0.9})


def test_stateful_portfolio_no_repeated_initial_buys(tmp_path: Path) -> None:
    targets = [{"symbol_reference": "OXY", "paper_target_notional_eur": 100.0}]
    prices = {"OXY": 50.0}
    r1 = execute_initial_allocation(tmp_path, targets=targets, prices_eur=prices)
    assert r1["executed"] is True
    r2 = execute_initial_allocation(tmp_path, targets=targets, prices_eur=prices)
    assert r2["skipped"] is True
    mark_to_market(tmp_path, {"OXY": 51.0})
    state = load_state(tmp_path)
    assert state["initial_allocation_executed"] is True


def test_t212_client_mock_get_path() -> None:
    class FakeCreds:
        api_key = "k"
        api_secret = "s"

    client = T212DemoReadOnlyClient(FakeCreds())
    mock_resp = mock.Mock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
    mock_resp.__exit__ = mock.Mock(return_value=False)
    with mock.patch.object(client._opener, "open", return_value=mock_resp):
        out = client.get("/equity/account/summary")
        assert out == {"ok": True}


def test_p16_import(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    result = verify_p16_import(root)
    assert result["zip_sha256_match"] is True
    assert result["expected_zip_sha256"] == EXPECTED_P16_ZIP_SHA256


def test_p16b_engine(tmp_path: Path) -> None:
    import shutil

    root = Path(__file__).resolve().parents[1]
    for rel in (
        "paper/config/p14_user_reference_allocation_500eur.json",
        "paper/config/p16_forward_observation_and_scaling_policy.json",
    ):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    from tests.paper_observation_stub import ensure_observation_dir

    ensure_observation_dir(tmp_path, root, "p16_forward_observation_scaling")
    out = run_p16b_continuous_forward(tmp_path)
    assert out["simulation_only"] is True
    assert out["repeated_initial_buys_blocked"] is True
