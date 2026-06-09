"""Lokale App-URLs — kein Tunnel-HTTPS in der Anzeige."""
from __future__ import annotations

from pathlib import Path

from analytics.local_app_urls import app_start_display_de, local_hub_url, normalize_start_cmd_de
from analytics.launch_progress_board import build_launch_status


def test_local_hub_url() -> None:
    assert local_hub_url("/desktop") == "http://127.0.0.1:17890/desktop"
    assert local_hub_url("launch") == "http://127.0.0.1:17890/launch"


def test_normalize_strips_tunnel() -> None:
    cmd = "Öffne https://foo.trycloudflare.com/join"
    out = normalize_start_cmd_de(cmd)
    assert "trycloudflare" not in out
    assert out.startswith("http://127.0.0.1")


def test_app_start_display_welt() -> None:
    root = Path(__file__).resolve().parents[1]
    disp = app_start_display_de(
        root,
        {"id": "welt", "tier": "link", "hub_path": "/launch"},
    )
    assert disp == "http://127.0.0.1:17890/launch"
    assert "https://" not in disp


def test_launch_join_local_when_king_surface(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.r3_local_surface.is_king_cockpit_local",
        lambda r: True,
    )
    monkeypatch.setattr(
        "analytics.launch_progress_board._hub_healthy",
        lambda r: True,
    )
    monkeypatch.setattr(
        "analytics.h1_governance_status.sync_h1_governance_status",
        lambda r, **k: {"status": "COMPLETE", "progress_pct": 100, "sealed": False},
    )
    monkeypatch.setattr(
        "analytics.community_spread_plan._gate_gui_preview_fresh",
        lambda r: (True, "ok"),
    )
    doc = build_launch_status(tmp_path, persist=False)
    assert doc.get("join_url") == "http://127.0.0.1:17890/join"
    assert str((doc.get("remote") or {}).get("public_base_url") or "").startswith("http://127.0.0.1")
