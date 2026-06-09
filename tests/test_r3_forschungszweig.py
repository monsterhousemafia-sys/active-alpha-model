from __future__ import annotations

from pathlib import Path

from analytics.r3_forschungszweig import (
    build_forschungszweig_status,
    classify_mandate_branch,
    load_forschungszweig_config,
    strip_branch_prefix,
)


def test_classify_branch() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_forschungszweig_config(root)
    assert classify_mandate_branch("Tagesprognose für AAPL verbessern", cfg) == "forschungszweig_finanzierung"
    assert classify_mandate_branch("Cockpit-Tile neu gestalten", cfg) == "r3_os"
    assert classify_mandate_branch("forschung Signal-Chart", cfg) == "forschungszweig_finanzierung"


def test_strip_prefix() -> None:
    assert strip_branch_prefix("forschung Rebalance UI") == "Rebalance UI"


def test_build_status() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_forschungszweig_status(root)
    assert doc.get("branch_id") == "forschungszweig_finanzierung"
    assert doc.get("title_de")
    assert doc.get("headline_de")
    assert (doc.get("king_32b_forschung") or {}).get("is_forschungsprojekt") is True
