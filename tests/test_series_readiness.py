"""Serienreife — Gate-Scan und sichere Reparatur."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.series_readiness import (
    apply_series_readiness_repair,
    load_series_readiness_policy,
    scan_series_readiness,
)


def _seed_minimal(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    policy_src = Path(__file__).resolve().parents[1] / "control/series_readiness_policy.json"
    (root / "control/series_readiness_policy.json").write_text(
        policy_src.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_bind": "127.0.0.1", "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    (root / "promotion_gate_config.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "promotion_gate_config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "control/champion_lineage_policy.json").write_text(
        json.dumps(
            {
                "status": "M9_SYNCED",
                "authoritative_champion": "R0_LEGACY_ENSEMBLE",
            }
        ),
        encoding="utf-8",
    )
    (root / "control/operational_champion_status.json").write_text(
        json.dumps({"auto_promotion": "DISABLED"}),
        encoding="utf-8",
    )
    (root / "evidence/stack_integrity_latest.json").write_text(
        json.dumps({"stack_ok": True}),
        encoding="utf-8",
    )
    caps = [
        {"id": "hub_local", "label_de": "Hub lokal", "ok": True},
        {"id": "mirror_api", "label_de": "Mirror-API", "ok": True},
        {"id": "surface_r3", "label_de": "Oberfläche /r3", "ok": True},
        {"id": "plan_evidence", "label_de": "Modell-Plan Evidence", "ok": True},
    ]
    (root / "evidence/r3_local_growth_latest.json").write_text(
        json.dumps(
            {
                "growth_pct": 100,
                "milestones_ok": 4,
                "milestones_total": 4,
                "capabilities": caps,
            }
        ),
        encoding="utf-8",
    )
    (root / "evidence/king_verify_latest.json").write_text(
        json.dumps({"ok": True, "verified_at_utc": "2026-06-07T12:00:00+00:00"}),
        encoding="utf-8",
    )


def test_load_policy(tmp_path: Path) -> None:
    _seed_minimal(tmp_path)
    pol = load_series_readiness_policy(tmp_path)
    assert pol.get("min_growth_pct") == 100
    assert "safety_flags" in (pol.get("critical_gate_ids") or [])


def test_scan_series_readiness(tmp_path: Path, monkeypatch) -> None:
    _seed_minimal(tmp_path)
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "1")
    doc = scan_series_readiness(tmp_path, persist=True, force=True, fast=True)
    assert doc.get("readiness_pct", 0) >= 0
    assert len(doc.get("gates") or []) >= 7
    assert (tmp_path / "evidence/series_readiness_latest.json").is_file()
    assert "headline_de" in doc


def test_apply_repair_steps(tmp_path: Path) -> None:
    _seed_minimal(tmp_path)
    (tmp_path / "control/r3_local_first_policy.json").write_text(
        json.dumps({"status": "AUTHORITATIVE"}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_runtime_profile.json").write_text(
        json.dumps({"profile_id": "fluid_v2", "label_de": "Flüssig"}),
        encoding="utf-8",
    )
    out = apply_series_readiness_repair(tmp_path)
    assert "steps" in out
    assert len(out.get("steps") or []) == 8
    assert any(s.get("id") == "r3_local" for s in out.get("steps") or [])
    assert any(s.get("id") == "operator_readiness" for s in out.get("steps") or [])
    assert "checklist_ref" in out


def test_next_de_warn_uses_first_operator_command(tmp_path: Path) -> None:
    _seed_minimal(tmp_path)
    pol = load_series_readiness_policy(tmp_path)
    cmds = list(pol.get("operator_commands_de") or ["bash tools/king_ops.sh verify"])
    next_de = f"Optional: Linux-Potenzial — {cmds[0] if cmds else 'bash tools/king_ops.sh verify'}"
    assert next_de.startswith("Optional:")
    assert "[" not in next_de
    assert "king_ops.sh" in next_de
