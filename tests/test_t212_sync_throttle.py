from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from integrations.trading212.t212_sync_throttle import (
    can_test_connection_now,
    is_auth_error,
    is_rate_limit_error,
    record_connection_test,
    record_sync_attempt,
    should_sync_now,
)


def test_rate_limit_detection() -> None:
    assert is_rate_limit_error("HTTP 429")
    assert not is_rate_limit_error("HTTP 401")


def test_auth_error_detection() -> None:
    assert is_auth_error("HTTP 401")
    assert is_auth_error("unauthorized")
    assert not is_auth_error("HTTP 429")


def test_should_sync_respects_interval(tmp_path: Path) -> None:
    record_sync_attempt(tmp_path, success=True)
    allow, reason = should_sync_now(tmp_path, force=False, last_successful_sync_utc=None)
    assert allow is False
    assert "pausiert" in reason.lower() or "warten" in reason.lower()


def test_force_sync_after_recent_full_sync_blocked(tmp_path: Path) -> None:
    record_sync_attempt(tmp_path, success=True)
    allow, _ = should_sync_now(tmp_path, force=True)
    assert allow is False


def test_connection_test_does_not_block_sync(tmp_path: Path) -> None:
    record_connection_test(tmp_path, success=True)
    allow, _ = should_sync_now(tmp_path, force=True)
    assert allow is True


def test_stale_cache_allows_sync(tmp_path: Path) -> None:
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    allow, _ = should_sync_now(tmp_path, force=False, last_successful_sync_utc=old)
    assert allow is True


def test_test_connection_throttled_after_double_click(tmp_path: Path) -> None:
    record_connection_test(tmp_path, success=True)
    allow, reason = can_test_connection_now(tmp_path)
    assert allow is False
    assert "warten" in reason.lower()


def test_test_connection_rate_limit_does_not_block_sync(tmp_path: Path) -> None:
    record_connection_test(tmp_path, success=False, error="HTTP 429")
    allow, _ = should_sync_now(tmp_path, force=True)
    assert allow is True


def test_test_connection_blocked_after_rate_limit(tmp_path: Path) -> None:
    record_connection_test(tmp_path, success=False, error="HTTP 429")
    allow, reason = can_test_connection_now(tmp_path)
    assert allow is False
    assert "Anfragen" in reason or "warten" in reason.lower() or "Test" in reason
