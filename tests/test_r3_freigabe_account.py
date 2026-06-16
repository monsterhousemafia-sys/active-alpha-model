"""T212-Kontobestätigung + Freigabe fail-closed bei Account-Wechsel."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_freigabe import package_ready
from analytics.r3_t212_account_identity import assess_account_confirmation, confirm_t212_account


def _bond(fp: str = "abc123") -> dict:
    return {
        "bonded": True,
        "connected": True,
        "account_fingerprint": fp,
        "account_label": "T212 LIVE READ ONLY · 500 EUR",
        "connection_label": f"T212 LIVE · #{fp[:8]}",
        "environment": "LIVE_READ_ONLY",
        "credentials_configured": True,
    }


def _orders_active(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/r3_stock_orders_latest.json").write_text(
        json.dumps(
            {
                "initial_package": {"active": True},
                "stocks": [{"side": "BUY", "notional_eur": 100.0}],
            }
        ),
        encoding="utf-8",
    )


def test_package_blocked_until_account_confirmed(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(_bond("newacct01")),
        encoding="utf-8",
    )
    _orders_active(tmp_path)
    with patch(
        "integrations.trading212.t212_trust_gate.assess_t212_trust_from_root",
        return_value={"orders_allowed": True},
    ):
        status = package_ready(tmp_path)
    assert status.get("package_ready") is False
    assert "Neues T212-Konto" in str(status.get("headline_de") or "")


def test_package_ready_after_confirm(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    bond = _bond("confirmed1")
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(json.dumps(bond), encoding="utf-8")
    _orders_active(tmp_path)
    confirm = confirm_t212_account(tmp_path, bond=bond)
    assert confirm.get("ok") is True
    with patch(
        "integrations.trading212.t212_trust_gate.assess_t212_trust_from_root",
        return_value={"orders_allowed": True},
    ):
        status = package_ready(tmp_path)
    assert status.get("package_ready") is True


def test_account_mismatch_after_switch(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    old = _bond("oldaccount")
    confirm_t212_account(tmp_path, bond=old)
    new = _bond("newaccount")
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(json.dumps(new), encoding="utf-8")
    assess = assess_account_confirmation(tmp_path, bond=new)
    assert assess.get("needs_confirmation") is True
    assert "gewechselt" in str(assess.get("message_de") or "").lower()
