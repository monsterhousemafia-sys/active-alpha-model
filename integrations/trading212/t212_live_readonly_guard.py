"""Live read-only URL guard with strict path boundaries."""
from __future__ import annotations

from urllib.parse import urlparse

LIVE_HOST = "live.trading212.com"
ALLOWED_SCHEME = "https"
ALLOWED_API_PREFIX = "/api/v0"
DEFAULT_HTTPS_PORT = 443


def _parse_url(url: str):
    return urlparse(url.strip())


def _validate_live_api_path(path: str) -> None:
    if path == ALLOWED_API_PREFIX:
        return
    if not path.startswith(f"{ALLOWED_API_PREFIX}/"):
        raise PermissionError(f"TRADING212_INVALID_API_BASE_PATH:{path}")
    suffix = path[len(ALLOWED_API_PREFIX) :]
    if suffix.startswith("/0") or "evil" in suffix.lower():
        raise PermissionError(f"TRADING212_INVALID_API_PATH_SUFFIX:{path}")


def assert_live_readonly_url(url: str) -> None:
    parsed = _parse_url(url)
    if parsed.scheme != ALLOWED_SCHEME:
        raise PermissionError(f"TRADING212_NON_HTTPS_SCHEME_BLOCKED:{parsed.scheme}")
    if parsed.username or parsed.password:
        raise PermissionError("TRADING212_URL_USERINFO_BLOCKED")
    if parsed.fragment:
        raise PermissionError("TRADING212_URL_FRAGMENT_BLOCKED")
    host = (parsed.hostname or "").lower()
    if host != LIVE_HOST:
        raise PermissionError(f"TRADING212_UNEXPECTED_LIVE_HOST:{host}")
    if parsed.port is not None and parsed.port != DEFAULT_HTTPS_PORT:
        raise PermissionError(f"TRADING212_UNEXPECTED_PORT_BLOCKED:{parsed.port}")
    _validate_live_api_path(parsed.path or "")


def normalize_live_path(path: str) -> str:
    if path.startswith("http"):
        assert_live_readonly_url(path.split("?", 1)[0])
        parsed = _parse_url(path)
        remainder = parsed.path.split(ALLOWED_API_PREFIX, 1)[-1]
        return remainder if remainder.startswith("/") else f"/{remainder}"
    return path if path.startswith("/") else f"/{path}"


def validate_live_redirect_target(url: str) -> None:
    assert_live_readonly_url(url.split("?", 1)[0] if "?" in url else url)
