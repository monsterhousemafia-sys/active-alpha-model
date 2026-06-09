"""Trading 212 LIVE read-only client — GET-only, no orders."""
from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict

from integrations.trading212.t212_credentials_loader import T212Credentials
from integrations.trading212.t212_live_readonly_allowlist import validate_live_get_path, validate_live_method
from integrations.trading212.t212_live_readonly_guard import assert_live_readonly_url
from integrations.trading212.t212_secret_redaction import redact_secrets

LIVE_BASE_URL = "https://live.trading212.com/api/v0"
LIVE_HOST = "live.trading212.com"


class T212LiveReadOnlyError(RuntimeError):
    pass


class T212LiveNoRedirectHandler(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        if 300 <= response.status < 400:
            raise T212LiveReadOnlyError("TRADING212_LIVE_REDIRECT_BLOCKED")
        return response


def build_live_readonly_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    validate_live_get_path(normalized)
    url = f"https://{LIVE_HOST}/api/v0{normalized}"
    assert_live_readonly_url(url)
    return url


class T212LiveReadOnlyClient:
    """GET-only live account observation — never submits orders."""

    def __init__(self, credentials: T212Credentials, *, timeout_s: float = 20.0) -> None:
        self.credentials = credentials
        self.timeout_s = timeout_s
        self._opener = urllib.request.build_opener(
            T212LiveNoRedirectHandler(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.credentials.api_key}:{self.credentials.api_secret}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"

    def get(self, path: str) -> Dict[str, Any]:
        validate_live_method("GET", path)
        url = build_live_readonly_url(path.split("?", 1)[0])
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self._auth_header(),
                "Accept": "application/json",
                "User-Agent": "ActiveAlpha-P16E-LiveReadOnly/1.0",
            },
            method="GET",
        )
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            raise T212LiveReadOnlyError(redact_secrets(f"HTTP {exc.code}")) from exc
        except urllib.error.URLError as exc:
            raise T212LiveReadOnlyError(redact_secrets(str(exc))) from exc

    def get_account_summary(self) -> Dict[str, Any]:
        return self.get("/equity/account/summary")

    def get_positions(self) -> Dict[str, Any]:
        return self.get("/equity/positions")
