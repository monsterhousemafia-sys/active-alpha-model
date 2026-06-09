from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from analytics.community_spread_plan import (
    _write_forum_draft_anonym,
    broadcast_spread_anonym,
)
from analytics.spread_finish_anonym_loop import run_anonym_finish_tick


def _urls(remote: str = "https://test.trycloudflare.com") -> dict:
    return {
        "remote_url": remote,
        "lan_url": "http://192.168.11.30:17890",
        "join_remote": f"{remote}/join",
        "lite_zip": "/tmp/world.zip",
    }


def test_write_forum_draft_anonym_no_lan(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    with patch("analytics.community_spread_plan.collect_spread_urls", return_value=_urls()):
        path = _write_forum_draft_anonym(tmp_path)
    text = path.read_text(encoding="utf-8")
    reddit = (tmp_path / "evidence/reddit_post_body_ready.txt").read_text(encoding="utf-8")
    assert "192.168" not in text
    assert "LAN (same house" not in text
    assert "Join over the Internet" in text
    assert "https://test.trycloudflare.com/join" in text
    assert "https://test.trycloudflare.com/join" in reddit
    assert "or LAN" not in reddit


def test_broadcast_spread_anonym_https_only_wa(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    with patch("analytics.community_spread_plan.collect_spread_urls", return_value=_urls()), patch(
        "analytics.preview_federation.build_share_package", return_value={}
    ):
        doc = broadcast_spread_anonym(tmp_path, persist=False)
    wa = (tmp_path / "evidence/spread_whatsapp_de.txt").read_text(encoding="utf-8")
    assert doc.get("ok") is True
    assert wa.startswith("https://test.trycloudflare.com/join")
    assert "192.168" not in wa.splitlines()[0]


def test_anonym_finish_tick_writes_evidence(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    with patch("analytics.spread_autonomous.resume_autonomous_spread", return_value={"ok": True}), patch(
        "analytics.community_spread_plan.collect_spread_urls", return_value=_urls()
    ), patch("analytics.preview_federation.build_share_package", return_value={}), patch(
        "analytics.remote_hub_access.remote_access_status",
        return_value={"tunnel_pid_alive": True, "remote_ready": True, "tunnel_stable": False},
    ), patch(
        "analytics.spread_secure_ops.verify_spread_security",
        return_value={"ok": True, "checks_passed": 6, "checks_total": 6},
    ), patch(
        "analytics.tunnel_token_setup.apply_from_server_env",
        return_value={"ok": False, "message_de": "no token"},
    ), patch(
        "analytics.spread_autonomous._try_whatsapp_autonomous",
        return_value={"ok": True, "skipped": False},
    ), patch(
        "analytics.spread_finish_anonym_loop._federation_hostnames",
        return_value={
            "ok": True,
            "hostnames": ["king-pc"],
            "remote_compute_workers": 0,
            "workers_online": 2,
        },
    ), patch(
        "analytics.spread_secure_ops.build_spread_facts",
        return_value={
            "forum_posted": False,
            "tunnel_stable": False,
            "remote_compute_workers": 0,
            "verify_ok": True,
        },
    ):
        doc = run_anonym_finish_tick(tmp_path, iteration=1, execute_whatsapp=False)
    assert doc.get("anonym") is True
    assert doc.get("done") is False
    assert any(r.get("id") == "B_reddit_anonym" for r in doc.get("remaining") or [])
    evidence = tmp_path / "evidence/spread_finish_anonym_loop_latest.json"
    assert evidence.is_file()


def test_forum_ack_when_url_set(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    monkeypatch.setenv("AA_FORUM_POST_URL", "https://reddit.com/r/selfhosted/comments/abc/title/")
    with patch("analytics.spread_autonomous.resume_autonomous_spread", return_value={"ok": True}), patch(
        "analytics.community_spread_plan.collect_spread_urls", return_value=_urls()
    ), patch("analytics.preview_federation.build_share_package", return_value={}), patch(
        "analytics.remote_hub_access.remote_access_status",
        return_value={"tunnel_pid_alive": True, "remote_ready": True},
    ), patch(
        "analytics.spread_secure_ops.verify_spread_security",
        return_value={"ok": True, "checks_passed": 6, "checks_total": 6},
    ), patch(
        "analytics.tunnel_token_setup.apply_from_server_env",
        return_value={"ok": False},
    ), patch(
        "analytics.reddit_forum_post.complete_reddit_post",
        return_value={"ok": True, "post_url": "https://reddit.com/r/selfhosted/comments/abc/title/"},
    ), patch(
        "analytics.spread_finish_anonym_loop._federation_hostnames",
        return_value={"ok": True, "remote_compute_workers": 0, "hostnames": ["king"]},
    ), patch(
        "analytics.spread_secure_ops.build_spread_facts",
        return_value={"forum_posted": True, "tunnel_stable": False, "remote_compute_workers": 0},
    ):
        doc = run_anonym_finish_tick(tmp_path, execute_whatsapp=False)
    assert doc.get("forum_ack", {}).get("ok") is True
