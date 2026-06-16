"""Internet spread health/join checks — localhost fallback when remote DNS fails."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.community_spread_plan import collect_spread_urls
from analytics.spread_secure_ops import _spread_internet_checks


def test_spread_internet_checks_local_fallback(tmp_path: Path) -> None:
    stale = "https://dead-old-url.trycloudflare.com"
    live = "https://live-tunnel.trycloudflare.com"
    with patch(
        "analytics.remote_hub_access.load_tunnel_state",
        return_value={
            "running": True,
            "ok": True,
            "public_url": live,
            "stable": False,
            "mode": "cloudflared",
        },
    ), patch("analytics.spread_secure_ops._http_ok", side_effect=lambda url, **kw: "127.0.0.1" in url), patch(
        "analytics.spread_secure_ops._join_page_ok", return_value=False
    ), patch(
        "analytics.spread_secure_ops._local_join_ok", return_value=True
    ), patch(
        "analytics.remote_hub_access._verify_remote_health", return_value=False
    ), patch(
        "analytics.preview_federation.federation_config",
        return_value={"hub_port": 17890},
    ):
        checks = _spread_internet_checks(tmp_path, stale)
    assert checks["remote_base"] == live
    assert checks["health_ok"] is True
    assert checks["join_ok"] is True
    assert checks["health_local"] is True
    assert checks["join_local"] is True


def test_collect_spread_urls_prefers_live_tunnel(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        '{"public_base_url":"https://stale.trycloudflare.com","public_base_url_locked":true,"hub_port":17890}',
        encoding="utf-8",
    )
    live = "https://live-tunnel.trycloudflare.com"
    with patch(
        "analytics.remote_hub_access.load_tunnel_state",
        return_value={
            "running": True,
            "ok": True,
            "public_url": live,
            "stable": False,
            "mode": "cloudflared",
        },
    ), patch("analytics.remote_hub_access._sync_public_urls", return_value=["preview_federation:public_base_url"]), patch(
        "analytics.preview_federation.build_share_package",
        return_value={"share_url": ""},
    ), patch(
        "analytics.community_spread_plan._load_json",
        return_value={},
    ):
        urls = collect_spread_urls(tmp_path)
    assert urls["remote_url"] == live
    assert urls["join_remote"] == f"{live}/join"
