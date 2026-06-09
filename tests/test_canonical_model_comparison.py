"""Phase C canonical model comparison tests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_canonical_comparison import (
    align_return_series,
    build_canonical_model_comparison,
    resolve_variant_returns_path,
)
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tools.build_canonical_model_comparison import main as build_main


def _seed_returns(run_dir: Path, *, offset: float = 0.0) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2020-01-01", periods=260, freq="B")
    rets = pd.Series(0.0004 + offset, index=dates)
    rets.to_frame("strategy_return").to_csv(run_dir / "strategy_daily_returns.csv")
    (run_dir / "integrity_report.json").write_text(
        json.dumps({"status": "PASS", "errors": []}),
        encoding="utf-8",
    )


def test_align_return_series_inner_join_length() -> None:
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    a = pd.Series(0.001, index=dates)
    b = pd.Series(0.002, index=dates[10:90])
    frame, meta = align_return_series({"A": a, "B": b}, min_overlap=50)
    assert meta["status"] == "OK"
    assert len(frame) == 80
    assert meta["n_aligned"] == 80


def test_aligned_calendar_recomputes_metrics(tmp_path: Path) -> None:
    root = tmp_path
    _seed_returns(root / "validation_runs" / "20260101_R3_w075_q065_noexit", offset=0.0)
    _seed_returns(root / "validation_runs" / "20260101_M1_MOM_BLEND_MATCHED_CONTROLS", offset=0.0002)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "variant_run_inventory.json").write_text(
        json.dumps({"variants": []}),
        encoding="utf-8",
    )
    doc = build_canonical_model_comparison(root)
    assert doc["alignment_mode"] == "INTERSECTION_RECOMPUTED"
    assert doc["calendar"]["n_aligned"] >= 200
    champ = next(v for v in doc["variants"] if v["variant_id"] == AUTHORITATIVE_CHAMPION)
    assert champ["metrics_mode"] == "aligned_recomputed"
    assert champ["metrics"]["n_days"] == doc["calendar"]["n_aligned"]


def test_challenger_cost_stress_never_uses_champion_turnover_proxy(tmp_path: Path) -> None:
    root = tmp_path
    g1 = root / "evidence" / "g1_independent_next_level" / "challenger" / "MOM_63_TOP12"
    g1.mkdir(parents=True)
    dates = pd.date_range("2020-01-01", periods=260, freq="B")
    pd.Series(0.0006, index=dates).to_frame("strategy_return").to_csv(g1 / "daily_returns.csv")
    (root / "model_output_sp500_pit_t212").mkdir(parents=True)
    _seed_returns(root / "model_output_sp500_pit_t212")
    (root / "model_output_sp500_pit_t212" / "backtest_decisions.csv").write_text(
        "rebalance_date,turnover\n2020-02-01,0.5\n",
        encoding="utf-8",
    )
    (root / "model_output_sp500_pit_t212" / "backtest_report.txt").write_text(
        "fee_model: trading212\n",
        encoding="utf-8",
    )
    doc = build_canonical_model_comparison(root)
    plus_25 = doc["cost_stress"]["scenarios"].get("PLUS_25_BPS", [])
    mom = next((r for r in plus_25 if r.get("variant_id") == "MOM_63_TOP12"), None)
    assert mom is not None
    assert mom.get("turnover_is_proxy") is not True
    assert "CHALLENGER_TURNOVER_PROXY_DETECTED" not in (doc.get("governance_blockers") or [])


def test_build_tool_writes_evidence(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    _seed_returns(root / "validation_runs" / "20260101_R3_w075_q065_noexit")
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "variant_run_inventory.json").write_text(
        json.dumps({"variants": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["build_canonical_model_comparison.py", "--root", str(root)],
    )
    assert build_main() == 0
    assert (root / "evidence" / "canonical_model_comparison.json").is_file()
    assert (root / "evidence" / "canonical_model_comparison.md").is_file()


def test_resolve_rejects_contaminated_archive(tmp_path: Path) -> None:
    root = tmp_path
    arch = root / "evidence" / "archive_phase_b_contaminated_model_output"
    arch.mkdir(parents=True)
    dates = pd.date_range("2017-01-01", periods=2000, freq="B")
    pd.Series(0.0001, index=dates).to_frame("strategy_return").to_csv(arch / "strategy_daily_returns.csv")
    out = root / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    contaminated = arch / "strategy_daily_returns.csv"
    (out / "strategy_daily_returns.csv").write_bytes(contaminated.read_bytes())
    path, reason = resolve_variant_returns_path(root, AUTHORITATIVE_CHAMPION)
    assert path is None
    assert "contaminated" in (reason or "") or "calendar_too_long" in (reason or "")
