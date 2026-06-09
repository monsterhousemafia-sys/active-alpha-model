from __future__ import annotations

import json
from pathlib import Path

def _shield_base(tmp_path: Path) -> None:
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
    (tmp_path / "control/spread_shield.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")


from analytics.whatsapp_spread import (
    build_wa_me_url,
    complete_self_send,
    load_whatsapp_config,
    normalize_phone_e164,
    phone_to_chat_id,
    send_spread_message,
    send_to_self,
    verify_join_reachable,
    verify_whatsapp_binding,
)


def test_normalize_phone_de_mobile() -> None:
    assert normalize_phone_e164("+49 172 3949830") == "491723949830"
    assert normalize_phone_e164("01723949830") == "491723949830"
    assert phone_to_chat_id("+49 172 3949830") == "491723949830@c.us"


def test_build_wa_me_url() -> None:
    url = build_wa_me_url("491723949830", "Hallo")
    assert url.startswith("https://wa.me/491723949830?")
    assert "text=Hallo" in url


def test_verify_fail_closed_without_enable(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/whatsapp_spread.json").write_text(
        json.dumps({"enabled": False, "provider": "wa_me"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/spread_whatsapp_de.txt").write_text("Spread-Text", encoding="utf-8")
    doc = verify_whatsapp_binding(tmp_path)
    assert doc.get("ok") is False
    assert doc.get("provider") == "wa_me"


def test_dry_run_send(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    _shield_base(tmp_path)
    monkeypatch.setattr("analytics.spread_shield._agent_dry_run_env", lambda: True)
    (tmp_path / "control/whatsapp_spread.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "provider": "wa_me",
                "send_mode": "self",
                "self_phone_e164": "4915756402383",
                "attach_zip": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/spread_whatsapp_de.txt").write_text(
        "https://example.com/join\n\nWorker ZIP",
        encoding="utf-8",
    )
    doc = send_spread_message(tmp_path, "4915756402383", dry_run=True)
    assert doc.get("ok") is True
    assert doc.get("dry_run") is True
    assert doc.get("phone_e164") == "4915756402383"


def test_load_config(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/whatsapp_spread.json").write_text('{"provider":"waha"}', encoding="utf-8")
    cfg = load_whatsapp_config(tmp_path)
    assert cfg.get("provider") == "waha"


def test_verify_join_reachable(monkeypatch) -> None:
    monkeypatch.setattr("analytics.whatsapp_spread._http_ok", lambda *_a, **_k: True)
    monkeypatch.setattr("analytics.whatsapp_spread._join_page_ok", lambda *_a, **_k: True)
    doc = verify_join_reachable("https://example.com/join")
    assert doc.get("ok") is True
    assert doc.get("join_url") == "https://example.com/join"


def test_complete_self_send_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("analytics.whatsapp_spread._http_ok", lambda *_a, **_k: True)
    monkeypatch.setattr("analytics.whatsapp_spread._join_page_ok", lambda *_a, **_k: True)
    monkeypatch.setattr("analytics.spread_shield._agent_dry_run_env", lambda: True)
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    _shield_base(tmp_path)
    (tmp_path / "control/whatsapp_spread.json").write_text(
        json.dumps({"send_mode": "self", "self_phone_e164": "4915756402383", "attach_zip": False}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/spread_whatsapp_de.txt").write_text(
        "https://sport-supplied-rivers-macintosh.trycloudflare.com/join\n\nZIP im Anhang.",
        encoding="utf-8",
    )
    doc = complete_self_send(tmp_path, dry_run=True)
    assert doc.get("ok") is True
    assert doc.get("dry_run") is True


def test_send_to_self_dry_run(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    _shield_base(tmp_path)
    monkeypatch.setattr("analytics.spread_shield._agent_dry_run_env", lambda: True)
    (tmp_path / "control/whatsapp_spread.json").write_text(
        json.dumps(
            {
                "send_mode": "self",
                "self_phone_e164": "4915756402383",
                "provider": "wa_me",
                "attach_zip": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/spread_whatsapp_de.txt").write_text("Join-Link", encoding="utf-8")
    doc = send_to_self(tmp_path, dry_run=True)
    assert doc.get("ok") is True
    assert doc.get("send_mode") == "self"
    assert doc.get("phone_e164") == "4915756402383"
