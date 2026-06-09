"""Trading 212 demo read-only HTTP client with redirect guard."""
from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict

from integrations.trading212.t212_credentials_loader import T212Credentials
from integrations.trading212.t212_environment_guard import DEMO_BASE_URL, assert_demo_url, build_demo_url
from integrations.trading212.t212_redirect_guard import T212RedirectGuardHandler
from integrations.trading212.t212_request_allowlist import validate_method
from integrations.trading212.t212_secret_redaction import redact_secrets


class T212DemoReadOnlyError(RuntimeError):
    pass


class T212DemoReadOnlyClient:
    def __init__(self, credentials: T212Credentials, *, timeout_s: float = 20.0) -> None:
        self.credentials = credentials
        self.base_url = DEMO_BASE_URL
        self.timeout_s = timeout_s
        assert_demo_url(self.base_url)
        self._opener = urllib.request.build_opener(
            T212RedirectGuardHandler(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.credentials.api_key}:{self.credentials.api_secret}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"

    def get(self, path: str) -> Dict[str, Any]:
        validate_method("GET", path)
        url = build_demo_url(path.split("?", 1)[0], path.split("?", 1)[1] if "?" in path else "")
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self._auth_header(),
                "Accept": "application/json",
                "User-Agent": "ActiveAlpha-P16-DemoReadOnly/1.0",
            },
            method="GET",
        )
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            raise T212DemoReadOnlyError(redact_secrets(f"HTTP {exc.code} for path")) from exc
        except urllib.error.URLError as exc:
            raise T212DemoReadOnlyError(redact_secrets(str(exc))) from exc

    def get_account_summary(self) -> Dict[str, Any]:
        return self.get("/equity/account/summary")

    def get_positions(self) -> Dict[str, Any]:
        return self.get("/equity/positions")

    def get_instruments_metadata(self) -> Any:
        return self.get("/equity/metadata/instruments")
