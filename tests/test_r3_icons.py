from __future__ import annotations

from analytics.r3_icons import ALL_ICONS, closure_status_icon, icon_svg, icon_span, shell_icon_svg


def test_all_icons_have_svg() -> None:
    for name, svg in ALL_ICONS.items():
        assert "<svg" in svg, name
        assert "viewBox" in svg, name


def test_shell_icon_fallback() -> None:
    assert "<svg" in shell_icon_svg("unknown_feature")
    assert "<svg" in shell_icon_svg("network")


def test_icon_span_wrapper() -> None:
    html = icon_span("mic")
    assert "r3-ico" in html
    assert "<svg" in html


def test_closure_status_icons() -> None:
    assert "<svg" in closure_status_icon("native")
    assert "<svg" in closure_status_icon("partial")
    assert "<svg" in icon_svg("send")
