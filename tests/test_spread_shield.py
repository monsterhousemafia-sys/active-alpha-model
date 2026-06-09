from __future__ import annotations

import json
import time
from pathlib import Path

from analytics.spread_shield import evaluate_spread_shield, load_shield_config, shield_block_response, touch_rate_limit


def _base(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "promotion_gate_config.yaml").write_text(
        "\n".join(
            [
                "auto_execute_real_money_enabled: false",
                "auto_promote_paper_enabled: false",
                "auto_promote_signal_enabled: false",
                "auto_research_enabled: false",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/AI_KERNEL.json").write_text(
        json.dumps({"governance": {"auto_execute_real_money": False}}),
        encoding="utf-8",
    )
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"join_token": "a" * 32, "lan_bind": True, "hub_port": 17890}),
        encoding="utf-8",
    )
    (tmp_path / "control/whatsapp_spread.json").write_text(
        json.dumps(
            {
                "provider": "wa_me",
                "send_mode": "self",
                "self_phone_e164": "4915756402383",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/spread_shield.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "self_only": True,
                "autonomous_rate_limit_seconds": 21600,
                "require_url_sync_for_send": True,
                "require_spread_security_for_autonomous": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/spread_autonomous.json").write_text(
        json.dumps({"autonomous_spread_enabled": True, "operator_stock_veto": True, "paused": False}),
        encoding="utf-8",
    )


def test_shield_blocks_foreign_phone(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    monkeypatch.setattr("analytics.spread_shield._agent_dry_run_env", lambda: True)
    doc = evaluate_spread_shield(
        tmp_path,
        action="prepare_send",
        phone="4917999999999",
        text="https://example.com/join",
        dry_run=True,
    )
    assert doc.get("ok") is False
    assert any(c.get("id") == "phone" and not c.get("ok") for c in doc.get("checks") or [])


def test_shield_blocks_bot_provider(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    (tmp_path / "control/whatsapp_spread.json").write_text(
        json.dumps({"provider": "callmebot", "self_phone_e164": "4915756402383"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("analytics.spread_shield._agent_dry_run_env", lambda: True)
    doc = evaluate_spread_shield(tmp_path, action="api_send", dry_run=True)
    assert doc.get("ok") is False
    assert any(c.get("id") == "provider" and not c.get("ok") for c in doc.get("checks") or [])


def test_shield_blocks_api_without_confirm(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    (tmp_path / "control/spread_autonomous.json").write_text(
        json.dumps({"autonomous_spread_enabled": False}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "")
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "")
    monkeypatch.setenv("AA_SPREAD_HUMAN_CONFIRM", "")
    doc = evaluate_spread_shield(tmp_path, action="waha_send", dry_run=False)
    blocked = [c for c in doc.get("checks") or [] if not c.get("ok")]
    assert any(c.get("id") in {"agent_env", "human_confirm"} for c in blocked)


def test_shield_ok_self_prepare(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    monkeypatch.setattr("analytics.spread_shield._agent_dry_run_env", lambda: True)
    doc = evaluate_spread_shield(
        tmp_path,
        action="prepare_send",
        phone="4915756402383",
        text="https://example.com/join\n\nZIP im Anhang.",
        dry_run=True,
    )
    assert doc.get("ok") is True


def test_shield_blocks_url_mismatch(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    monkeypatch.setattr(
        "analytics.spread_shield._canonical_join_urls",
        lambda _r: ["https://canonical.example/join"],
    )
    doc = evaluate_spread_shield(
        tmp_path,
        action="auto_send",
        phone="4915756402383",
        text="https://evil.example/join",
        dry_run=False,
    )
    assert doc.get("ok") is False
    assert any(c.get("id") == "url_sync" and not c.get("ok") for c in doc.get("checks") or [])


def test_shield_blocks_when_paused(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    (tmp_path / "control/spread_autonomous.json").write_text(
        json.dumps({"autonomous_spread_enabled": True, "paused": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.spread_shield._canonical_join_urls",
        lambda _r: ["https://example.com/join"],
    )
    doc = evaluate_spread_shield(
        tmp_path,
        action="auto_send",
        phone="4915756402383",
        text="https://example.com/join",
        dry_run=False,
    )
    assert doc.get("ok") is False
    assert any(c.get("id") == "autonomous_pause" and not c.get("ok") for c in doc.get("checks") or [])


def test_autonomous_rate_limit(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    (tmp_path / "control/spread_shield.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "self_only": True,
                "autonomous_rate_limit_seconds": 3600,
                "require_spread_security_for_autonomous": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.spread_shield._canonical_join_urls",
        lambda _r: ["https://example.com/join"],
    )
    touch_rate_limit(tmp_path, autonomous=True)
    doc = evaluate_spread_shield(
        tmp_path,
        action="auto_send",
        phone="4915756402383",
        text="https://example.com/join",
        dry_run=False,
    )
    assert doc.get("ok") is False
    assert any(c.get("id") == "autonomous_rate" and not c.get("ok") for c in doc.get("checks") or [])


def test_load_shield_config_defaults(tmp_path: Path) -> None:
    cfg = load_shield_config(tmp_path)
    assert cfg.get("self_only") is True
    assert int(cfg.get("autonomous_rate_limit_seconds") or 0) >= 21600


def test_shield_block_response_shape() -> None:
    doc = shield_block_response({"headline_de": "BLOCK", "checks": [{"id": "x", "ok": False}]})
    assert doc.get("shield_blocked") is True
    assert doc.get("ok") is False
