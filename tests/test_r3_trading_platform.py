"""R3 Handelsplattform — Ergebnisse only, Alpha Model trainiert im Hintergrund."""
from pathlib import Path

from analytics.r3_trading_platform import (
    build_r3_trading_platform_status,
    load_trading_platform_policy,
)
from analytics.r3_t212_prognosis import load_product_roles, render_r3_t212_prognosis_section


def test_trading_platform_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_trading_platform_policy(root)
    assert "Handelsplattform" in str(policy.get("headline_de") or "")
    assert policy.get("presentation_rules_de")


def test_product_roles_platform_vs_model() -> None:
    roles = load_product_roles(Path(__file__).resolve().parents[1])
    assert roles.get("r3_de", {}).get("role") == "Zentrale Handelsplattform"
    assert "täglich" in str(roles.get("active_alpha_model_de", {}).get("delivers_de") or "").lower()
    assert roles.get("r3_de", {}).get("presentation_only_de")


def test_build_platform_status() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_r3_trading_platform_status(root, persist=True)
    assert doc.get("presentation_only") is True
    assert doc.get("platform_de") == "R3"
    assert "model_training" in doc
    assert "trading_result" in doc
    assert (root / "evidence/r3_trading_platform_latest.json").is_file()


def test_render_desktop_r3_only() -> None:
    html_out = render_r3_t212_prognosis_section(
        Path(__file__).resolve().parents[1], desktop_only=True
    )
    if html_out:
        assert "r3-desktop" in html_out
