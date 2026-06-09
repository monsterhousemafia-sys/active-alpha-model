"""P16D validated forward runtime hardening tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import mock

import pytest

from integrations.trading212.t212_demo_readonly_client import T212DemoReadOnlyClient
from paper.p16d.data_quality_stateful import assess_observation, load_dq_state
from paper.p16d.fx_runtime_guard import FX_PASS, FX_PAUSED, classify_fx_observation, fx_available_for_currency
from paper.p16d.portfolio_identity import EXECUTABLE_SYMBOLS, REFERENCE_SYMBOLS
from paper.p16d.portfolio_state_store import migrate_checkpoint_from_p16c, mark_to_market_post_baseline
from paper.p16d.quote_unit_normalization import normalize_quote_price
from research.p16d.p16c_import_verification import EXPECTED_P16C_ZIP_SHA256, verify_p16c_import


def test_p16c_import(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    result = verify_p16c_import(root)
    assert result["zip_sha256_match"] is True
    assert result["expected_sha256"] == EXPECTED_P16C_ZIP_SHA256


def test_gbp_pence_normalization() -> None:
    norm, meta = normalize_quote_price(raw_price=1680.0, exchange="LSE", quote_currency="GBP", instrument_type="ETF")
    assert meta["raw_price_unit"] == "GBp"
    assert norm == pytest.approx(16.8, rel=0.01)


def test_multi_currency_fx_pass() -> None:
    fx = {
        "usd_fx_quality_gate": "PASS",
        "gbp_fx_quality_gate": "PASS",
        "usd_to_eur_rate": 0.86,
        "gbp_to_eur_rate": 1.17,
    }
    result = classify_fx_observation(fx)
    assert result["fx_runtime_gate"] == FX_PASS
    assert fx_available_for_currency(fx, "GBP") is True


def test_missing_gbp_fx_pauses() -> None:
    fx = {"usd_fx_quality_gate": "PASS", "gbp_fx_quality_gate": "FAIL", "usd_to_eur_rate": 0.86}
    result = classify_fx_observation(fx)
    assert result["fx_runtime_gate"] == FX_PAUSED


def test_portfolio_identity_separation() -> None:
    assert len(REFERENCE_SYMBOLS) == 8
    assert len(EXECUTABLE_SYMBOLS) == 6
    assert "VUSD" not in EXECUTABLE_SYMBOLS
    assert "CIEN" in EXECUTABLE_SYMBOLS


def test_baseline_not_performance_event() -> None:
    dq = {"post_baseline_batch_count": 0, "p16d_hardening_complete": False}
    r = assess_observation(
        symbol="OXY",
        raw_price=50.0,
        quote_currency="USD",
        event_time_utc="2026-06-01T12:00:00+00:00",
        ingestion_time_utc="2026-06-01T12:00:01+00:00",
        dq_state=dq,
        fx_available=True,
        identity_action="VIRTUAL_FILL_VALID",
        batch_fingerprint="abc",
    )
    assert "BASELINE" in r["outlier_status"] or r["gate"].startswith("PASS")


def test_no_reinitialization(tmp_path: Path) -> None:
    ck = tmp_path / "paper/p16c/runtime_checkpoint.json"
    ck.parent.mkdir(parents=True, exist_ok=True)
    ck.write_text(
        json.dumps(
            {
                "initial_allocation_executed": True,
                "cash_eur": 100,
                "positions": [{"symbol": "OXY", "shares": 1, "avg_cost_eur": 50}],
                "mark_count": 1,
                "last_mark_value_eur": 150,
                "initial_post_fill_portfolio_value_eur": 150,
                "initial_capital_eur": 500,
                "initial_execution_cost_eur": 0.5,
            }
        ),
        encoding="utf-8",
    )
    state = migrate_checkpoint_from_p16c(tmp_path)
    assert state["no_reinitialization"] is True
    assert state["migrated_from_p16c"] is True


def test_post_baseline_mtm(tmp_path: Path) -> None:
    ck = tmp_path / "paper/p16c/runtime_checkpoint.json"
    ck.parent.mkdir(parents=True, exist_ok=True)
    ck.write_text(
        json.dumps(
            {
                "initial_allocation_executed": True,
                "cash_eur": 100,
                "positions": [{"symbol": "OXY", "shares": 2, "avg_cost_eur": 50, "last_mark_eur": 50}],
                "mark_count": 1,
                "last_mark_value_eur": 200,
                "initial_post_fill_portfolio_value_eur": 200,
                "initial_capital_eur": 500,
                "initial_execution_cost_eur": 0.5,
                "subsequent_market_price_pnl_eur": 0,
            }
        ),
        encoding="utf-8",
    )
    m1 = mark_to_market_post_baseline(tmp_path, {"OXY": 50}, fx_gate_ok=True)
    assert m1.get("independent_post_baseline_mark") is False
    m2 = mark_to_market_post_baseline(tmp_path, {"OXY": 52}, fx_gate_ok=True)
    assert m2.get("independent_post_baseline_mark") is True


def test_t212_client_path() -> None:
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


def test_p16d_engine(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "paper/config/p14_user_reference_allocation_500eur.json",
        "paper/config/p16_forward_observation_and_scaling_policy.json",
    ):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    from tests.paper_observation_stub import ensure_observation_dir

    ensure_observation_dir(tmp_path, root, "p16c_forward_runtime_correction")
    ck_src = root / "paper/p16c/runtime_checkpoint.json"
    if ck_src.is_file():
        ck_dst = tmp_path / "paper/p16c/runtime_checkpoint.json"
        ck_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ck_src, ck_dst)

    with mock.patch("paper.p16d.multi_currency_fx_feed.fetch_multi_currency_fx") as mfx:
        mfx.return_value = {
            "usd_fx_quality_gate": "PASS",
            "gbp_fx_quality_gate": "PASS",
            "usd_to_eur_rate": 0.86,
            "gbp_to_eur_rate": 1.17,
            "usd_fx_source": "TEST_FIXTURE",
            "gbp_fx_source": "TEST_FIXTURE",
            "fx_event_time_utc": "2026-06-01T12:00:00+00:00",
        }
        from paper.p16d.engine import run_p16d_forward_hardening

        out = run_p16d_forward_hardening(tmp_path)
    assert out["simulation_only"] is True
    assert out["portfolio_identity"]["full_reference_claimed_as_executed"] is False
