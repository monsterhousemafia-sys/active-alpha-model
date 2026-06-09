"""König-Souveränität — Puls und nächster Schritt."""
from __future__ import annotations

from pathlib import Path


def test_next_king_action_complete_without_benchmark(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path

    monkeypatch.setattr(
        "analytics.live_profile_governance.h1_backtest_status",
        lambda _root: {"status": "COMPLETE"},
    )
    monkeypatch.setattr(
        "analytics.live_profile_governance.is_h1_backtest_sealed",
        lambda _root: False,
    )
    monkeypatch.setattr(
        "analytics.h1_benchmark.benchmark_status",
        lambda _root: {"ok": True, "exists": False, "generating": False},
    )

    from analytics.king_sovereignty import next_king_action_de

    assert "/h1-benchmark" in next_king_action_de(root)


def test_sovereignty_model_mentions_vasall() -> None:
    from analytics.king_sovereignty import sovereignty_model_de

    text = sovereignty_model_de()
    assert "Vasall" in text
    assert "König" in text
