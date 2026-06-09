"""Qualitäts-Scores 10/10."""
from __future__ import annotations

from pathlib import Path

from analytics.r3_quality_scores import evaluate_quality_scores


def test_quality_scores_dimensions() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = evaluate_quality_scores(root)
    dims = doc.get("dimensions") or []
    assert len(dims) >= 4
    assert doc.get("average_10") is not None
    for d in dims:
        assert 0 <= int(d.get("score_10") or 0) <= 10
