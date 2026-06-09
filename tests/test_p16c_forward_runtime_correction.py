"""P16C forward runtime correction tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from integrations.trading212.t212_demo_readonly_client import T212DemoReadOnlyClient
from paper.p16c.cost_adjusted_allocation import build_cost_adjusted_targets
from paper.p16c.fx_runtime_guard import FX_PAUSED, FX_PASS, classify_fx_observation
from paper.p16c.pnl_attribution import initial_batch_pnl
from paper.p16c.portfolio_state_store import execute_cost_adjusted_initial, load_state, mark_to_market_forward
from research.p16c.p16b_import_verification import EXPECTED_P16B_ZIP_SHA256, verify_p16b_import


def test_static_fx_fallback_not_performance_valid() -> None:
    fx = {"fx_quality_gate": "PARTIAL", "fx_source": "STATIC_FALLBACK_EURUSD"}
    result = classify_fx_observation(fx)
    assert result["fx_runtime_gate"] == FX_PAUSED
    assert result["performance_valid"] is False


def test_readonly_fx_pass() -> None:
    fx = {"fx_quality_gate": "PASS", "fx_source": "READONLY_YFINANCE"}
    result = classify_fx_observation(fx)
    assert result["fx_runtime_gate"] == FX_PASS


def test_initial_cost_not_market_pnl() -> None:
    pnl = initial_batch_pnl(initial_capital_eur=500, initial_cost_eur=0.92, post_fill_value_eur=499.08)
    assert pnl["subsequent_market_price_pnl_eur"] == 0.0
    assert pnl["cumulative_net_pnl_eur"] == pytest.approx(-0.92, abs=0.01)


def test_cost_adjusted_pro_rata(tmp_path: Path) -> None:
    positions = [{"symbol_reference": s, "paper_target_notional_eur": 62.5} for s in ("OXY", "WDC", "STX", "INTC", "MU", "CIEN")]
    adj = build_cost_adjusted_targets(tmp_path, positions=positions, fill_allowed=["OXY", "WDC", "STX", "INTC", "MU", "CIEN"])
    assert len(adj["positions"]) == 6
    total_gross = sum(p["cost_adjusted_target_eur"] for p in adj["positions"])
    assert total_gross + adj["expected_max_cost_eur"] <= 500.01


def test_stateful_no_repeated_initial(tmp_path: Path) -> None:
    targets = [{"symbol_reference": "OXY", "cost_adjusted_target_eur": 100.0}]
    prices = {"OXY": 50.0}
    r1 = execute_cost_adjusted_initial(tmp_path, adjusted_targets=targets, prices_eur=prices, fx_gate_ok=True)
    assert r1["executed"] is True
    r2 = execute_cost_adjusted_initial(tmp_path, adjusted_targets=targets, prices_eur=prices, fx_gate_ok=True)
    assert r2["skipped"] is True
    m1 = mark_to_market_forward(tmp_path, {"OXY": 51.0}, fx_gate_ok=True)
    m2 = mark_to_market_forward(tmp_path, {"OXY": 52.0}, fx_gate_ok=True)
    assert m2.get("subsequent_market_price_pnl_eur") is not None or m2.get("note")


def test_t212_client_opener_path() -> None:
    class FakeCreds:
        api_key = "k"
        api_secret = "s"

    client = T212DemoReadOnlyClient(FakeCreds())
    mock_resp = mock.Mock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
    mock_resp.__exit__ = mock.Mock(return_value=False)
    with mock.patch.object(client._opener, "open", return_value=mock_resp) as opener:
        out = client.get("/equity/account/summary")
        assert out == {"ok": True}
        opener.assert_called_once()


def test_p16b_import(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    result = verify_p16b_import(root)
    assert result["zip_sha256_match"] is True
    assert result["expected_sha256"] == EXPECTED_P16B_ZIP_SHA256


def test_p16c_engine(tmp_path: Path) -> None:
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

    ensure_observation_dir(tmp_path, root, "p16b_continuous_forward_runtime")
    from paper.p16c.engine import run_p16c_forward_correction

    out = run_p16c_forward_correction(tmp_path)
    assert out["simulation_only"] is True
    assert out["static_fx_fallback_excluded_from_performance"] is True
