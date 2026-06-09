"""R3 Laufzeit-Upgrades — Vorschlag, Erklärung, Bestätigung."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_exec_mirror import build_exec_mirror_state, render_r3_exec_mirror_page
from analytics.r3_runtime_upgrade import (
    align_r3_surface,
    confirm_runtime_upgrade,
    dismiss_runtime_upgrade,
    load_runtime_profile,
    scan_runtime_upgrades,
)
from tests.r3_order_fixtures import seed_orders_stack


def _seed_upgrade_stack(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_runtime_profile.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "stable_v1",
                "label_de": "Stabil — Standard",
                "mirror_poll_ms": 45000,
                "mirror_prep_every_n_polls": 4,
                "mirror_reload_on_evidence_change": True,
                "mirror_soft_update": False,
                "cache_stale_sec": 300,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_runtime_upgrade_catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "upgrades": [
                    {
                        "id": "fluid_mirror_v2",
                        "label_de": "Flüssigerer R3-Spiegel",
                        "summary_de": "Sanfteres Update.",
                        "replaces_profile_id": "stable_v1",
                        "target_profile": {
                            "profile_id": "fluid_v2",
                            "label_de": "Flüssig",
                            "mirror_poll_ms": 60000,
                            "mirror_prep_every_n_polls": 6,
                            "mirror_reload_on_evidence_change": False,
                            "mirror_soft_update": True,
                            "cache_stale_sec": 240,
                        },
                        "changes_de": ["Poll 60 s", "Soft-Update"],
                        "detection": {"requires_mirror_state_ok": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"bonded": True, "connected": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_freigabe_latest.json").write_text(
        json.dumps({"updated_at_utc": "2026-06-08T12:00:00+00:00", "prep_steps": []}),
        encoding="utf-8",
    )


def test_scan_proposes_upgrade_with_explanation(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    doc = scan_runtime_upgrades(tmp_path, persist=True)
    pending = doc.get("pending") or {}
    assert pending.get("proposal_id") == "fluid_mirror_v2"
    assert pending.get("status") == "awaiting_confirmation"
    assert "Sanfteres Update" in str(pending.get("summary_de"))
    assert len(pending.get("changes_de") or []) >= 1


def test_confirm_applies_profile_only_after_operator(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    scan_runtime_upgrades(tmp_path, persist=True)
    before = load_runtime_profile(tmp_path)
    assert before.get("profile_id") == "stable_v1"

    out = confirm_runtime_upgrade(tmp_path, proposal_id="fluid_mirror_v2")
    assert out.get("ok") is True
    after = load_runtime_profile(tmp_path)
    assert after.get("profile_id") == "fluid_v2"
    assert after.get("mirror_soft_update") is True
    assert after.get("mirror_poll_ms") == 60000

    doc = scan_runtime_upgrades(tmp_path, persist=True)
    assert doc.get("pending") is None


def test_dismiss_hides_proposal(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    scan_runtime_upgrades(tmp_path, persist=True)
    out = dismiss_runtime_upgrade(tmp_path, proposal_id="fluid_mirror_v2")
    assert out.get("ok") is True
    doc = scan_runtime_upgrades(tmp_path, persist=True)
    assert doc.get("pending") is None
    assert "fluid_mirror_v2" in (doc.get("dismissed_ids") or [])


def test_mirror_page_shows_upgrade_banner(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    scan_runtime_upgrades(tmp_path, persist=True)
    html = render_r3_exec_mirror_page(tmp_path).decode("utf-8")
    assert "r3-upgrade-banner" in html
    assert "Flüssigerer R3-Spiegel" in html
    assert "Ja</button>" in html
    assert "Nein</button>" in html


def test_align_r3_surface_warms_and_scans(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    doc = align_r3_surface(tmp_path, warm_cache=True, scan_upgrades=True, persist=True)
    assert doc.get("ok") is True
    assert any(s.get("step") == "warm_cache" and s.get("ok") for s in doc.get("steps") or [])
    assert doc.get("upgrade_pending") is True
    assert doc.get("hub_url", "").endswith("/r3") or "17890" in doc.get("hub_url", "")


def test_scan_respects_cooldown(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    first = scan_runtime_upgrades(tmp_path, persist=True, force=True)
    second = scan_runtime_upgrades(tmp_path, persist=True, force=False)
    assert first.get("pending")
    assert second.get("pending") == first.get("pending")


def test_mirror_state_fast_without_recursion(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    scan_runtime_upgrades(tmp_path, persist=True, force=True)
    import time

    t0 = time.monotonic()
    state = build_exec_mirror_state(tmp_path, refresh_scans=False)
    elapsed = time.monotonic() - t0
    assert state.get("schema_version")
    assert elapsed < 2.0


def test_mirror_state_includes_runtime_profile(tmp_path: Path) -> None:
    _seed_upgrade_stack(tmp_path)
    state = build_exec_mirror_state(tmp_path)
    assert state.get("runtime_profile", {}).get("profile_id") == "stable_v1"
    assert "runtime_upgrade" in state
