"""Linux runtime harmonization — v2 vs legacy gates."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.linux_runtime_unified import (
    control_plane_mode,
    kernel_is_authoritative,
    kernel_supremacy_status,
    runtime_profile,
    sync_operator_timer_catalog,
)


def test_sync_operator_timer_catalog_writes(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    doc = sync_operator_timer_catalog(tmp_path)
    assert doc.get("timers")
    path = tmp_path / "control/linux_operator_timers.json"
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved.get("source") == "linux_runtime_unified"


def test_runtime_profile_legacy(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/linux_runtime_unified.json").write_text(
        json.dumps({"control_plane": "cognitive_kernel_v2"}),
        encoding="utf-8",
    )
    prof = runtime_profile(tmp_path)
    assert prof.get("control_plane") in ("legacy", "v2", "hybrid")
    assert "headline_de" in prof


def test_kernel_supremacy_when_succession_ack(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/cognitive_kernel_manifest.json").write_text(
        json.dumps({"kernel_generation": 2}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/kernel_succession_operator_ack.json").write_text(
        json.dumps({"ok": True}),
        encoding="utf-8",
    )
    assert kernel_is_authoritative(tmp_path)
    sup = kernel_supremacy_status(tmp_path)
    assert sup.get("authoritative") is True
    assert "einzig" in str(sup.get("supremacy_de", "")).lower() or "Cognitive" in str(sup.get("supremacy_de", ""))


def test_control_plane_v2_when_decommissioned(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/old_stack_decommission_latest.json").write_text(
        json.dumps({"masked_services": ["active-alpha-preview-hub.service"], "disabled_timers": []}),
        encoding="utf-8",
    )
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/cognitive_kernel_manifest.json").write_text(
        json.dumps({"kernel_generation": 2}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/kernel_succession_operator_ack.json").write_text(
        json.dumps({"ok": True}),
        encoding="utf-8",
    )
    assert control_plane_mode(tmp_path) == "v2"
