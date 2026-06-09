from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_write_naive_benchmark_progress(tmp_path: Path) -> None:
    from aa_backtest import _write_naive_benchmark_progress

    path = tmp_path / "progress.json"
    _write_naive_benchmark_progress(
        str(path),
        variant="mom_1_top12",
        phase="prep",
        progress_pct=12,
        prep_done=100,
        prep_total=1866,
    )
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["phase"] == "prep"
    assert doc["progress_pct"] == 12
    assert doc["prep_done"] == 100


def test_record_benchmark_lessons() -> None:
    from analytics.h1_benchmark_lessons import record_benchmark_lessons

    doc = record_benchmark_lessons(ROOT, trigger_de="test")
    assert doc.get("ok") is True
    assert len(doc.get("lessons_de") or []) >= 3
    evidence = ROOT / "evidence/h1_benchmark_lessons_latest.json"
    assert evidence.is_file()


def test_start_benchmark_progress_schema() -> None:
    """Background-Start schreibt ab jetzt phase=starting (Code-Review)."""
    from analytics.h1_benchmark import _PROGRESS_REL, BENCHMARK_VARIANT

    text = (ROOT / "analytics/h1_benchmark.py").read_text(encoding="utf-8")
    assert "phase" in text and "starting" in text
    assert str(_PROGRESS_REL).replace("\\", "/") in text
    assert BENCHMARK_VARIANT == "mom_1_top12"
