"""R3 Hardware↔Software-Bond — Resolver und Stack-Anbindung."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_hw_software_bond import resolve_r3_runtime_tuning, sync_r3_hw_software_bond


def _write_profile(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_runtime_profile.json").write_text(
        json.dumps(
            {
                "profile_id": "fluid_v3",
                "mirror_poll_ms": 15000,
                "mirror_soft_update": True,
                "cache_stale_sec": 120,
                "mirror_reload_on_evidence_change": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_os_supremacy.json").write_text(
        json.dumps({"session": {"startup_delay_sec": 8}}),
        encoding="utf-8",
    )


def test_resolve_returns_mirror_and_cache(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    doc = resolve_r3_runtime_tuning(tmp_path)
    assert doc["mirror"]["mirror_poll_ms"] >= 12_000
    assert doc["cache"]["cache_stale_sec"] >= 60
    assert doc["startup"]["startup_delay_sec"] >= 3
    assert doc["pressure_class"] in ("fast", "balanced", "constrained")


def test_constrained_increases_poll_and_disables_live_prep(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    with patch(
        "analytics.r3_hw_software_bond._host_snapshot",
        return_value={
            "preview": {"mem_available_gb": 4.0, "load_per_cpu": 0.2, "h1": {}},
            "host": {"ram_gb": 60, "logical_cores": 16},
            "policy_headline_de": "test",
            "host_profile_de": "test",
        },
    ):
        doc = resolve_r3_runtime_tuning(tmp_path)
    assert doc["pressure_class"] == "constrained"
    assert doc["mirror"]["mirror_poll_ms"] > 15_000
    assert doc["cache"]["warm_live_prep"] is False


def test_sync_persists_evidence(tmp_path: Path) -> None:
    _write_profile(tmp_path)
    doc = sync_r3_hw_software_bond(tmp_path, persist=True)
    path = tmp_path / "evidence/r3_hw_software_bond_latest.json"
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk.get("pressure_class") == doc.get("pressure_class")
