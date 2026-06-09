from __future__ import annotations

import json
from pathlib import Path

from analytics.spread_secure_ops import run_spread_efficient, verify_spread_security


def _base_control(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "join_token": "a" * 32,
                "lan_bind": True,
                "bind_host": "0.0.0.0",
                "hub_port": 17890,
                "remote_workers_expected": False,
            }
        ),
        encoding="utf-8",
    )
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


def test_verify_blocks_unsafe_flags(tmp_path: Path) -> None:
    _base_control(tmp_path)
    (tmp_path / "promotion_gate_config.yaml").write_text(
        "auto_execute_real_money_enabled: true\n",
        encoding="utf-8",
    )
    doc = verify_spread_security(tmp_path)
    assert doc.get("ok") is False
    assert any(c.get("id") == "safety_flags" and not c.get("ok") for c in doc.get("checks") or [])


def test_verify_blocks_auto_research(tmp_path: Path) -> None:
    _base_control(tmp_path)
    (tmp_path / "promotion_gate_config.yaml").write_text(
        "\n".join(
            [
                "auto_execute_real_money_enabled: false",
                "auto_promote_paper_enabled: false",
                "auto_promote_signal_enabled: false",
                "auto_research_enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    doc = verify_spread_security(tmp_path)
    assert doc.get("ok") is False
    assert any(c.get("id") == "safety_flags" and not c.get("ok") for c in doc.get("checks") or [])


def test_run_haus_mode(monkeypatch, tmp_path: Path) -> None:
    _base_control(tmp_path)
    monkeypatch.setattr(
        "analytics.spread_secure_ops._http_ok",
        lambda url, timeout=4.0: True,
    )
    monkeypatch.setattr(
        "analytics.preview_federation.apply_lan_spread",
        lambda *_a, **_k: {"ok": True},
    )
    doc = run_spread_efficient(tmp_path, "haus")
    assert doc.get("mode") == "haus"
    assert "haus" in doc


def test_verify_mode(tmp_path: Path) -> None:
    _base_control(tmp_path)
    doc = run_spread_efficient(tmp_path, "verify")
    assert doc.get("mode") is None or "checks" in doc


def test_adoption_zero_without_compute(tmp_path: Path) -> None:
    _base_control(tmp_path)
    (tmp_path / "control/COMMUNITY_SPREAD_PLAN.json").write_text(
        '{"phases":[{"id":"prep","status":"done"}]}', encoding="utf-8"
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/world_worker_LITE.zip").write_bytes(b"zip")
    from analytics.spread_secure_ops import build_spread_progress

    doc = build_spread_progress(tmp_path)
    assert doc["bars"]["adoption"]["pct"] == 0
    assert doc["adoption_gate"]["done"] is False
    assert "PC" in doc["adoption_gate"]["next_real_jump_de"]


def test_build_spread_progress(tmp_path: Path) -> None:
    _base_control(tmp_path)
    (tmp_path / "control/COMMUNITY_SPREAD_PLAN.json").write_text(
        '{"phases":[{"id":"prep","status":"done"},{"id":"sustain","status":"done"}]}',
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/spread_whatsapp_de.txt").write_text("x", encoding="utf-8")
    doc = __import__("analytics.spread_secure_ops", fromlist=["build_spread_progress"]).build_spread_progress(
        tmp_path
    )
    assert "bars" in doc
    assert "vorbereitung" in doc["bars"]


def test_hub_health_ok_without_lan_ip(tmp_path: Path, monkeypatch) -> None:
    _base_control(tmp_path)
    monkeypatch.setattr("analytics.preview_federation.detect_lan_ip", lambda: "")
    monkeypatch.setattr("analytics.spread_secure_ops._http_ok", lambda url, timeout=4.0: "127.0.0.1" in url)
    from analytics.spread_secure_ops import _check_hub_health

    doc = _check_hub_health(tmp_path)
    assert doc.get("ok") is True
    assert doc.get("id") == "hub_health"
