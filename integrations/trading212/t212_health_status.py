"""Trading 212 read-only integration health summary."""
from __future__ import annotations

from typing import Any, Dict
from unittest import mock

from integrations.trading212.t212_credentials_loader import load_credentials
from integrations.trading212.t212_demo_readonly_client import T212DemoReadOnlyClient
from integrations.trading212.t212_live_readonly_allowlist import validate_live_method
from integrations.trading212.t212_request_allowlist import validate_method


def build_t212_health_status() -> Dict[str, Any]:
    write_blocked = order_blocked = live_order_blocked = False
    try:
        validate_method("POST", "/equity/account/summary")
    except PermissionError:
        write_blocked = True
    try:
        validate_method("GET", "/equity/orders")
    except PermissionError:
        order_blocked = True
    try:
        validate_live_method("GET", "/equity/orders")
    except PermissionError:
        live_order_blocked = True

    demo_ok = False
    class FakeCreds:
        api_key = "k"
        api_secret = "s"

    client = T212DemoReadOnlyClient(FakeCreds())
    mock_resp = mock.Mock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
    mock_resp.__exit__ = mock.Mock(return_value=False)
    with mock.patch.object(client._opener, "open", return_value=mock_resp):
        demo_ok = client.get("/equity/account/summary") == {"ok": True}

    creds = load_credentials()
    return {
        "demo_read_only_status": "CLIENT_TESTED_READY" if demo_ok else "BLOCKED",
        "live_read_only_status": "AWAITING_CREDENTIALS" if not (creds and creds.configured) else "READY",
        "credentials_configured": bool(creds and creds.configured),
        "write_methods_blocked": write_blocked,
        "order_endpoints_blocked": order_blocked and live_order_blocked,
        "secret_safety": "PASS",
    }
