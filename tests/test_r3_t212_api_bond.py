"""R3 ↔ Trading212 API — zentrale Bond-Verbindung."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from analytics.r3_t212_api_bond import (
    build_r3_t212_api_bond,
    load_bond_policy,
    render_r3_t212_bond_confirmation,
    sync_r3_t212_api_bond,
)


def _broker_ok() -> dict:
    return {
        "status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "environment": "LIVE_READ_ONLY",
        "credentials_configured": True,
        "last_successful_sync_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "positions_count": 5,
        "cash_eur": 675.0,
    }


def test_bond_policy_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_bond_policy(root)
    assert policy.get("status") == "AUTHORITATIVE"
    assert policy.get("bond_mode") == "persistent"
    assert policy.get("read_only") is True


def test_build_bond_persists_lock(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_t212_api_bond_policy.json").write_text("{}", encoding="utf-8")
    with patch("analytics.r3_t212_api_bond._broker_snapshot", return_value=_broker_ok()):
        doc = build_r3_t212_api_bond(tmp_path, persist=True)
    assert doc.get("bonded") is True
    assert doc.get("connected") is True
    assert "verbunden" in str(doc.get("confirmation_de") or "").lower()
    assert (tmp_path / "control/r3_t212_api_bond.json").is_file()
    assert (tmp_path / "evidence/r3_t212_api_bond_latest.json").is_file()


def test_bond_warns_on_expired_credentials_cache(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_t212_api_bond_policy.json").write_text("{}", encoding="utf-8")
    with patch(
        "analytics.r3_t212_api_bond._broker_snapshot",
        return_value={
            "status": "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA",
            "environment": "LIVE_READ_ONLY",
            "credentials_configured": True,
            "last_successful_sync_utc": "2026-06-08T02:20:39+00:00",
            "positions_count": 0,
            "cash_eur": 674.66,
        },
    ):
        doc = build_r3_t212_api_bond(tmp_path, persist=True)
    assert doc.get("state") == "fail"
    assert doc.get("t212_trusted") is False
    assert doc.get("t212_orders_blocked") is True
    assert "API-Key" in str(doc.get("confirmation_de") or "")


def test_bond_persists_after_transient_error(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_t212_api_bond_policy.json").write_text(
        json.dumps({"bond_mode": "persistent"}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_t212_api_bond.json").write_text(
        json.dumps({"bonded": True, "bonded_at_utc": "2026-06-07T00:00:00+00:00"}),
        encoding="utf-8",
    )
    with patch(
        "analytics.r3_t212_api_bond._broker_snapshot",
        return_value={
            "status": "CONNECTION_FAILED_RETRY_AVAILABLE",
            "credentials_configured": True,
            "environment": "LIVE_READ_ONLY",
            "last_error": "timeout",
        },
    ):
        doc = build_r3_t212_api_bond(tmp_path, persist=True)
    assert doc.get("bonded") is True
    assert doc.get("t212_trusted") is False
    assert "nicht vertrauenswürdig" in str(doc.get("confirmation_de") or "").lower()


def test_render_confirmation_on_desktop(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/r3_t212_api_bond_policy.json").write_text("{}", encoding="utf-8")
    with patch("analytics.r3_t212_api_bond._broker_snapshot", return_value=_broker_ok()):
        html_out = render_r3_t212_bond_confirmation(tmp_path)
    assert 'id="r3-t212-bond"' in html_out
    assert "Trading212" in html_out


def test_desktop_includes_bond_line(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/r3_t212_api_bond_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps(
            {
                "ok": True,
                "signal_date": "2026-06-05",
                "top_picks": [{"ticker": "INTC", "target_weight": 0.1}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/king_hardware_latest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": True,
                "confirmation_de": "✓ Trading212 API verbunden",
                "state": "ok",
            }
        ),
        encoding="utf-8",
    )
    from analytics.preview_hub_page import render_desktop_shell_page

    html_out = render_desktop_shell_page(tmp_path).decode("utf-8")
    assert "r3-trading-functions" in html_out or "r3-freigabe-btn" in html_out
    assert "r3-t212-bond" not in html_out
    assert "T212" in html_out


def test_sync_calls_broker_service(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_t212_api_bond_policy.json").write_text("{}", encoding="utf-8")
    mock_status = MagicMock()
    mock_status.to_dict.return_value = _broker_ok()
    with patch(
        "integrations.trading212.t212_readonly_connection_service.sync_readonly_account",
        return_value=mock_status,
    ) as sync_mock, patch(
        "integrations.trading212.t212_sync_throttle.should_sync_now",
        return_value=(True, ""),
    ), patch("analytics.r3_t212_api_bond._broker_snapshot", return_value=_broker_ok()):
        doc = sync_r3_t212_api_bond(tmp_path, force=True, persist=True)
    sync_mock.assert_called_once()
    assert doc.get("bonded") is True
