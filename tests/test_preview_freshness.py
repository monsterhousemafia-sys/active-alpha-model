"""GUI Preview dedup stamp."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.preview_freshness import (
    is_preview_fresh,
    mark_gui_preview_done,
    mark_preview_inputs_changed,
    preview_stale_status,
    should_skip_gui_preview,
)


def test_skip_when_fresh_and_passed(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    mark_gui_preview_done(tmp_path)
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"overall_pass": True, "report_de": "OK"}),
        encoding="utf-8",
    )
    skip, cached = should_skip_gui_preview(tmp_path, force=False)
    assert skip
    assert cached and cached.get("overall_pass")


def test_no_skip_when_force(tmp_path: Path) -> None:
    mark_gui_preview_done(tmp_path)
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"overall_pass": True}),
        encoding="utf-8",
    )
    skip, _ = should_skip_gui_preview(tmp_path, force=True)
    assert not skip


def test_not_fresh_without_stamp(tmp_path: Path) -> None:
    assert not is_preview_fresh(tmp_path)


def test_inputs_stale_breaks_dedup(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    mark_gui_preview_done(tmp_path)
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"overall_pass": True, "report_de": "OK"}),
        encoding="utf-8",
    )
    mark_preview_inputs_changed(tmp_path, source="trading-day")
    assert preview_stale_status(tmp_path)["stale"]
    skip, _ = should_skip_gui_preview(tmp_path, force=False)
    assert not skip
