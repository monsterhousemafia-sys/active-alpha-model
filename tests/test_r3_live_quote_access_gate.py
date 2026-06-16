"""Live quote access gate — fail-closed refresh authorization."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest


def test_unknown_owner_blocked(tmp_path: Path) -> None:
    from analytics.r3_live_quote_access_gate import check_live_quote_refresh_allowed

    with mock.patch("analytics.r3_live_quote_access_gate._test_bypass", return_value=False):
        gate = check_live_quote_refresh_allowed(tmp_path, owner="headless")
    assert gate["allowed"] is False
    assert gate["error"] == "LIVE_QUOTE_ACCESS_DENIED"


def test_empty_owner_blocked(tmp_path: Path) -> None:
    from analytics.r3_live_quote_access_gate import check_live_quote_refresh_allowed

    with mock.patch("analytics.r3_live_quote_access_gate._test_bypass", return_value=False):
        gate = check_live_quote_refresh_allowed(tmp_path, owner="")
    assert gate["allowed"] is False


def test_king_ops_allowed_with_internet(tmp_path: Path) -> None:
    from analytics.r3_live_quote_access_gate import check_live_quote_refresh_allowed

    policy = tmp_path / "control"
    policy.mkdir(parents=True)
    (policy / "r3_live_quote_access_policy.json").write_text(
        '{"allowed_owners":["king_ops"],"forbidden_owners":["headless"],"refresh_requires_internet":true}',
        encoding="utf-8",
    )
    with mock.patch("analytics.r3_live_quote_access_gate._test_bypass", return_value=False):
        with mock.patch(
            "analytics.r3_internet_requirement.require_internet_for",
            return_value={"allowed": True, "internet_ok": True},
        ):
            gate = check_live_quote_refresh_allowed(tmp_path, owner="king_ops")
    assert gate["allowed"] is True


def test_refresh_blocked_without_owner(tmp_path: Path) -> None:
    from market.live_quote_engine import refresh_live_quotes

    with mock.patch("analytics.r3_live_quote_access_gate._test_bypass", return_value=False):
        snap = refresh_live_quotes(tmp_path, force=True, owner="")
    assert snap.get("live_quote_access_denied") is True
    assert snap.get("executable_prices_eur") == {}


def test_load_snapshot_always_allowed(tmp_path: Path) -> None:
    from market.live_quote_engine import load_live_quote_snapshot, snapshot_path

    path = snapshot_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"generated_at_utc":"2026-06-10T08:00:00+00:00","executable_prices_eur":{"OXY":50.0}}',
        encoding="utf-8",
    )
    loaded = load_live_quote_snapshot(tmp_path)
    assert loaded is not None
    assert loaded["executable_prices_eur"]["OXY"] == 50.0


@pytest.mark.parametrize("owner", ["mirror_poll", "R3_MIRROR", "R3_COCKPIT"])
def test_mirror_poll_owners_allowed(tmp_path: Path, owner: str) -> None:
    from analytics.r3_live_quote_access_gate import check_live_quote_refresh_allowed

    policy = tmp_path / "control"
    policy.mkdir(parents=True)
    (policy / "r3_live_quote_access_policy.json").write_text(
        json.dumps(
            {
                "allowed_owners": [
                    "mirror_poll",
                    "R3_MIRROR",
                    "R3_COCKPIT",
                    "king_ops",
                ],
                "forbidden_owners": ["headless"],
                "refresh_requires_internet": True,
            }
        ),
        encoding="utf-8",
    )
    with mock.patch("analytics.r3_live_quote_access_gate._test_bypass", return_value=False):
        with mock.patch(
            "analytics.r3_internet_requirement.require_internet_for",
            return_value={"allowed": True, "internet_ok": True},
        ):
            gate = check_live_quote_refresh_allowed(tmp_path, owner=owner)
    assert gate["allowed"] is True
