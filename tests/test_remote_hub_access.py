from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.remote_hub_access import (
    is_private_lan_host,
    is_remote_reachable_url,
    ensure_remote_hub_url,
    start_cloudflared_quick_tunnel,
)


def test_private_lan_hosts() -> None:
    assert is_private_lan_host("192.168.1.1") is True
    assert is_private_lan_host("10.0.0.5") is True
    assert is_private_lan_host("127.0.0.1") is True
    assert is_private_lan_host("100.64.0.1") is False


def test_remote_reachable_urls() -> None:
    assert is_remote_reachable_url("https://abc.trycloudflare.com") is True
    assert is_remote_reachable_url("http://100.64.0.2:17890") is True
    assert is_remote_reachable_url("http://192.168.1.1:17890") is False
    assert is_remote_reachable_url("http://127.0.0.1:17890") is False


def test_ensure_remote_tailscale(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"hub_port": 17890, "remote_workers_expected": True}),
        encoding="utf-8",
    )
    with patch("analytics.remote_hub_access.build_tailscale_hub_url", return_value="http://100.77.1.2:17890"), patch(
        "analytics.remote_hub_access.tailscale_online", return_value=True
    ):
        out = ensure_remote_hub_url(tmp_path, mode="auto")
    assert out["ok"] is True
    assert out["mode"] == "tailscale"
    cfg = json.loads((tmp_path / "control/preview_federation.json").read_text(encoding="utf-8"))
    assert cfg["public_base_url"] == "http://100.77.1.2:17890"


def test_ensure_remote_cloudflared(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"hub_port": 17890, "remote_workers_expected": True}),
        encoding="utf-8",
    )
    with patch("analytics.remote_hub_access.build_tailscale_hub_url", return_value=None), patch(
        "analytics.remote_hub_access.tailscale_online", return_value=False
    ), patch(
        "analytics.remote_hub_access.start_cloudflared_quick_tunnel",
        return_value={
            "ok": True,
            "mode": "cloudflared",
            "public_url": "https://test.trycloudflare.com",
            "pid": 12345,
        },
    ):
        out = ensure_remote_hub_url(tmp_path, mode="auto")
    assert out["ok"] is True
    assert out["public_base_url"] == "https://test.trycloudflare.com"


def test_export_fingerprint_stable(tmp_path: Path) -> None:
    from analytics.worker_export_sync import export_fingerprint, export_is_current

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "public_base_url": "https://x.trycloudflare.com",
                "join_token": "tok123",
                "join_token_locked": True,
                "public_base_url_locked": True,
            }
        ),
        encoding="utf-8",
    )
    a = export_fingerprint(tmp_path)
    b = export_fingerprint(tmp_path)
    assert a == b
    ok, _ = export_is_current(tmp_path)
    assert ok is False


def test_gate_remote_blocks_lan(tmp_path: Path) -> None:
    from analytics.community_spread_plan import evaluate_gate

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "public_base_url": "http://192.168.11.30:17890",
                "remote_workers_expected": True,
            }
        ),
        encoding="utf-8",
    )
    g = evaluate_gate(tmp_path, "public_base_url_set")
    assert g["ok"] is False
    assert "spread-remote" in (g.get("detail_de") or "")
