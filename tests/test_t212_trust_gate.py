"""T212 Trust Gate — fail-closed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from integrations.trading212.t212_trust_gate import assess_t212_trust, sync_age_seconds


def _fresh_broker() -> dict:
    return {
        "status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "credentials_configured": True,
        "last_successful_sync_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "cash_eur": 675.0,
        "positions_count": 0,
    }


def test_trusted_fresh_sync() -> None:
    doc = assess_t212_trust(_fresh_broker())
    assert doc["trusted"] is True
    assert doc["orders_allowed"] is True
    assert doc["reason_code"] == "OK"


def test_untrusted_auth_expired() -> None:
    doc = assess_t212_trust(
        {
            "status": "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA",
            "credentials_configured": True,
            "last_successful_sync_utc": "2026-06-08T02:00:00+00:00",
            "cash_eur": 675.0,
        }
    )
    assert doc["trusted"] is False
    assert doc["orders_allowed"] is False
    assert doc["message_de"] == "API prüfen"


def test_untrusted_stale_sync() -> None:
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).isoformat()
    doc = assess_t212_trust(
        {
            "status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
            "credentials_configured": True,
            "last_successful_sync_utc": old,
            "cash_eur": 675.0,
        }
    )
    assert doc["trusted"] is False
    assert doc["reason_code"] == "STALE_SYNC"


def test_cached_readonly_untrusted() -> None:
    doc = assess_t212_trust(
        {
            "status": "CACHED_READONLY_DATA",
            "credentials_configured": True,
            "last_successful_sync_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "cash_eur": 675.0,
        }
    )
    assert doc["trusted"] is False
    assert doc["orders_allowed"] is False


def test_sync_age_seconds() -> None:
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    age = sync_age_seconds(ts)
    assert age is not None
    assert age < 5


def test_order_gate_blocks_untrusted(tmp_path) -> None:
    from tests.r3_order_fixtures import seed_operator_api_complete

    seed_operator_api_complete(tmp_path)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "live_pilot/manual_execution/readonly_real_account_state").mkdir(parents=True)
    import json

    (tmp_path / "live_pilot/manual_execution/readonly_real_account_state/latest_sync.json").write_text(
        json.dumps(
            {
                "synced_at_utc": "2020-01-01T00:00:00+00:00",
                "cash_eur": 100.0,
                "status": "CACHED_READONLY_DATA",
                "environment": "LIVE_READ_ONLY",
                "positions_count": 0,
                "positions": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_order_execution_policy.json").write_text(
        json.dumps({"allowed_order_sources": ["R3_DESKTOP"]}),
        encoding="utf-8",
    )
    from analytics.r3_order_execution_gate import check_order_execution_allowed

    gate = check_order_execution_allowed(tmp_path, source="R3_DESKTOP", operation="initial_package")
    assert gate.get("allowed") is False
    assert gate.get("error") == "T212_UNTRUSTED"
