from pathlib import Path

from analytics.community_spread_plan import (
    _write_forum_draft,
    ack_soft_launch,
    ensure_community_spread,
    evaluate_gate,
    load_spread_plan,
    run_spread_tick,
    scan_community_spread,
)


def test_spread_plan_loads(tmp_path: Path) -> None:
    plan_src = Path(__file__).resolve().parents[1] / "control/COMMUNITY_SPREAD_PLAN.json"
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/COMMUNITY_SPREAD_PLAN.json").write_text(plan_src.read_text(encoding="utf-8"))
    plan = load_spread_plan(tmp_path)
    assert len(plan.get("phases") or []) == 4


def test_manifest_gate(tmp_path: Path) -> None:
    g = evaluate_gate(tmp_path, "manifest_present")
    assert g["ok"] is False
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/PREVIEW_MANIFEST_DE.json").write_text('{"one_liner_de":"x"}', encoding="utf-8")
    g2 = evaluate_gate(tmp_path, "manifest_present")
    assert g2["ok"] is True


def test_federation_gate_needs_compute_worker(tmp_path: Path) -> None:
    from analytics.community_spread_plan import evaluate_gate

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        '{"enabled": true, "king_worker_id": "king"}',
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/preview_federation.json").write_text(
        '{"workers": {"king": {"worker_id": "king", "role": "king", "cpus": 8, "last_seen_utc": "2099-01-01T00:00:00+00:00"}}}',
        encoding="utf-8",
    )
    g = evaluate_gate(tmp_path, "federation_min_two_nodes")
    assert g["ok"] is False


def test_join_token_gate(tmp_path: Path) -> None:
    from analytics.community_spread_plan import evaluate_gate

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        '{"join_token": "abc123def456ghi789"}', encoding="utf-8"
    )
    assert evaluate_gate(tmp_path, "join_token_active")["ok"] is True


def test_soft_launch_ack(tmp_path: Path) -> None:
    plan_src = Path(__file__).resolve().parents[1] / "control/COMMUNITY_SPREAD_PLAN.json"
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/COMMUNITY_SPREAD_PLAN.json").write_text(plan_src.read_text(encoding="utf-8"))
    doc = ack_soft_launch(tmp_path)
    assert doc["ok"] is True
    g = evaluate_gate(tmp_path, "soft_launch_ack")
    assert g["ok"] is True


def test_public_launch_only_needs_h1_not_hub_stable(tmp_path: Path) -> None:
    plan_src = Path(__file__).resolve().parents[1] / "control/COMMUNITY_SPREAD_PLAN.json"
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/COMMUNITY_SPREAD_PLAN.json").write_text(plan_src.read_text(encoding="utf-8"))
    plan = load_spread_plan(tmp_path)
    public = next(p for p in plan["phases"] if p["id"] == "public")
    assert "h1_sealed" in public["gates"]
    assert "hub_stable" in public.get("optional_gates", [])
    assert "soft_launch_done" in public.get("optional_gates", [])


def test_forum_draft_synced_gate(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        '{"public_base_url": "https://example.trycloudflare.com", "public_base_url_locked": true, "lan_bind": false, "join_token": "abc123def456ghi789"}',
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/community_spread_forum_de.txt").write_text(
        "Hub (Remote): https://old.trycloudflare.com/\n",
        encoding="utf-8",
    )
    g = evaluate_gate(tmp_path, "forum_draft_synced")
    assert g["ok"] is False
    (tmp_path / "evidence/community_spread_forum_de.txt").write_text(
        "Hub (Remote): https://example.trycloudflare.com/\n",
        encoding="utf-8",
    )
    g2 = evaluate_gate(tmp_path, "forum_draft_synced")
    assert g2["ok"] is True


def test_ensure_community_spread_refreshes_forum(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        '{"public_base_url": "https://new-hub.trycloudflare.com", "public_base_url_locked": true, "join_token": "abc123def456ghi789"}',
        encoding="utf-8",
    )
    (tmp_path / "control/PREVIEW_MANIFEST_DE.json").write_text('{"one_liner_de":"test"}', encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/LINUX_COMMUNITY_DE.md").write_text("# test\n" * 50, encoding="utf-8")
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/community_spread_forum_de.txt").write_text(
        "Hub (Remote): https://old.trycloudflare.com/\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "analytics.community_spread_plan.ensure_federation_spread_security",
        lambda _r: {"ok": True, "changed": []},
    )
    monkeypatch.setattr(
        "analytics.community_spread_plan.sync_spread_timers",
        lambda _r: ["sustain-tick-1"],
    )
    monkeypatch.setattr(
        "tools.preview_hub.ensure_hub_running",
        lambda *_a, **_k: 17890,
    )
    monkeypatch.setattr(
        "analytics.worker_export_sync.ensure_lite_export",
        lambda *_a, **_k: {"ok": True, "detail_de": "ok"},
    )
    monkeypatch.setattr(
        "analytics.preview_federation.build_share_package",
        lambda _r: {
            "share_url": "https://new-hub.trycloudflare.com/",
            "join_url": "https://new-hub.trycloudflare.com/join",
            "health_check_de": "curl …",
            "export_command_de": "ai_kernel spread-remote",
            "join_command_lite_de": "Linux_START.sh",
        },
    )

    _write_forum_draft(tmp_path)
    doc = ensure_community_spread(tmp_path, repair=True, persist=True)
    text = (tmp_path / "evidence/community_spread_forum_de.txt").read_text(encoding="utf-8")
    assert "https://new-hub.trycloudflare.com" in text
    assert evaluate_gate(tmp_path, "forum_draft_synced")["ok"] is True
    assert (tmp_path / "evidence/community_spread_sustain_latest.json").is_file()
    assert doc.get("share_url")


def test_scan_community_spread(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/LINUX_COMMUNITY_DE.md").write_text("# test\n" * 50, encoding="utf-8")
    doc = scan_community_spread(tmp_path)
    assert "gates" in doc
    assert doc.get("gates_total", 0) >= 6


def test_tick_writes_evidence(tmp_path: Path) -> None:
    plan_src = Path(__file__).resolve().parents[1] / "control/COMMUNITY_SPREAD_PLAN.json"
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/COMMUNITY_SPREAD_PLAN.json").write_text(plan_src.read_text(encoding="utf-8"))
    (tmp_path / "control/PREVIEW_MANIFEST_DE.json").write_text('{"one_liner_de":"test"}', encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/LINUX_COMMUNITY_DE.md").write_text("# test\n" * 50, encoding="utf-8")
    rep = run_spread_tick(tmp_path, execute=False)
    assert (tmp_path / "evidence/community_spread_tick_latest.json").is_file()
    assert rep.get("phases")
