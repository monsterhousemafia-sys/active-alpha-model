from __future__ import annotations

import threading
from pathlib import Path

from analytics.secure_credential_portal import _issue_session, _touch_session, run_vault_server
from analytics.vault_hub_bridge import handle_vault_request, is_localhost_ip


def test_is_localhost_ip():
    assert is_localhost_ip("127.0.0.1") is True
    assert is_localhost_ip("::1") is True
    assert is_localhost_ip("192.168.1.1") is False


def test_vault_bridge_renders_page(tmp_path: Path):
    sid = _issue_session(tmp_path, mode="setup", reason_de="Test")
    _touch_session(tmp_path, sid, cloudflare_login=True)
    status, ctype, body = handle_vault_request(
        tmp_path,
        method="GET",
        path="/local/vault",
        query=f"session={sid}",
        client_ip="127.0.0.1",
    )
    assert status == 200
    assert "text/html" in ctype
    html = body.decode("utf-8")
    assert "Schlüssel" in html
    assert "Fortschritt" in html or "step-item" in html
    assert 'name="vault_passphrase"' in html


def test_vault_bridge_denies_remote(tmp_path: Path):
    status, _, _ = handle_vault_request(
        tmp_path,
        method="GET",
        path="/local/vault",
        query="session=x",
        client_ip="10.0.0.5",
    )
    assert status == 403


def test_vault_direct_server_still_works():
    root = Path(__file__).resolve().parent.parent
    server = run_vault_server(root, port=0, bind="127.0.0.1")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sid = _issue_session(root)
        status, ctype, body = handle_vault_request(
            root,
            method="GET",
            path="/local/vault/status",
            query="",
            client_ip="127.0.0.1",
        )
        assert status == 200
        assert "json" in ctype
        assert b"localhost_only" in body
    finally:
        server.shutdown()
        server.server_close()
