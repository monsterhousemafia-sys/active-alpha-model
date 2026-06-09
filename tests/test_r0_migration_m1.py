"""M1 R0 migration evidence baseline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_m1_artifacts_exist():
    for rel in (
        "evidence/r0_migration/pointer_audit.json",
        "evidence/r0_migration/env_alpha_model_mode_audit.json",
        "evidence/r0_migration/returns_manifest.json",
        "evidence/r0_migration/validation_runs_status.json",
        "evidence/r0_migration/M1_BACKTEST_INSTRUCTIONS.md",
        "evidence/r0_migration/crash_recovery.json",
    ):
        assert (ROOT / rel).is_file(), rel


def test_m1_env_ensemble_after_fix():
    audit = json.loads(
        (ROOT / "evidence" / "r0_migration" / "env_alpha_model_mode_audit.json").read_text(encoding="utf-8")
    )
    for entry in audit.get("files") or []:
        if entry.get("file") in ("active_alpha_user_config.bat", "active_alpha_settings.bat"):
            assert entry.get("AA_ALPHA_MODEL_MODE") == "ensemble"


def test_m1_returns_manifest_schema():
    manifest = json.loads(
        (ROOT / "evidence" / "r0_migration" / "returns_manifest.json").read_text(encoding="utf-8")
    )
    for vid in ("R0_LEGACY_ENSEMBLE", "R3_w075_q065_noexit", "M1_MOM_BLEND_MATCHED_CONTROLS"):
        assert vid in manifest.get("variants", {})


def test_m1_waiver_when_preparation_run():
    path = ROOT / "control" / "r0_migration" / "m1_backtest_waiver.json"
    if not path.is_file():
        pytest.skip("preparation not run")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("evidence_only") is True
    assert data.get("status") == "ACTIVE"


def test_path_only_cmd_preserves_shared_cache_dir(tmp_path: Path) -> None:
    from tools.r0_migration_sla_enforce import _build_path_only_cmd

    r0 = tmp_path / "validation_runs" / "20260101T120000Z_R0_LEGACY_ENSEMBLE"
    r0.mkdir(parents=True)
    shared = tmp_path / "robustness_results_trading212" / "_shared_cache"
    line = (
        f"python active_alpha_model.py --mode backtest --force-rebuild-predictions "
        f"--shared-cache-dir {shared} --out-dir {r0} --risk-off-selection-mode legacy"
    )
    (r0 / "validation_run.log").write_text(line + "\n", encoding="utf-8")
    cmd = _build_path_only_cmd(tmp_path, r0)
    assert "--shared-cache-dir" in cmd
    assert cmd[cmd.index("--shared-cache-dir") + 1] == str(shared)
    assert cmd[cmd.index("--backtest-scope") + 1] == "path-only"
    assert cmd[cmd.index("--prediction-cache-dir") + 1] == str(r0)
    assert "--parallel-backtest-backend" in cmd
    assert cmd[cmd.index("--parallel-backtest-backend") + 1] == "thread"
    assert cmd[cmd.index("--n-jobs") + 1] == "1"


def test_sla_blocks_full_matrix_while_canonical_r0_incomplete(tmp_path: Path) -> None:
    from tools.run_r0_migration_phase_m1 import _sla_blocks_full_matrix_launch

    (tmp_path / "control" / "r0_migration").mkdir(parents=True)
    (tmp_path / "control" / "r0_migration" / "m1_sla_6h.json").write_text(
        json.dumps({"deadline_enforced": True, "canonical_r0_stamp": "20260101T120000Z"}),
        encoding="utf-8",
    )
    vr = tmp_path / "validation_runs" / "20260101T120000Z_R0_LEGACY_ENSEMBLE"
    vr.mkdir(parents=True)
    assert _sla_blocks_full_matrix_launch(tmp_path, list(("R0_LEGACY_ENSEMBLE",))) is not None
    assert _sla_blocks_full_matrix_launch(tmp_path, ["R3_w075_q065_noexit"]) is not None


def test_m1_phase_status():
    data = json.loads((ROOT / "control" / "r0_migration" / "phase_status.json").read_text(encoding="utf-8"))
    assert data["phases"]["M1"]["status"] in (
        "COMPLETE",
        "COMPLETE_WITH_BLOCKER",
        "IN_PROGRESS",
        "SEALED",
        "READY",
        "READY_TO_SEAL",
        "PENDING",
    )
    assert data["current_phase"] in ("M1", "M2")
