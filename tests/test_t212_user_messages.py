from integrations.trading212.t212_user_messages import (
    humanize_connection_status,
    humanize_t212_error,
    success_message,
)


def test_no_bare_http_429_in_user_text() -> None:
    msg = humanize_t212_error("HTTP 429")
    assert "HTTP" not in msg
    assert "429" not in msg
    assert "⏱" in msg


def test_insufficient_funds_humanized() -> None:
    raw = 'HTTP 400: {"type": "/api-errors/insufficient-free-for-stocks-buy", "detail": "Insufficient funds"}'
    msg = humanize_t212_error(raw)
    assert "HTTP" not in msg
    assert "400" not in msg
    assert "💶" in msg
    assert "Guthaben" in msg


def test_success_message_has_symbol() -> None:
    assert success_message("OK").startswith("✓")


def test_connected_status() -> None:
    assert "✓" in humanize_connection_status("LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE")
