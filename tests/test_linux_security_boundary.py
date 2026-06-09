"""Linux compute host must not submit live broker orders."""
from __future__ import annotations

import pytest


def test_linux_blocks_live_submission(monkeypatch) -> None:
    monkeypatch.setattr("execution.linux_security_boundary.sys.platform", "linux")
    monkeypatch.delenv("AA_LINUX_ALLOW_LIVE_ORDERS", raising=False)
    monkeypatch.delenv("AA_LINUX_NATIVE_APP", raising=False)

    from execution.linux_security_boundary import (
        assert_live_submission_host_allowed,
        live_order_submission_blocked,
    )

    assert live_order_submission_blocked()
    from integrations.trading212.t212_confirmed_execution_client import T212ExecutionBlockedError

    with pytest.raises(T212ExecutionBlockedError, match="LIVE_ORDERS_FORBIDDEN"):
        assert_live_submission_host_allowed()


def test_linux_override_allows_when_explicit(monkeypatch) -> None:
    monkeypatch.setattr("execution.linux_security_boundary.sys.platform", "linux")
    monkeypatch.setenv("AA_LINUX_ALLOW_LIVE_ORDERS", "1")

    from execution.linux_security_boundary import live_order_submission_blocked

    assert not live_order_submission_blocked()


def test_linux_native_app_not_blocked(monkeypatch) -> None:
    monkeypatch.setattr("execution.linux_security_boundary.sys.platform", "linux")
    monkeypatch.delenv("AA_LINUX_ALLOW_LIVE_ORDERS", raising=False)
    monkeypatch.setenv("AA_LINUX_NATIVE_APP", "1")

    from execution.linux_security_boundary import live_order_submission_blocked

    assert not live_order_submission_blocked()


def test_windows_not_blocked(monkeypatch) -> None:
    monkeypatch.setattr("execution.linux_security_boundary.sys.platform", "win32")

    from execution.linux_security_boundary import live_order_submission_blocked

    assert not live_order_submission_blocked()
