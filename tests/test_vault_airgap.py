from __future__ import annotations

from pathlib import Path

from analytics.secure_credential_portal import is_localhost_client
from analytics.vault_airgap import hub_does_not_proxy_vault, verify_airgap


class _Handler:
    client_address = ("127.0.0.1", 0)
    headers = {"X-Forwarded-For": "8.8.8.8"}


def test_ignore_forwarded_for():
    assert is_localhost_client(_Handler()) is True


def test_hub_does_not_proxy_vault(tmp_path: Path):
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/cloudflare_tunnel.json").write_text(
        '{"public_url":"https://hub.example.com"}', encoding="utf-8"
    )
    doc = hub_does_not_proxy_vault(tmp_path)
    assert doc.get("ok") is True


def test_verify_airgap_clean(tmp_path: Path):
    doc = verify_airgap(tmp_path)
    assert "airgapped" in doc
    assert "principles_de" in doc
