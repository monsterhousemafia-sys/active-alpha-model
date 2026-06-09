"""Strategy registry tests."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mom_63_top12_alias_documented():
    reg = ROOT / "research/registry/strategy_registry.json"
    if not reg.is_file():
        return
    data = json.loads(reg.read_text(encoding="utf-8"))
    assert data.get("resolution") == "ALIAS_INCONSISTENCY_DOCUMENTED"
    ids = {s["strategy_id"] for s in data.get("strategies") or []}
    assert "MOM_63_TOP12_STRICT" in ids
    assert "MOM_63_TOP15_RECONSTRUCTED" in ids


def test_top12_strict_has_top_k_12():
    reg = ROOT / "research/registry/strategy_registry.json"
    if not reg.is_file():
        return
    data = json.loads(reg.read_text(encoding="utf-8"))
    strict = next(s for s in data["strategies"] if s["strategy_id"] == "MOM_63_TOP12_STRICT")
    assert strict["top_k"] == 12
