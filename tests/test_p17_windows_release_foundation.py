"""P17 Windows release foundation tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from execution.confirmed_live.cancellation_confirmation_service import (
    cancel_confirmation_phrase,
    issue_cancel_token,
    submit_cancel,
)
from execution.confirmed_live.confirmed_execution_mode_controller import ACTIVATION_PHRASE, activate_by_user
from execution.confirmed_live.order_confirmation_token_service import issue_token, validate_and_consume
from execution.confirmed_live.p17_review_mode_guard import (
    BLOCK_REASON,
    assert_live_network_submission_allowed,
    review_mode_active,
)
from execution.confirmed_live.unknown_broker_state_guard import register_unknown
from integrations.trading212.t212_confirmed_execution_client import T212ConfirmedExecutionClient, T212ExecutionBlockedError
from integrations.trading212.t212_credentials_loader import T212Credentials
from integrations.trading212.t212_secret_scan import scan_text
from research.p17.p16h_import_verification import verify_p16h_import
from research.p17.p17_gap_backlog import gap_backlog


@pytest.fixture(autouse=True)
def _p17_review_mode(monkeypatch):
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")


def test_p17_review_mode_default_on():
    assert review_mode_active() is True


def test_live_submission_blocked_by_p17_guard():
    with pytest.raises(RuntimeError, match=BLOCK_REASON):
        assert_live_network_submission_allowed()


def test_execution_client_blocked_in_p17():
    client = T212ConfirmedExecutionClient(T212Credentials("k", "s"))
    with pytest.raises(T212ExecutionBlockedError, match="P17_REVIEW_MODE"):
        client.submit_limit_order({"ticker": "X", "quantity": 1, "limitPrice": 1})


def test_core_live_activation_blocked_in_p17(tmp_path: Path):
    r = activate_by_user(tmp_path, phrase=ACTIVATION_PHRASE, risk_ack=True)
    assert not r.get("ok")
    assert "P17" in str(r.get("error", ""))


def test_p16h_import_verification(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    v = verify_p16h_import(root)
    assert v.get("artefact_folder_found") is True
    assert v.get("package_zip_found") is True


def test_gap_backlog_has_p17_items():
    bl = gap_backlog()
    assert len(bl["gaps"]) >= 10


def test_secret_scan_detects_auth_header():
    hits = scan_text("Authorization: Basic abcdef1234567890")
    assert hits


def test_cancel_mock_in_p17(tmp_path: Path):
    order = {"order_id": "MOCK-1", "instrument": "OXY", "quantity": 1}
    issued = issue_cancel_token(tmp_path, order, profile="test")
    assert "STORNIERUNG" in cancel_confirmation_phrase(order)
    result = submit_cancel(tmp_path, order, one_time_token=issued["one_time_token"])
    assert result.get("ok")
    assert result.get("mock") is True


def test_unknown_state_no_auto_retry(tmp_path: Path):
    register_unknown(tmp_path, draft_id="d1", context="timeout")
    from execution.confirmed_live.unknown_broker_state_guard import blocks_submission

    assert blocks_submission(tmp_path) is True


def test_token_expiry_invalidates(tmp_path: Path):
    from datetime import datetime, timedelta, timezone
    import json

    payload = {"instrument": "OXY", "side": "BUY", "max_notional_eur": 50.0, "limit_price": 50.0, "quantity": 1, "order_type": "LIMIT_BUY", "t212_instrument_id": "OXY_US_EQ"}
    issued = issue_token(tmp_path, payload, profile="X")
    token_id = issued["one_time_token"].split(":", 1)[0]
    path = tmp_path / "live_pilot/confirmed_execution/confirmation_tokens" / f"{token_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["expires_at_utc"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(data), encoding="utf-8")
    v = validate_and_consume(tmp_path, issued["one_time_token"], payload)
    assert v.get("error") == "TOKEN_EXPIRED"


def test_first_run_flag(tmp_path: Path):
    from ui.interactive_cockpit.first_run_onboarding import first_run_required, mark_first_run_completed

    assert first_run_required(tmp_path) is True
    mark_first_run_completed(tmp_path)
    assert first_run_required(tmp_path) is False


def test_windows_credential_storage_status():
    from integrations.trading212.t212_windows_credential_store_adapter import storage_status

    assert storage_status().startswith("PASS_")


def test_p16h_and_p17_tests_together():
    """Meta — ensures module imports."""
    assert os.environ.get("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION") == "1"
