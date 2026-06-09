from __future__ import annotations

from analytics.hub_runtime import (
    HUB_PRODUCT,
    HUB_SCHEMA_VERSION,
    build_health_report,
    is_healthy,
    parse_health_body,
    probe_route,
)


def test_parse_health_body_ok() -> None:
    raw = (
        b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n"
        + (
            '{"ok": true, "product": "preview-hub", "hub_schema_version": 2}'
        ).encode()
    )
    doc = parse_health_body(raw)
    assert doc.get("ok") is True
    assert doc.get("product") == HUB_PRODUCT


def test_health_doc_validation() -> None:
    legacy = parse_health_body(
        b"HTTP/1.0 200 OK\r\n\r\n" + b'{"ok": true, "product": "legacy-hub"}'
    )
    assert legacy.get("product") == "legacy-hub"
    current = parse_health_body(
        b"HTTP/1.0 200 OK\r\n\r\n"
        + (
            '{"ok": true, "product": "preview-hub", "hub_schema_version": 2}'
        ).encode()
    )
    assert current.get("hub_schema_version") == 2


def test_build_health_report_offline(tmp_path) -> None:
    rep = build_health_report(tmp_path, port=1)
    assert rep.get("layer") == "hub"
    assert rep.get("online") is False
    assert rep.get("hub_schema_version") == HUB_SCHEMA_VERSION


def test_probe_route_unreachable() -> None:
    ok, detail = probe_route(1, "/login", timeout=0.2)
    assert ok is False
    assert detail == "timeout"
