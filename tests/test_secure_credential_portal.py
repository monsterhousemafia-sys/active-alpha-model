from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from analytics.secure_credential_portal import (
    _issue_session,
    auto_open_if_needed,
    credential_action_needed,
    is_localhost_client,
    open_portal,
    portal_status,
    reveal_vault_portal,
    run_vault_server,
    store_tunnel_credentials,
)


class _FakeHandler:
    def __init__(self, ip: str) -> None:
        self.client_address = (ip, 0)
        self.headers = {}


def test_localhost_guard():
    assert is_localhost_client(_FakeHandler("127.0.0.1")) is True
    assert is_localhost_client(_FakeHandler("::1")) is True
    assert is_localhost_client(_FakeHandler("192.168.1.5")) is False


def test_store_tunnel_credentials_encrypted(tmp_path: Path):
    token = "eyJhIjoidGVzdC5hLmI.cGF5bG9hZC5zaWdu"
    out = store_tunnel_credentials(
        tmp_path, token=token, url="https://hub.example.com", passphrase="TestPassphrase12!"
    )
    assert out.get("ok") is True
    st = portal_status(tmp_path)
    assert st.get("tunnel_configured") is True
    assert st.get("public_url") == "https://hub.example.com"


def test_vault_server_localhost_only():
    import threading

    root = Path(__file__).resolve().parent.parent
    server = run_vault_server(root, port=0, bind="127.0.0.1")
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sid = _issue_session(root)
        url = f"http://127.0.0.1:{port}/vault?session={sid}"
        with urllib.request.urlopen(url, timeout=3) as resp:
            html = resp.read().decode("utf-8")
        assert "Privatsphäre" in html
        assert "Schlüssel" in html
        assert 'name="tunnel_token"' in html
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/vault/status", timeout=3) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        assert doc.get("localhost_only") is True
    finally:
        server.shutdown()
        server.server_close()


def test_open_portal_returns_session_url(tmp_path: Path):
    doc = open_portal(tmp_path, mode="setup", reason_de="Test")
    assert doc.get("ok") is True
    assert "session=" in str(doc.get("portal_url"))
    assert "127.0.0.1" in str(doc.get("portal_url"))


def test_credential_action_needed_when_empty(tmp_path: Path):
    need = credential_action_needed(tmp_path)
    assert need.get("needed") is True
    assert need.get("mode") == "setup"


def test_auto_open_if_needed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AA_VAULT_NO_AUTO_OPEN", "1")
    doc = auto_open_if_needed(tmp_path, context="test")
    assert doc is not None
    assert doc.get("portal_url")
    assert doc.get("portal_opened") is False


def test_vault_manage_forces_open(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AA_VAULT_NO_AUTO_OPEN", "1")
    token = "eyJhIjoidGVzdC5hLmI.cGF5bG9hZC5zaWdu"
    store_tunnel_credentials(tmp_path, token=token, url="https://hub.example.com")
    need = credential_action_needed(tmp_path, force_manage=True)
    assert need.get("needed") is True
    assert need.get("mode") == "manage"
    doc = reveal_vault_portal(tmp_path, mode="manage", reason_de="Verwalten", auto_open_browser=False)
    assert doc.get("mode") == "manage"
