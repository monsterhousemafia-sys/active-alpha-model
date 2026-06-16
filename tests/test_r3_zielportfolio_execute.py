"""R3 Zielportfolio-Ausführung — Preflight + One-Click (fail-closed)."""
from __future__ import annotations

import json
from pathlib import Path

from execution.confirmed_live.order_preflight_gate import run_preflight


def test_preflight_blocks_without_core_live_mode(tmp_path: Path) -> None:
    (tmp_path / "live_pilot/confirmed_execution").mkdir(parents=True, exist_ok=True)
    (tmp_path / "live_pilot/confirmed_execution/core_live_mode_state.json").write_text(
        json.dumps({"status": "LOCKED"}),
        encoding="utf-8",
    )
    pf = run_preflight(
        tmp_path,
        {"instrument": "INTC", "max_notional_eur": 50.0, "order_type": "MARKET_BUY"},
        readonly_cash=500.0,
        account_currency="EUR",
    )
    assert pf.get("passed") is False
    assert "CORE_LIVE_MODE_NOT_ACTIVE" in (pf.get("blockers") or [])


def test_one_click_start_requires_freigabe_chain(tmp_path: Path) -> None:
    from unittest.mock import patch

    from analytics.r3_one_click_start import run_one_click_start

    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    with patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True},
    ), patch(
        "analytics.r3_t212_api_bond.ensure_r3_t212_api_bond",
        return_value={"setup_ok": True, "t212_trusted": True, "credentials_configured": True, "steps": []},
    ), patch(
        "analytics.r3_prognosis_pipeline.run_prognosis_automation",
        return_value={"ok": True, "t212_trusted": True, "worthwhile_buys": 11},
    ), patch(
        "analytics.r3_freigabe.auto_prepare_freigabe_for_desktop",
        return_value={
            "package_ready": False,
            "headline_de": "Neues T212-Konto — bitte bestätigen",
            "account_confirmed": False,
        },
    ):
        doc = run_one_click_start(tmp_path, persist=False)
    assert doc.get("ok") is False
    assert doc.get("package_ready") is False
