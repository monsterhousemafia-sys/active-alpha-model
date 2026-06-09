"""R3 Bau-Mandate — König 32B effizienter Pfad."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_build_mandate import (
    build_mandate_context_block,
    build_r3_local_mandate,
    notify_king_build_handoff,
)
from tests.r3_order_fixtures import seed_orders_stack


def _seed(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "control/r3_runtime_profile.json").write_text(
        json.dumps({"profile_id": "stable_v1", "label_de": "Stabil"}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_runtime_upgrade_catalog.json").write_text(
        json.dumps(
            {
                "upgrades": [
                    {
                        "id": "fluid_mirror_v2",
                        "label_de": "Flüssig",
                        "replaces_profile_id": "stable_v1",
                        "target_profile": {"profile_id": "fluid_v2"},
                        "changes_de": ["A"],
                        "detection": {"requires_mirror_state_ok": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"bonded": True, "connected": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_freigabe_latest.json").write_text(
        json.dumps({"updated_at_utc": "2026-06-08T12:00:00+00:00"}),
        encoding="utf-8",
    )


def test_build_r3_local_mandate_has_steps(tmp_path: Path) -> None:
    _seed(tmp_path)
    doc = build_r3_local_mandate(tmp_path)
    assert doc.get("mandate_de")
    assert len(doc.get("steps_de") or []) >= 4
    assert "r3_sync" in str(doc.get("post_build_de"))
    assert (tmp_path / "evidence/r3_local_build_mandate_latest.json").is_file()


def test_mandate_context_block_for_r3_topic(tmp_path: Path) -> None:
    _seed(tmp_path)
    build_r3_local_mandate(tmp_path)
    block = build_mandate_context_block(tmp_path, "R3 Lokal abstimmen")
    assert "R3 LOKAL-BAU" in block
    assert "pytest" in block


def test_notify_king_build_handoff(tmp_path: Path) -> None:
    _seed(tmp_path)
    doc = build_r3_local_mandate(tmp_path)
    out = notify_king_build_handoff(tmp_path, doc)
    assert out.get("ok") is True
    bridge = json.loads(
        (tmp_path / "evidence/alpha_model_cursor_king_bridge_latest.json").read_text(encoding="utf-8")
    )
    assert bridge.get("last_cursor_push", {}).get("source") == "r3_build_mandate"
