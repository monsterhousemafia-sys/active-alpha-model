from __future__ import annotations

import json
from pathlib import Path

from analytics.active_alpha_identity import load_unified_config, product_name, unified_intro_de, window_title


def test_unified_config(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/active_alpha_unified.json").write_text(
        json.dumps({"product_name": "Alpha Model", "window_title": "Test Title"}),
        encoding="utf-8",
    )
    assert window_title(tmp_path) == "Test Title"
    assert product_name(tmp_path) == "Alpha Model"
    intro = unified_intro_de(tmp_path)
    assert "Alpha Model" in intro


def test_project_defaults_alpha_model() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_unified_config(root)
    assert cfg.get("product_name") == "Alpha Model"
    assert window_title(root) == "Alpha Model"
