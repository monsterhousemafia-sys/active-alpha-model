"""T212 sync coordinator — coalesce + single owner."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.r3_t212_sync_coordinator import (
    record_t212_sync,
    resolve_t212_sync_force,
    should_coalesce_t212_sync,
)


def _write_policy(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_t212_sync_policy.json").write_text(
        json.dumps(
            {
                "canonical_owner": "prognosis_pipeline",
                "min_coalesce_interval_s": 120,
                "prognosis_first": True,
            }
        ),
        encoding="utf-8",
    )


def test_non_owner_coalesces_after_recent_sync(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    record_t212_sync(tmp_path, owner="prognosis_pipeline", ok=True)
    skip, reason = should_coalesce_t212_sync(tmp_path, owner="background_engine", force=False)
    assert skip is True
    assert "Cache" in reason or "prognosis" in reason


def test_canonical_owner_respects_coalesce_window(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    record_t212_sync(tmp_path, owner="prognosis_pipeline", ok=True)
    skip, _ = should_coalesce_t212_sync(tmp_path, owner="prognosis_pipeline", force=False)
    assert skip is True
    assert resolve_t212_sync_force(tmp_path, owner="prognosis_pipeline", force=False) is False


def test_force_sync_allowed_for_canonical_owner(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    record_t212_sync(tmp_path, owner="prognosis_pipeline", ok=True)
    assert resolve_t212_sync_force(tmp_path, owner="prognosis_pipeline", force=True) is True
    skip, _ = should_coalesce_t212_sync(tmp_path, owner="prognosis_pipeline", force=True)
    assert skip is False


def test_stale_sync_allows_non_owner(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_t212_sync_coordinator_state.json").write_text(
        json.dumps({"last_sync_utc": old, "last_sync_ok": True, "last_owner": "prognosis_pipeline"}),
        encoding="utf-8",
    )
    skip, _ = should_coalesce_t212_sync(tmp_path, owner="king_plan", force=False)
    assert skip is False
