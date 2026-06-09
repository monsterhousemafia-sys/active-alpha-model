"""Trading 212 environment guard — strict DEMO-only URL validation."""
from __future__ import annotations

from urllib.parse import urlparse

DEMO_BASE_URL = "https://demo.trading212.com/api/v0"
LIVE_HOST = "live.trading212.com"
DEMO_HOST = "demo.trading212.com"
ALLOWED_SCHEME = "https"
ALLOWED_API_PREFIX = "/api/v0"
DEFAULT_HTTPS_PORT = 443


def _parse_url(url: str):
    return urlparse(url.strip())


def _validate_api_path(path: str) -> None:
    if path == ALLOWED_API_PREFIX:
        return
    if not path.startswith(f"{ALLOWED_API_PREFIX}/"):
        raise PermissionError(f"TRADING212_INVALID_API_BASE_PATH:{path}")
    suffix = path[len(ALLOWED_API_PREFIX) :]
    if suffix.startswith("/") and (suffix.startswith("/0") or "evil" in suffix.lower()):
        raise PermissionError(f"TRADING212_INVALID_API_PATH_SUFFIX:{path}")


def assert_demo_url(url: str) -> None:
    """Reject live hosts, non-https, lookalikes, userinfo, bad ports, fragments."""
    parsed = _parse_url(url)
    if parsed.scheme != ALLOWED_SCHEME:
        raise PermissionError(f"TRADING212_NON_HTTPS_SCHEME_BLOCKED:{parsed.scheme}")
    if parsed.username or parsed.password:
        raise PermissionError("TRADING212_URL_USERINFO_BLOCKED")
    if parsed.fragment:
        raise PermissionError("TRADING212_URL_FRAGMENT_BLOCKED")
    host = (parsed.hostname or "").lower()
    if host == LIVE_HOST or LIVE_HOST in url:
        raise PermissionError("TRADING212_LIVE_HOST_BLOCKED")
    if host != DEMO_HOST:
        raise PermissionError(f"TRADING212_NON_DEMO_HOST_BLOCKED:{host or 'missing'}")
    if parsed.port is not None and parsed.port != DEFAULT_HTTPS_PORT:
        raise PermissionError(f"TRADING212_UNEXPECTED_PORT_BLOCKED:{parsed.port}")
    path = parsed.path or ""
    _validate_api_path(path)


def build_demo_url(path: str, query: str = "") -> str:
    normalized = normalize_demo_path(path)
    from integrations.trading212.t212_query_policy import validate_query_for_path

    validate_query_for_path(normalized, query)
    url = f"https://{DEMO_HOST}{ALLOWED_API_PREFIX}{normalized}"
    if query:
        url = f"{url}?{query.lstrip('?')}"
    assert_demo_url(url.split("?", 1)[0] if "?" in url else url)
    if query:
        assert_demo_url(url)
    return url


def normalize_demo_path(path: str) -> str:
    if path.startswith("http"):
        assert_demo_url(path.split("?", 1)[0])
        parsed = _parse_url(path)
        remainder = parsed.path.split(ALLOWED_API_PREFIX, 1)[-1]
        return remainder if remainder.startswith("/") else f"/{remainder}"
    return path if path.startswith("/") else f"/{path}"


def validate_redirect_target(url: str) -> None:
    assert_demo_url(url.split("?", 1)[0] if "?" in url else url)
