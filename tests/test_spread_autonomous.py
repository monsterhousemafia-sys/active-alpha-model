from __future__ import annotations

import json
from pathlib import Path

from analytics.spread_autonomous import (
    is_autonomous_spread_enabled,
    is_autonomous_spread_paused,
    operator_stock_veto_active,
    pause_autonomous_spread,
    release_autonomous_spread,
    resume_autonomous_spread,
    run_autonomous_preflight,
    run_autonomous_spread_tick,
    verify_autonomous_spread,
)
from analytics.spread_shield import evaluate_spread_shield


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
                "auto_send_mode": "manual",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/spread_shield.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "self_only": True,
                "require_spread_security_for_autonomous": False,
            }
        ),
        encoding="utf-8",
    )


def test_release_enables_autonomous(tmp_path: Path) -> None:
    _base(tmp_path)
    doc = release_autonomous_spread(tmp_path, released_by_de="Test")
    assert doc.get("autonomous_spread_enabled") is True
    assert doc.get("preflight_required") is True
    assert is_autonomous_spread_enabled(tmp_path)
    assert operator_stock_veto_active(tmp_path)


def test_shield_allows_autonomous_auto_send(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    release_autonomous_spread(tmp_path)
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "")
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "")
    monkeypatch.setenv("AA_SPREAD_HUMAN_CONFIRM", "")
    monkeypatch.setattr(
        "analytics.spread_shield._canonical_join_urls",
        lambda _r: ["https://example.com/join"],
    )
    monkeypatch.setattr(
        "analytics.spread_secure_ops.verify_spread_security",
        lambda _r: {"ok": True, "headline_de": "OK"},
    )
    doc = evaluate_spread_shield(
        tmp_path,
        action="auto_send",
        phone="4915756402383",
        text="https://example.com/join",
        dry_run=False,
    )
    assert doc.get("ok") is True
    assert any(
        c.get("id") == "human_confirm" and "Aktien" in str(c.get("detail_de"))
        for c in doc.get("checks") or []
    )


def test_autonomous_tick_skipped_when_disabled(tmp_path: Path) -> None:
    _base(tmp_path)
    doc = run_autonomous_spread_tick(tmp_path)
    assert doc.get("skipped") is True


def test_pause_and_resume(tmp_path: Path) -> None:
    _base(tmp_path)
    release_autonomous_spread(tmp_path)
    pause_autonomous_spread(tmp_path)
    assert is_autonomous_spread_paused(tmp_path)
    resume_autonomous_spread(tmp_path)
    assert not is_autonomous_spread_paused(tmp_path)


def test_preflight_fails_on_unsafe_flags(tmp_path: Path) -> None:
    _base(tmp_path)
    release_autonomous_spread(tmp_path)
    (tmp_path / "promotion_gate_config.yaml").write_text(
        "auto_execute_real_money_enabled: true\n",
        encoding="utf-8",
    )
    doc = run_autonomous_preflight(tmp_path)
    assert doc.get("ok") is False


def test_audit_written(tmp_path: Path) -> None:
    _base(tmp_path)
    release_autonomous_spread(tmp_path)
    verify_autonomous_spread(tmp_path)
    audit = tmp_path / "evidence/spread_autonomous_audit.jsonl"
    assert audit.is_file()
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2


def test_verify_autonomous_shield_auto_send_not_dry_run(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    release_autonomous_spread(tmp_path)
    calls: list[bool] = []

    def _fake_shield(root, *, action, phone="", text="", zip_path=None, dry_run=False):
        if action == "auto_send":
            calls.append(dry_run)
            return {"ok": True, "checks": [{"id": "spread_security", "ok": True}]}
        return {"ok": True, "checks": []}

    monkeypatch.setattr("analytics.spread_shield.evaluate_spread_shield", _fake_shield)
    monkeypatch.setattr(
        "analytics.spread_secure_ops.verify_spread_security",
        lambda _r: {"ok": True, "headline_de": "OK"},
    )
    monkeypatch.setattr(
        "analytics.secret_leak_scan.scan_for_leaks",
        lambda _r: {"ok": True, "headline_de": "OK"},
    )
    monkeypatch.setattr(
        "analytics.community_spread_plan.collect_spread_urls",
        lambda _r: {},
    )
    (tmp_path / "evidence/spread_whatsapp_de.txt").write_text(
        "https://example.com/join\n", encoding="utf-8"
    )
    doc = verify_autonomous_spread(tmp_path)
    assert calls == [False]
    sim = doc.get("shield_auto_send_sim") or {}
    assert sim.get("simulation") is True
    assert "Send" in str(sim.get("note_de") or "")


def test_preflight_join_lan_before_remote(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    release_autonomous_spread(tmp_path)
    tried: list[str] = []

    def _fake_verify(url: str, timeout: float = 12.0):
        tried.append(url)
        if "192.168" in url:
            return {"ok": True, "detail_de": "lan OK"}
        return {"ok": False, "detail_de": "remote FAIL"}

    monkeypatch.setattr("analytics.whatsapp_spread.verify_join_reachable", _fake_verify)
    monkeypatch.setattr(
        "analytics.spread_secure_ops.verify_spread_security",
        lambda _r: {"ok": True, "headline_de": "OK"},
    )
    monkeypatch.setattr(
        "analytics.secret_leak_scan.scan_for_leaks",
        lambda _r: {"ok": True, "headline_de": "OK"},
    )
    monkeypatch.setattr(
        "analytics.community_spread_plan.collect_spread_urls",
        lambda _r: {
            "join_lan": "http://192.168.1.10:17890/join",
            "join_remote": "https://tunnel.example/join",
        },
    )
    doc = run_autonomous_preflight(tmp_path)
    join = next(c for c in doc.get("checks") or [] if c.get("id") == "join_reachable")
    assert join.get("ok") is True
    assert tried[0] == "http://192.168.1.10:17890/join"
    assert len(tried) == 2


def test_preflight_join_skips_without_urls(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    release_autonomous_spread(tmp_path)
    monkeypatch.setattr(
        "analytics.spread_secure_ops.verify_spread_security",
        lambda _r: {"ok": True, "headline_de": "OK"},
    )
    monkeypatch.setattr(
        "analytics.secret_leak_scan.scan_for_leaks",
        lambda _r: {"ok": True, "headline_de": "OK"},
    )
    monkeypatch.setattr(
        "analytics.community_spread_plan.collect_spread_urls",
        lambda _r: {},
    )
    doc = run_autonomous_preflight(tmp_path)
    join = next(c for c in doc.get("checks") or [] if c.get("id") == "join_reachable")
    assert join.get("ok") is True
    assert "skip" in str(join.get("detail_de") or "").lower()


def test_append_audit_uses_flock(tmp_path: Path, monkeypatch) -> None:
    _base(tmp_path)
    import fcntl as fcntl_mod

    flock_calls: list[int] = []
    real_flock = fcntl_mod.flock

    def _track_flock(fd, op):
        flock_calls.append(op)
        return real_flock(fd, op)

    monkeypatch.setattr("analytics.spread_autonomous.fcntl.flock", _track_flock)
    release_autonomous_spread(tmp_path)
    assert fcntl_mod.LOCK_EX in flock_calls
    assert fcntl_mod.LOCK_UN in flock_calls
