"""P15 paper runtime validation tests."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from integrations.trading212.t212_environment_guard import DEMO_BASE_URL, assert_demo_url
from integrations.trading212.t212_request_allowlist import ALLOWED_GET_PATHS, validate_get_path, validate_method
from integrations.trading212.t212_secret_redaction import contains_likely_secret, redact_secrets
from paper.p15.engine import run_p15_paper_runtime
from paper.p15.status_model import classify_p14_legacy_runtime
from paper.p15.test_fixtures import INITIALIZATION_DEMO_LABEL, static_prices_for_mode
from research.p15.p14_import_verification import EXPECTED_P14_ZIP_SHA256, verify_p14_import


def test_t212_live_host_blocked() -> None:
    with pytest.raises(PermissionError, match="LIVE"):
        assert_demo_url("https://live.trading212.com/api/v0/equity/account/summary")


def test_t212_lookalike_host_blocked() -> None:
    with pytest.raises(PermissionError):
        assert_demo_url("https://demo.trading212.com.evil.com/api/v0/equity/account/summary")


def test_t212_demo_url_allowed() -> None:
    assert_demo_url(DEMO_BASE_URL)


def test_t212_non_https_blocked() -> None:
    with pytest.raises(PermissionError):
        assert_demo_url("http://demo.trading212.com/api/v0/equity/account/summary")


def test_t212_write_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_method("POST", "/equity/orders/market")


def test_t212_exact_allowlist_only() -> None:
    for path in ALLOWED_GET_PATHS:
        validate_get_path(path)
    with pytest.raises(PermissionError):
        validate_get_path("/equity/account/summary/extra")


def test_t212_order_path_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_get_path("/equity/orders/market")


def test_secret_redaction() -> None:
    raw = "TRADING212_API_SECRET=supersecretvalue"
    redacted = redact_secrets(raw)
    assert "supersecretvalue" not in redacted
    assert not contains_likely_secret(redacted)


def test_static_prices_not_for_forward_mode() -> None:
    with pytest.raises(ValueError):
        static_prices_for_mode(mode="READ_ONLY_FORWARD_OBSERVATION", symbols=["OXY"])


def test_static_prices_allowed_for_demo() -> None:
    prices = static_prices_for_mode(mode=INITIALIZATION_DEMO_LABEL, symbols=["OXY", "VUSD"])
    assert prices["OXY"] == 45.0


def test_p14_status_adjudication_model() -> None:
    status = classify_p14_legacy_runtime()
    assert status["p14_validated_forward_observation_runtime"] == "NOT_YET_PROVEN"


def test_p14_import_verification(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    result = verify_p14_import(root)
    assert result["zip_present"] is True
    assert result["expected_zip_sha256"] == EXPECTED_P14_ZIP_SHA256
    assert result["zip_sha256_match"] is True
    assert not result["unsafe_zip_paths"]
    assert not result["bytecode_entries"]


def test_p15_runtime(tmp_path: Path) -> None:
    import shutil

    root = Path(__file__).resolve().parents[1]
    for rel in (
        "paper/config/p14_user_reference_allocation_500eur.json",
        "paper/config/p14_paper_evaluation_policy.json",
    ):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    from tests.paper_observation_stub import ensure_observation_dir

    ensure_observation_dir(tmp_path, root, "p14_paper_forward")
    out = run_p15_paper_runtime(tmp_path)
    assert out["initial_capital_eur"] == 500.0
    assert out["simulation_only"] is True
    assert out["broker_order_sent"] is False
    assert out["p14_adjudication"]["p14_previously_claimed_forward_runtime_downgraded"] is True
