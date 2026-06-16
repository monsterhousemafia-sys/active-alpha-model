"""Google world spread orchestrator."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from analytics.google_world_spread import run_google_world_spread


def test_google_world_spread_blocks_without_tunnel(tmp_path: Path) -> None:
    with patch(
        "analytics.spread_secure_ops.expand_internet_spread",
        return_value={"ok": False, "headline_de": "Tunnel fehlgeschlagen", "welt": {"ok": False}},
    ), patch(
        "analytics.community_spread_plan.broadcast_spread_anonym",
        return_value={"ok": True},
    ), patch(
        "analytics.remote_hub_access.remote_access_status",
        return_value={"tunnel_pid_alive": False, "public_base_url": ""},
    ), patch(
        "analytics.community_spread_plan.collect_spread_urls",
        return_value={},
    ):
        doc = run_google_world_spread(tmp_path, use_gemini=False)
    assert doc["ok"] is False


def test_google_world_spread_skips_gemini_without_key(tmp_path: Path) -> None:
    with patch(
        "analytics.remote_hub_access.ensure_remote_hub_url",
        return_value={"ok": True, "public_base_url": "https://example.trycloudflare.com"},
    ), patch(
        "analytics.spread_secure_ops.expand_internet_spread",
        return_value={"ok": True, "headline_de": "ok"},
    ), patch(
        "analytics.community_spread_plan.broadcast_spread_anonym",
        return_value={"ok": True},
    ), patch(
        "analytics.community_spread_plan.collect_spread_urls",
        return_value={"join_remote": "https://example.trycloudflare.com/join"},
    ), patch(
        "analytics.remote_hub_access.remote_access_status",
        return_value={
            "public_base_url": "https://example.trycloudflare.com",
            "tunnel_stable": False,
            "tunnel_pid_alive": True,
        },
    ), patch(
        "analytics.google_world_spread._generate_global_copy_ollama",
        return_value={"ok": False, "skipped": True},
    ):
        doc = run_google_world_spread(tmp_path, use_gemini=True)
    assert doc["ok"] is True
    assert doc["gemini"].get("ok") is True
    assert doc["gemini"].get("provider") == "template"
    assert (tmp_path / "evidence/spread_google_world_en.txt").is_file()


def test_google_world_spread_uses_ollama_fallback(tmp_path: Path) -> None:
    with patch(
        "analytics.spread_secure_ops.expand_internet_spread",
        return_value={"ok": True, "headline_de": "ok"},
    ), patch(
        "analytics.community_spread_plan.broadcast_spread_anonym",
        return_value={"ok": True},
    ), patch(
        "analytics.community_spread_plan.collect_spread_urls",
        return_value={"join_remote": "https://example.trycloudflare.com/join"},
    ), patch(
        "analytics.remote_hub_access.remote_access_status",
        return_value={
            "public_base_url": "https://example.trycloudflare.com",
            "tunnel_stable": False,
            "tunnel_pid_alive": True,
        },
    ), patch(
        "analytics.google_world_spread._generate_global_copy_gemini",
        return_value={"ok": False, "skipped": True},
    ), patch(
        "analytics.google_world_spread._generate_global_copy_ollama",
        return_value={
            "ok": True,
            "provider": "ollama",
            "fallback": True,
            "path": "evidence/spread_google_world_en.txt",
        },
    ):
        doc = run_google_world_spread(tmp_path, use_gemini=True)
    assert doc["gemini"].get("provider") == "ollama"
