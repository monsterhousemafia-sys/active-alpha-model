from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.r3_unified import (
    build_power_status,
    classify_intent,
    dispatch_unified,
    format_power_status_de,
)


def test_classify_intent() -> None:
    root = Path(__file__).resolve().parents[1]
    assert classify_intent("Welche Aktien heute?", root=root) == "trading"
    assert classify_intent("implementiere Status-Tile", root=root) == "build_strong"
    assert classify_intent("Wie ist der status?", root=root) == "status"


def test_build_power_status() -> None:
    root = Path(__file__).resolve().parents[1]
    st = build_power_status(root)
    assert st.get("power_pct") is not None
    assert len(st.get("modules") or []) >= 4


def test_dispatch_r3_command() -> None:
    root = Path(__file__).resolve().parents[1]
    out = dispatch_unified(root, "/r3")
    assert out.get("unified")
    assert out.get("ok")
    assert "R3 Power" in out.get("reply_de", "")


def test_dispatch_freetext_trading() -> None:
    root = Path(__file__).resolve().parents[1]
    out = dispatch_unified(root, "Welche Aktien steigen heute?")
    assert out.get("unified")
    assert out.get("intent") == "trading"
    assert "Prognose" in out.get("reply_de", "") or "Top" in out.get("reply_de", "")


def test_format_power() -> None:
    root = Path(__file__).resolve().parents[1]
    text = format_power_status_de(root)
    assert "Module" in text
