from __future__ import annotations

from pathlib import Path

from analytics.aa_lean_linux import lean_status


def test_lean_status(tmp_path: Path) -> None:
    doc = lean_status(tmp_path)
    assert "lean_active" in doc
    assert "keep_timers" in doc
