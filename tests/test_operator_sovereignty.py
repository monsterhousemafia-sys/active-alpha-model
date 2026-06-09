from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from analytics.operator_sovereignty import (
    assert_privileged_action,
    check_privileged_action,
    detect_invocation_source,
    record_natural_language_mandate,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AA_OPERATOR_CHANNEL",
        "INVOCATION_ID",
        "CRON",
        "AA_INVOCATION_SOURCE",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_policy(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "control/operator_sovereignty_policy.json"
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/operator_sovereignty_policy.json").write_text(
        src.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_systemd_blocked_for_h1_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_policy(tmp_path)
    monkeypatch.setenv("INVOCATION_ID", "abc-123")
    doc = check_privileged_action(tmp_path, "h1-force")
    assert doc["ok"] is False
    assert doc["source"] == "systemd"
    assert "Systemd" in doc["blocked_de"]


def test_conversational_with_mandate_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_policy(tmp_path)
    monkeypatch.setenv("AA_OPERATOR_CHANNEL", "conversational")
    mandate = record_natural_language_mandate(
        tmp_path,
        utterance_de="Bitte H1 mit Gewalt fortsetzen",
        authorized_actions=["h1-force"],
    )
    assert mandate["ok"] is True
    ok, doc = assert_privileged_action(tmp_path, "h1-force")
    assert ok is True
    assert doc["source"] == "conversational"


def test_raw_cli_blocked_without_mandate(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    doc = check_privileged_action(tmp_path, "lean-max")
    assert doc["ok"] is False
    assert doc["source"] == "raw_cli"


def test_routine_status_allowed_from_systemd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_policy(tmp_path)
    monkeypatch.setenv("INVOCATION_ID", "timer-run")
    doc = check_privileged_action(tmp_path, "status")
    assert doc["ok"] is True
    assert doc["privileged"] is False


def test_expired_mandate_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_policy(tmp_path)
    monkeypatch.setenv("AA_OPERATOR_CHANNEL", "conversational")
    expired = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat()
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/operator_natural_language_ack.json").write_text(
        json.dumps(
            {
                "ok": True,
                "authorized_actions": ["lean-max"],
                "expires_at_utc": expired,
            }
        ),
        encoding="utf-8",
    )
    doc = check_privileged_action(tmp_path, "lean-max")
    assert doc["ok"] is False


def test_detect_invocation_source_conversational(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AA_OPERATOR_CHANNEL", "conversational")
    assert detect_invocation_source() == "conversational"
