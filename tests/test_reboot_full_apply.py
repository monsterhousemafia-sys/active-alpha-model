"""Neustart-Apply — Vorbereitung und Pending-Marker."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.reboot_full_apply import complete_after_reboot, prepare_before_reboot, reboot_pending


def _seed(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parents[1]
    for name in (
        "control/series_readiness_policy.json",
        "control/r3_local_growth.json",
        "control/linux_potential.json",
        "promotion_gate_config.yaml",
    ):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text((src / name).read_text(encoding="utf-8"), encoding="utf-8")
    (root / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_bind": "127.0.0.1", "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    (root / "control/champion_lineage_policy.json").write_text(
        json.dumps({"status": "M9_SYNCED", "authoritative_champion": "R0_LEGACY_ENSEMBLE"}),
        encoding="utf-8",
    )
    (root / "control/r3_local_first_policy.json").write_text(
        json.dumps({"status": "AUTHORITATIVE"}),
        encoding="utf-8",
    )
    (root / "evidence/stack_integrity_latest.json").write_text(
        json.dumps({"stack_ok": True, "r3": {"mirror_api_ok": True, "surface_page_ok": True}}),
        encoding="utf-8",
    )


def test_prepare_writes_pending(tmp_path: Path) -> None:
    _seed(tmp_path)
    doc = prepare_before_reboot(tmp_path)
    assert doc.get("steps")
    assert (tmp_path / "evidence/reboot_apply_pending.json").is_file()
    assert reboot_pending(tmp_path)


def test_complete_clears_pending(tmp_path: Path) -> None:
    _seed(tmp_path)
    prepare_before_reboot(tmp_path)
    out = complete_after_reboot(tmp_path)
    assert "headline_de" in out
    assert not reboot_pending(tmp_path)
    assert (tmp_path / "evidence/reboot_apply_complete_latest.json").is_file()
