"""Confirmed execution client — POST limit orders only with guards."""
from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION
from integrations.trading212.t212_credentials_loader import T212Credentials
from integrations.trading212.t212_dual_profile_credential_store import get_profile_credentials
from integrations.trading212.t212_execution_endpoint_registry import (
    CONFIRMED_CANCEL_PATH_PREFIX,
    CONFIRMED_LIVE_POST_PATHS,
)
from integrations.trading212.t212_secret_redaction import redact_secrets

LIVE_HOST = "live.trading212.com"


class T212ExecutionBlockedError(RuntimeError):
    pass


class T212ConfirmedExecutionClient:
    """Submits only user-confirmed limit orders — never auto-routes."""

    def __init__(self, credentials: T212Credentials, *, timeout_s: float = 20.0) -> None:
        self.credentials = credentials
        self.timeout_s = timeout_s
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )

    @classmethod
    def from_execution_profile(cls, root: Path | None = None) -> "T212ConfirmedExecutionClient":
        creds = get_profile_credentials(PROFILE_CONFIRMED_EXECUTION)
        if (not creds or not creds.configured) and root is not None:
            from integrations.trading212.t212_dual_profile_secure_store import load_profile_credentials
            from integrations.trading212.t212_execution_dpapi_store import load_execution_credentials

            creds = load_execution_credentials(Path(root)) or load_profile_credentials(
                PROFILE_CONFIRMED_EXECUTION
            )
            if creds and creds.configured:
                from integrations.trading212.t212_dual_profile_credential_store import set_profile_credentials

                set_profile_credentials(
                    PROFILE_CONFIRMED_EXECUTION,
                    api_key=creds.api_key,
                    api_secret=creds.api_secret,
                )
        if not creds or not creds.configured:
            raise T212ExecutionBlockedError("EXECUTION_PROFILE_NOT_CONFIGURED")
        return cls(creds)

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.credentials.api_key}:{self.credentials.api_secret}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"

    def _assert_credentials_ready(self) -> None:
        if not self.credentials.configured:
            raise T212ExecutionBlockedError("EXECUTION_PROFILE_NOT_CONFIGURED")

    def _assert_submission_allowed(self, root: Optional[Path] = None) -> None:
        self._assert_credentials_ready()
        from execution.linux_security_boundary import assert_live_submission_host_allowed

        assert_live_submission_host_allowed()
        from execution.confirmed_live.p17_review_mode_guard import review_mode_active
        from execution.confirmed_live.pilot_live_trading_policy import live_submission_allowed

        if review_mode_active():
            if root is None or not live_submission_allowed(root):
                raise T212ExecutionBlockedError("P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION")
        if os.environ.get("AA_NO_LIVE_ORDER_SUBMISSION", "").strip() == "1":
            raise T212ExecutionBlockedError("LIVE_SUBMISSION_BLOCKED_BY_ENV")
        if os.environ.get("AA_DECISION_COCKPIT_SMOKE_TEST", "").strip() == "1":
            raise T212ExecutionBlockedError("LIVE_SUBMISSION_BLOCKED_SMOKE_TEST")
        if os.environ.get("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "").strip() == "1":
            raise T212ExecutionBlockedError("LIVE_SUBMISSION_BLOCKED_SMOKE_TEST")

    def _request(
        self,
        method: str,
        path: str,
        *,
        root: Optional[Path] = None,
        body: Optional[Dict[str, Any]] = None,
        submission: bool = True,
    ) -> Dict[str, Any]:
        if submission:
            self._assert_submission_allowed(root)
        else:
            self._assert_credentials_ready()
        if method == "POST" and path not in CONFIRMED_LIVE_POST_PATHS:
            raise T212ExecutionBlockedError("ENDPOINT_NOT_IN_REGISTRY")
        if method == "DELETE" and not path.startswith(CONFIRMED_CANCEL_PATH_PREFIX):
            raise T212ExecutionBlockedError("ENDPOINT_NOT_IN_REGISTRY")
        if method == "GET" and path != "/equity/orders":
            raise T212ExecutionBlockedError("ENDPOINT_NOT_IN_REGISTRY")
        url = f"https://{LIVE_HOST}/api/v0{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": self._auth_header(),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ActiveAlpha-P16H-ConfirmedExecution/1.0",
            },
            method=method,
        )
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                raw_err = exc.read().decode("utf-8", errors="replace")
                if raw_err.strip():
                    parsed = json.loads(raw_err)
                    detail = redact_secrets(json.dumps(parsed, ensure_ascii=False))[:400]
            except Exception:
                pass
            msg = f"HTTP {exc.code}"
            if detail:
                msg = f"{msg}: {detail}"
            raise T212ExecutionBlockedError(redact_secrets(msg)) from exc

    def get_json(self, path: str, *, root: Optional[Path] = None) -> Any:
        return self._request("GET", path, root=root, submission=False)

    def cancel_order(self, order_id: int | str, *, root: Optional[Path] = None) -> Dict[str, Any]:
        oid = str(order_id).strip()
        if not oid.isdigit():
            raise T212ExecutionBlockedError("INVALID_ORDER_ID")
        return self._request("DELETE", f"{CONFIRMED_CANCEL_PATH_PREFIX}{oid}", root=root)

    def submit_limit_order(self, body: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
        self._assert_submission_allowed(root)
        path = "/equity/orders/limit"
        if path not in CONFIRMED_LIVE_POST_PATHS:
            raise T212ExecutionBlockedError("ENDPOINT_NOT_IN_REGISTRY")
        return self._request("POST", path, root=root, body=body)

    def submit_market_order(self, body: Dict[str, Any], *, root: Optional[Path] = None) -> Dict[str, Any]:
        path = "/equity/orders/market"
        payload = dict(body)
        if "extendedHours" not in payload:
            payload["extendedHours"] = False
        return self._request("POST", path, root=root, body=payload)

    def dry_run_submit(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Mock submission for tests — no network."""
        return {"dry_run": True, "status": "SUBMITTED_AWAITING_READONLY_RECONCILIATION", "body_keys": sorted(body.keys())}
