"""Tests for Marktanalyse runtime bootstrap."""
from __future__ import annotations

from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout


def test_ensure_runtime_layout_seeds_summary(tmp_path):
    root = ensure_marktanalyse_runtime_layout(tmp_path)
    summary = root / "paper/p16f/p16f_desktop_runtime_summary.json"
    assert summary.is_file()
    marker = root / "control/marktanalyse_runtime_layout.json"
    assert marker.is_file()
