"""R3 Shell Brand — gemeinsame Lade-/Icon-Farben."""
from __future__ import annotations

from analytics.r3_shell_brand import (
    R3_APP_NAME,
    R3_BRAND_GRADIENT,
    R3_ORANGE_BOTTOM,
    R3_ORANGE_TOP,
    head_link_tags,
    loading_html,
)


def test_brand_gradient_matches_icon_colors() -> None:
    assert R3_ORANGE_TOP in R3_BRAND_GRADIENT
    assert R3_ORANGE_BOTTOM in R3_BRAND_GRADIENT


def test_loading_html_contains_brand_mark() -> None:
    html = loading_html()
    assert "R3" in html
    assert R3_ORANGE_TOP in html
    assert "spin" in html


def test_app_name_and_favicon() -> None:
    assert R3_APP_NAME == "R3"
    assert "/assets/r3-icon.svg" in head_link_tags()
