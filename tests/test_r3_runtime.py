from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.r3_runtime import (
    build_health_report,
    default_surface_path,
    launch_cockpit,
)


def test_default_surface_path_fallback(tmp_path: Path) -> None:
    assert default_surface_path(tmp_path) == "/r3"


@patch("analytics.r3_runtime.is_healthy", return_value=False)
@patch("analytics.stack_integrity.ensure_hub_reliable", side_effect=RuntimeError("hub down"))
def test_launch_cockpit_requires_hub(_ensure, _healthy, tmp_path: Path) -> None:
    doc = launch_cockpit(tmp_path, require_hub=True)
    assert doc.get("ok") is False
    assert "Hub" in str(doc.get("error_de") or "")


def test_build_health_report_layers(tmp_path: Path) -> None:
    rep = build_health_report(tmp_path, port=1)
    assert rep.get("layer") == "r3"
    assert "hub_online" in rep
    assert "cockpit_running" in rep
