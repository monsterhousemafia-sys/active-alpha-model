from integrations.trading212.t212_order_error_parser import (
    extract_min_quantity,
    is_min_quantity_error,
    parse_t212_order_error,
)


def test_parse_min_quantity() -> None:
    msg = 'HTTP 400: {"detail": "must trade at least 0.02330155"}'
    p = parse_t212_order_error(msg)
    assert p.category == "min_quantity"
    assert extract_min_quantity(msg) == 0.02330155
    assert is_min_quantity_error(msg)


def test_parse_insufficient() -> None:
    msg = 'HTTP 400: {"type": "/api-errors/insufficient-free-for-stocks-buy"}'
    assert parse_t212_order_error(msg).category == "insufficient"
