from __future__ import annotations

import json
from pathlib import Path

from analytics.linux_operator_scope import (
    level_allowed,
    level_autonomous,
    load_operator_scope,
    scope_summary_de,
)


def test_levels_a_through_d_approved(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/linux_operator_scope.json").write_text(
        json.dumps(
            {
                "approved_levels": ["A", "B", "C", "D"],
                "max_level": "D",
                "levels": {
                    "A": {"label_de": "App", "autonomous": True},
                    "D": {"label_de": "System", "autonomous": False},
                },
            }
        ),
        encoding="utf-8",
    )
    assert level_allowed(tmp_path, "A")
    assert level_allowed(tmp_path, "D")
    assert level_autonomous(tmp_path, "A")
    assert not level_autonomous(tmp_path, "D")
    summary = scope_summary_de(tmp_path)
    assert "A" in "".join(summary["summary_lines_de"])


def test_default_scope_file_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_operator_scope(root)
    assert "D" in (cfg.get("approved_levels") or [])
