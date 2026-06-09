from __future__ import annotations

import json
from pathlib import Path

from analytics.alpha_model_local_runtime import enable_world_runtime, is_local_only
from analytics.preview_federation import hub_bind_host, hub_public_base_url, prepare_worker_bundle_config
from analytics.world_spread import activate_house_to_world


def test_enable_world_runtime_uses_public_url(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "public_base_url": "https://test-world.trycloudflare.com",
                "public_base_url_locked": True,
                "remote_workers_expected": False,
                "join_token": "tok",
            }
        ),
        encoding="utf-8",
    )
    out = enable_world_runtime(tmp_path)
    assert out.get("ok") is True
    assert is_local_only(tmp_path) is False
    assert hub_public_base_url(tmp_path) == "https://test-world.trycloudflare.com"
    cfg = prepare_worker_bundle_config(tmp_path)
    assert cfg["hub_join_url"] == "https://test-world.trycloudflare.com"


def test_activate_house_to_world_keeps_lan_and_tunnel(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "lan_bind": True,
                "bind_host": "0.0.0.0",
                "public_base_url": "https://tunnel.example.com",
                "public_base_url_locked": True,
                "join_token": "tok",
                "hub_port": 17890,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/LINUX_COMMUNITY_DE.md").write_text("x" * 300, encoding="utf-8")

    monkeypatch.setattr("analytics.preview_federation.detect_lan_ip", lambda: "192.168.9.1")
    monkeypatch.setattr("tools.preview_hub.ensure_hub_running", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(
        "analytics.remote_hub_access.ensure_remote_hub_url",
        lambda _r, mode="auto": {
            "ok": True,
            "public_base_url": "https://tunnel.example.com",
            "stable": False,
            "mode": "cloudflared",
            "changed": [],
        },
    )
    monkeypatch.setattr(
        "analytics.worker_export_sync.ensure_lite_export",
        lambda _r, force=False: {
            "ok": True,
            "lite_zip": str(tmp_path / "world.zip"),
        },
    )
    (tmp_path / "world.zip").write_bytes(b"zip")
    monkeypatch.setattr(
        "analytics.community_spread_plan.broadcast_spread",
        lambda _r, persist=True: {"ok": True},
    )
    monkeypatch.setattr(
        "analytics.remote_hub_access.remote_access_status",
        lambda _r: {"remote_ready": True},
    )
    monkeypatch.setattr(
        "analytics.preview_manifest.load_preview_manifest",
        lambda _r: {"one_liner_de": "Test"},
    )

    doc = activate_house_to_world(tmp_path, force_export=False)
    assert doc.get("ok") is True
    assert doc.get("lan_url") == "http://192.168.9.1:17890"
    assert doc.get("join_url") == "https://tunnel.example.com/join"
    fed = json.loads((tmp_path / "control/preview_federation.json").read_text(encoding="utf-8"))
    assert fed.get("lan_bind") is True
    assert fed.get("remote_workers_expected") is True
    assert hub_bind_host(tmp_path) == "0.0.0.0"
    assert is_local_only(tmp_path) is False
