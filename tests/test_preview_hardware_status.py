from __future__ import annotations

from pathlib import Path

from analytics.preview_hardware_status import build_preview_hardware_status


def test_hardware_status_shape(tmp_path: Path) -> None:
    doc = build_preview_hardware_status(tmp_path)
    assert "score" in doc
    assert "cpu" in doc
    assert "recommendations_de" in doc
    assert doc["cpu"]["logical"] >= 1
