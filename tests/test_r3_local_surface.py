from __future__ import annotations

from pathlib import Path

from analytics.r3_local_surface import (
    collect_ki_next_steps,
    filter_launch_tiles_for_king,
    hide_tunnel_url,
)


def test_hide_tunnel_url() -> None:
    assert hide_tunnel_url("https://foo.trycloudflare.com/join") == "Lokal · :17890"
    assert hide_tunnel_url("http://127.0.0.1:17890/") == "Lokal · :17890"


def test_filter_launch_tiles_for_king(monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.r3_local_surface.is_king_cockpit_local",
        lambda _root: True,
    )
    tiles = [
        {"id": "hub", "detail_de": "R3"},
        {"id": "remote", "ok": True, "detail_de": "https://x.trycloudflare.com"},
        {"id": "tunnel", "ok": True},
        {"id": "h1", "ok": False},
    ]
    out = filter_launch_tiles_for_king(tiles, Path("."))
    ids = [t["id"] for t in out]
    assert "tunnel" not in ids
    assert ids.count("remote") == 1
    assert "trycloudflare" not in str(out)


def test_collect_ki_next_steps() -> None:
    doc = collect_ki_next_steps(
        Path(__file__).resolve().parents[1],
        report={
            "chat_evolution": {"next_step_de": "learn", "chat_reply_de": "OK"},
            "system_status": {
                "cognitive": {"successor_active": True, "headline_de": "Kern aktiv", "active_interface": "ollama_local"},
                "operator": {"chat_next_de": "refresh"},
                "blockers_de": [],
            },
        },
    )
    assert doc.get("next_step_de") == "learn"
    assert doc.get("kernel_active") is True
    assert len(doc.get("next_steps_de") or []) >= 1
