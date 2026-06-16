"""R3 Monitoring-Governance — Policy-Kohärenz."""
from __future__ import annotations

import json
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_monitoring_governance_invariants() -> None:
    root = Path(__file__).resolve().parents[1]
    mon = _load(root / "control/r3_monitoring_governance.json")
    inv = mon["invariants"]
    assert inv["auto_execute_real_money_enabled"] is False
    assert inv["auto_research_enabled"] is False
    assert inv["champion_change_requires_external_approval"] is True


def test_ops_kernel_intraday_includes_fall_watch() -> None:
    root = Path(__file__).resolve().parents[1]
    ops = _load(root / "control/r3_ops_kernel_policy.json")
    daily = _load(root / "control/daily_alpha_ops_policy.json")
    assert "fall_watch" in ops["phases"]["intraday"]["steps"]
    assert "fall_watch" in daily["phases"]["intraday"]["steps"]
    assert ops["monitoring_governance_ref"] == "control/r3_monitoring_governance.json"


def test_strategic_governance_references_monitoring() -> None:
    root = Path(__file__).resolve().parents[1]
    from analytics.strategic_governance import build_governance_manifest

    manifest = build_governance_manifest(root)
    assert manifest.get("monitoring_governance_ref") == "control/r3_monitoring_governance.json"
    assert "Monitoring" in manifest.get("rules_de", "")
