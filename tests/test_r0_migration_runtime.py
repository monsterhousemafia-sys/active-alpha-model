"""M1 runtime signals."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_count_validation_matrix_processes_non_negative():
    from tools.r0_migration_runtime import count_validation_matrix_processes

    assert count_validation_matrix_processes(ROOT) >= 0


def test_newest_run_dir_prefers_canonical_r0_stamp(tmp_path: Path) -> None:
    from tools.r0_migration_runtime import newest_run_dir_for_variant

    vr = tmp_path / "validation_runs"
    vr.mkdir(parents=True)
    old = vr / "20260101T000000Z_R0_LEGACY_ENSEMBLE"
    new = vr / "20260201T000000Z_R0_LEGACY_ENSEMBLE"
    canon = vr / "20260115T120000Z_R0_LEGACY_ENSEMBLE"
    for d in (old, new, canon):
        d.mkdir()
        (d / "marker.txt").write_text("x", encoding="utf-8")
    (tmp_path / "control" / "r0_migration").mkdir(parents=True)
    (tmp_path / "control" / "r0_migration" / "m1_sla_6h.json").write_text(
        json.dumps({"canonical_r0_stamp": "20260115T120000Z"}),
        encoding="utf-8",
    )
    picked = newest_run_dir_for_variant(tmp_path, "R0_LEGACY_ENSEMBLE")
    assert picked == canon
