from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_king_network_config() -> None:
    doc = json.loads((ROOT / "control/king_network.json").read_text(encoding="utf-8"))
    assert doc.get("schema_version") == 1
    assert len(doc.get("nodes") or []) >= 5
    assert len(doc.get("edges") or []) >= 4
    assert len(doc.get("takt_phases_de") or []) == 8


def test_sync_network_pulse_writes_evidence() -> None:
    from analytics.king_network import compute_takt, sync_network_pulse

    pulse = sync_network_pulse(ROOT, source_node="test")
    assert pulse.get("ok") is True
    assert pulse.get("beat") is not None
    assert pulse.get("phase") in {
        "sync",
        "observe",
        "execute",
        "prove",
        "decide",
        "build",
        "verify",
        "ready",
    }
    evidence = ROOT / "evidence/king_network_pulse_latest.json"
    assert evidence.is_file()
    on_disk = json.loads(evidence.read_text(encoding="utf-8"))
    assert on_disk.get("phase") == pulse.get("phase")

    takt = compute_takt(ROOT)
    assert takt.get("active_layer") in {"bash", "python", "koenig", "cursor"}
    assert takt.get("next_action_de")


def test_bridge_pending_cursor_no_crash() -> None:
    from analytics.king_network import bridge_pending_cursor

    pending, msg = bridge_pending_cursor(ROOT)
    assert isinstance(pending, bool)
    assert isinstance(msg, str)


def test_autonomous_build_policy_authoritative() -> None:
    doc = json.loads((ROOT / "control/king_32b_autonomous_build.json").read_text(encoding="utf-8"))
    assert doc.get("autonomous_build_enabled") is True
    assert doc.get("cursor_build_fallback") is False


def test_bridge_pending_routes_to_koenig_when_autonomous(tmp_path: Path) -> None:
    from analytics.king_network import compute_takt

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    policy = json.loads((ROOT / "control/king_32b_autonomous_build.json").read_text(encoding="utf-8"))
    (tmp_path / "control/king_32b_autonomous_build.json").write_text(
        json.dumps(policy, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "evidence/alpha_model_cursor_king_bridge_latest.json").write_text(
        json.dumps(
            {
                "last_king_push": {
                    "at_utc": "2026-06-08T10:00:00+00:00",
                    "request_de": "R3 Panel anpassen",
                },
                "last_cursor_push": {"at_utc": "2026-06-07T10:00:00+00:00"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    takt = compute_takt(tmp_path)
    assert takt.get("phase") == "build"
    assert takt.get("active_layer") == "koenig"
    assert takt.get("build_owner") == "koenig_32b"
