"""Gemini Cloud-Bridge — Key, Routing, Parallel-Compute."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.gemini_advisor_bridge import (
    bridge_status,
    fetch_gemini_tip,
    resolve_gemini_tier,
    validate_gemini_key,
)
from analytics.r3_external_advisor import fetch_cloud_tip, resolve_primary_cloud_provider


def test_validate_gemini_key() -> None:
    assert validate_gemini_key("AIzaSyDUMMY_KEY_1234567890") is None
    assert validate_gemini_key("short") is not None


def test_resolve_gemini_tier_trading(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/r3_external_advisors.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "gemini": {
                    "enabled": True,
                    "model": "gemini-2.0-flash",
                    "tiers": {
                        "trading": {
                            "model": "gemini-2.0-flash",
                            "role_de": "Trading",
                            "max_tokens": 1000,
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    tier = resolve_gemini_tier(tmp_path, "Wie rebalance ich das Portfolio?", mode="tipp")
    assert tier.get("task") == "trading"


def test_fetch_gemini_mock(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/secrets").mkdir()
    (tmp_path / "control/secrets/gemini_api_key").write_text("AIzaSyTEST_KEY_1234567890123\n", encoding="utf-8")
    (tmp_path / "control/r3_external_advisors.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "primary_cloud_provider": "gemini",
                "gemini": {
                    "enabled": True,
                    "model": "gemini-2.0-flash",
                    "compute_boost": {"enabled": False},
                    "tiers": {"fast": {"model": "gemini-2.0-flash", "max_tokens": 500}},
                },
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "analytics.gemini_advisor_bridge._gemini_chat",
        return_value=("Tipp: pytest ausführen", {"model": "gemini-2.0-flash"}),
    ):
        out = fetch_gemini_tip(tmp_path, "Wie testen?")
    assert out.get("ok")
    assert out.get("provider") == "gemini"
    assert "pytest" in out.get("tip_de", "")


def test_cloud_routing_prefers_gemini(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/secrets").mkdir()
    (tmp_path / "control/secrets/gemini_api_key").write_text("AIzaSyTEST_KEY_1234567890123\n", encoding="utf-8")
    (tmp_path / "control/r3_external_advisors.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "primary_cloud_provider": "gemini",
                "gemini": {"enabled": True, "model": "gemini-2.0-flash", "compute_boost": {"enabled": False}},
                "openai": {"enabled": True, "keyless_mode": True},
            }
        ),
        encoding="utf-8",
    )
    assert resolve_primary_cloud_provider(tmp_path) == "gemini"
    with patch(
        "analytics.gemini_advisor_bridge.fetch_gemini_tip",
        return_value={"ok": True, "tip_de": "ok", "provider": "gemini"},
    ):
        out = fetch_cloud_tip(tmp_path, "Frage?")
    assert out.get("provider") == "gemini"


def test_bridge_status_no_key(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/r3_external_advisors.json").write_text("{}", encoding="utf-8")
    with patch("analytics.gemini_advisor_bridge.resolve_gemini_key", return_value=("", "")):
        st = bridge_status(tmp_path)
    assert st.get("configured") is False
