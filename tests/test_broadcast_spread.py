from __future__ import annotations

import json
from pathlib import Path

from analytics.community_spread_plan import broadcast_spread, collect_spread_urls


def test_collect_spread_urls_lan_and_remote(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "lan_bind": True,
                "public_base_url": "http://192.168.1.5:17890",
                "hub_port": 17890,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_https_mirror.json").write_text(
        json.dumps({"public_base_url": "https://example.trycloudflare.com"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.remote_hub_access.load_tunnel_state",
        lambda _r: {"ok": False},
    )
    urls = collect_spread_urls(tmp_path)
    assert urls["lan_url"] == "http://192.168.1.5:17890"
    assert urls["remote_url"] == "https://example.trycloudflare.com"


def test_broadcast_spread_writes_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_SPREAD_ANONYM", "0")
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "lan_bind": True,
                "public_base_url": "http://10.0.0.8:17890",
                "join_token": "tok",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_https_mirror.json").write_text(
        json.dumps({"public_base_url": "https://tunnel.example.com"}),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/LINUX_COMMUNITY_DE.md").write_text("x" * 300, encoding="utf-8")
    monkeypatch.setattr(
        "analytics.remote_hub_access.load_tunnel_state",
        lambda _r: {"ok": True, "public_url": "https://tunnel.example.com"},
    )
    monkeypatch.setattr(
        "analytics.preview_manifest.load_preview_manifest",
        lambda _r: {"one_liner_de": "Test one-liner"},
    )

    doc = broadcast_spread(tmp_path)
    assert (tmp_path / "evidence/spread_whatsapp_de.txt").is_file()
    assert (tmp_path / "evidence/spread_broadcast_de.txt").is_file()
    forum = (tmp_path / "evidence/community_spread_forum_de.txt").read_text(encoding="utf-8")
    assert "http://10.0.0.8:17890" in forum
    assert "https://tunnel.example.com" in forum
    assert doc.get("ok") is True
