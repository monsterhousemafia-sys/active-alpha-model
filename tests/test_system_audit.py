"""Systemaudit — Aggregation und Evidence."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.system_audit import run_system_audit


def _seed(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parents[1]
    (root / "promotion_gate_config.yaml").write_text(
        (src / "promotion_gate_config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "control/champion_lineage_policy.json").write_text(
        json.dumps({"status": "M9_SYNCED", "authoritative_champion": "R0_LEGACY_ENSEMBLE"}),
        encoding="utf-8",
    )
    (root / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_bind": "127.0.0.1"}),
        encoding="utf-8",
    )
    caps = [
        {"id": "hub_local", "label_de": "Hub", "ok": True},
        {"id": "mirror_api", "label_de": "Mirror", "ok": True},
        {"id": "surface_r3", "label_de": "/r3", "ok": True},
        {"id": "plan_evidence", "label_de": "Plan", "ok": True},
    ]
    (root / "evidence/r3_local_growth_latest.json").write_text(
        json.dumps({"growth_pct": 100, "milestones_ok": 4, "milestones_total": 4, "capabilities": caps}),
        encoding="utf-8",
    )
    (root / "evidence/stack_integrity_latest.json").write_text(
        json.dumps({"stack_ok": True, "r3": {"mirror_api_ok": True, "surface_page_ok": True}}),
        encoding="utf-8",
    )
    (root / "evidence/desktop_shell_cache_meta.json").write_text(
        json.dumps({"bytes": 5000}),
        encoding="utf-8",
    )
    (root / "control/series_readiness_policy.json").write_text(
        (src / "control/series_readiness_policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "control/r3_local_growth.json").write_text(
        (src / "control/r3_local_growth.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_run_system_audit(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path)
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "1")
    doc = run_system_audit(tmp_path, persist=True, live_stack=False, run_tests=False)
    assert len(doc.get("sections") or []) >= 7
    assert (tmp_path / "evidence/system_audit_latest.json").is_file()
    assert "headline_de" in doc


def test_surface_stack_fallback(tmp_path: Path) -> None:
    from analytics.r3_local_growth import scan_local_growth
    from tests.r3_order_fixtures import seed_orders_stack

    _seed(tmp_path)
    seed_orders_stack(tmp_path)
    (tmp_path / "control/r3_runtime_profile.json").write_text(
        json.dumps({"profile_id": "fluid_v2", "label_de": "Flüssig"}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_runtime_upgrade_catalog.json").write_text(
        json.dumps({"upgrades": [{"proposal_id": "fluid_mirror_v2"}]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_runtime_upgrade_latest.json").write_text(
        json.dumps({"schema_version": 1, "applied_profile_id": "fluid_v2"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_functions_latest.json").write_text(
        json.dumps({"functions": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_local_growth_latest.json").unlink(missing_ok=True)
    doc = scan_local_growth(tmp_path, persist=True, force=True, fast=False)
    caps = {c["id"]: c for c in doc.get("capabilities") or []}
    assert caps.get("surface_r3", {}).get("ok") is True
    assert caps.get("hub_local", {}).get("ok") is True
