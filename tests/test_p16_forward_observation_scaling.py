"""P16 forward observation and virtual scaling evidence tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.trading212.t212_environment_guard import assert_demo_url, validate_redirect_target
from integrations.trading212.t212_query_policy import validate_query_for_path
from integrations.trading212.t212_request_allowlist import validate_get_path, validate_method
from integrations.trading212.t212_secret_redaction import contains_likely_secret, redact_secrets
from paper.p16.engine import run_p16_forward_observation
from paper.p16.forward_feed import DATA_MODE_FIXTURE, DATA_MODE_FORWARD
from paper.p16.mappings import build_primary_market_data_mapping
from paper.p16.test_fixtures import static_prices_for_fixture
from research.p16.p15_import_verification import EXPECTED_P15_ZIP_SHA256, verify_p15_import


@pytest.mark.parametrize(
    "url",
    [
        "https://live.trading212.com/api/v0/equity/account/summary",
        "https://demo.trading212.com.evil.com/api/v0/equity/account/summary",
        "http://demo.trading212.com/api/v0/equity/account/summary",
        "https://user:pass@demo.trading212.com/api/v0/equity/account/summary",
        "https://demo.trading212.com:8443/api/v0/equity/account/summary",
        "https://demo.trading212.com/api/v0/equity/account/summary#frag",
        "https://demo.trading212.com/api/v00/equity/account/summary",
        "https://demo.trading212.com/api/v0evil/equity/account/summary",
    ],
)
def test_t212_blocked_urls(url: str) -> None:
    with pytest.raises(PermissionError):
        assert_demo_url(url)


def test_t212_demo_url_allowed() -> None:
    assert_demo_url("https://demo.trading212.com/api/v0/equity/account/summary")


def test_t212_unknown_query_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_query_for_path("/equity/metadata/instruments", "foo=bar")


def test_t212_write_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_method("POST", "/equity/orders/market")


def test_t212_order_path_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_get_path("/equity/orders/market")


def test_t212_pies_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_get_path("/equity/pies")


def test_redirect_live_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_redirect_target("https://live.trading212.com/api/v0/equity/account/summary")


def test_redirect_lookalike_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_redirect_target("https://demo.trading212.com.evil.com/api/v0/equity/account/summary")


def test_secret_redaction() -> None:
    raw = "TRADING212_API_SECRET=abc123"
    assert "abc123" not in redact_secrets(raw)
    assert not contains_likely_secret(redact_secrets(raw))


def test_fixture_not_forward_mode() -> None:
    prices = static_prices_for_fixture(["OXY"])
    assert prices["OXY"] > 0


def test_p15_import(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    result = verify_p15_import(root)
    assert result["zip_present"] is True
    assert result["expected_zip_sha256"] == EXPECTED_P15_ZIP_SHA256
    assert result["zip_sha256_match"] is True
    assert not result["unsafe_zip_paths"]
    assert not result["bytecode_entries"]


def test_primary_mapping(tmp_path: Path) -> None:
    import shutil

    root = Path(__file__).resolve().parents[1]
    for rel in (
        "paper/config/p14_user_reference_allocation_500eur.json",
        "paper/config/p16_forward_observation_and_scaling_policy.json",
    ):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    mapping = build_primary_market_data_mapping(tmp_path)
    assert mapping["instrument_mappings_verified"] == "8/8"


def test_p16_engine_minimal(tmp_path: Path) -> None:
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

    ensure_observation_dir(tmp_path, root, "p15_paper_runtime_validation")
    out = run_p16_forward_observation(tmp_path)
    assert out["initial_paper_capital_eur"] == 500.0
    assert out["simulation_only"] is True
    assert out["broker_order_sent"] is False
    assert out["p16_scope_classification"].startswith("FORWARD_OBSERVATION")
