from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.community_spread_plan import broadcast_spread
from analytics.reddit_forum_post import open_reddit_submit
from analytics.spread_anonym_policy import (
    is_anonym_enforced,
    redact_spread_urls,
    reddit_profile_block,
)
from analytics.spread_completion import run_spread_completion


def test_anonym_enforced_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AA_SPREAD_ANONYM", raising=False)
    (tmp_path / "control").mkdir(parents=True)
    assert is_anonym_enforced(tmp_path) is True


def test_anonym_opt_out_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_SPREAD_ANONYM", "0")
    assert is_anonym_enforced(tmp_path) is False


def test_reddit_profile_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_SPREAD_ANONYM", "1")
    doc = open_reddit_submit(tmp_path)
    assert doc.get("blocked") is True
    assert doc.get("ok") is False


def test_broadcast_spread_routes_anonym(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_SPREAD_ANONYM", "1")
    (tmp_path / "control").mkdir(parents=True)
    urls = {
        "remote_url": "https://x.trycloudflare.com",
        "lan_url": "http://192.168.1.1:17890",
        "lite_zip": "/home/user/world.zip",
    }
    with patch("analytics.community_spread_plan.collect_spread_urls", return_value=urls), patch(
        "analytics.preview_federation.build_share_package", return_value={}
    ):
        doc = broadcast_spread(tmp_path, persist=False)
    assert doc.get("anonym") is True
    assert "192.168" not in json.dumps(doc.get("urls") or {})


def test_redact_spread_urls_https_only() -> None:
    out = redact_spread_urls(
        {
            "remote_url": "https://hub.example.com",
            "lan_url": "http://192.168.0.1:17890",
            "join_lan": "http://192.168.0.1:17890/join",
            "world_zip": "/home/king/world_worker_LITE.zip",
        }
    )
    assert out["join_remote"] == "https://hub.example.com/join"
    assert "lan_url" not in out
    assert out["world_zip"] == "world_worker_LITE.zip"


def test_spread_completion_anonym_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_SPREAD_ANONYM", "1")
    (tmp_path / "control").mkdir(parents=True)
    with patch(
        "analytics.spread_finish_anonym_loop.run_anonym_finish_tick",
        return_value={"done": False, "headline_de": "tick", "facts": {}, "steps": [], "remaining": []},
    ):
        doc = run_spread_completion(tmp_path)
    assert doc.get("anonym") is True


def test_reddit_profile_block_message() -> None:
    doc = reddit_profile_block(Path("."))
    assert "Inkognito" in doc.get("detail_de", "")
