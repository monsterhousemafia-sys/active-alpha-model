"""R3 Crash-Guard — absturzsichere Spiegel-Pfade."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_crash_guard import (
    clamp_wait_sec,
    empty_mirror_state,
    render_mirror_fallback_page,
    safe_float,
)
from analytics.r3_exec_mirror import build_exec_mirror_state, render_r3_exec_mirror_page


def test_clamp_wait_sec_bounds() -> None:
    assert clamp_wait_sec(1) == 5.0
    assert clamp_wait_sec(999) == 120.0
    assert clamp_wait_sec("45") == 45.0


def test_safe_float_nan_and_garbage() -> None:
    assert safe_float("x", default=3.0) == 3.0
    assert safe_float(float("nan"), default=1.0) == 1.0


def test_build_state_survives_corrupt_evidence(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text("{not json", encoding="utf-8")
    doc = build_exec_mirror_state(tmp_path)
    assert doc.get("schema_version") == 2
    assert doc.get("package_ready") is False


def test_render_mirror_fallback_page() -> None:
    body = render_mirror_fallback_page("test", port=17890)
    assert b"R3" in body
    assert "geschützt".encode("utf-8") in body
    assert b"17890" in body


def test_render_page_never_raises(tmp_path: Path) -> None:
    body = render_r3_exec_mirror_page(tmp_path)
    assert isinstance(body, bytes)
    assert len(body) > 100


def test_empty_mirror_state_shape() -> None:
    doc = empty_mirror_state(detail_de="x")
    assert doc["model_output"]["allocations"] == []
    assert doc["error_de"] == "x"
