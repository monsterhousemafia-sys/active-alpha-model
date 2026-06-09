from __future__ import annotations

from pathlib import Path

from analytics.cloudflare_login_flow import plan_login_flow, resolve_public_url


def test_plan_login_flow_oauth_phase(tmp_path: Path):
    doc = plan_login_flow(tmp_path)
    assert doc.get("phase") == "oauth"
    assert len(doc.get("steps") or []) == 3
    assert (tmp_path / "evidence/cloudflare_login_plan.json").is_file()


def test_resolve_public_url_prefers_user(tmp_path: Path):
    url = resolve_public_url(tmp_path, "https://hub.example.com")
    assert url == "https://hub.example.com"
