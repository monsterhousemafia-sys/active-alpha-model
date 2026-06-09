"""P3 background research gate tests (master prompt §12.5)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_background_research import (
    build_background_research_status,
    format_background_research_report,
    run_background_research,
    write_background_research_status,
)
from aa_challenger_eval import evaluate_promotion_gate


def _seed_run(run_dir: Path, *, integrity: str = "PASS") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2020-01-01", periods=260, freq="B")
    pd.Series(0.0005, index=dates).to_frame("strategy_return").to_csv(run_dir / "strategy_daily_returns.csv")
    (run_dir / "integrity_report.json").write_text(
        json.dumps({"status": integrity, "errors": [] if integrity == "PASS" else ["fail"]}),
        encoding="utf-8",
    )


def test_p3_integrity_fail_not_shown_as_candidate(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    (out / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": "R3_w075_q065_noexit", "integrity_status": "PASS", "run_id": "good"}),
        encoding="utf-8",
    )
    _seed_run(root / "validation_runs" / "x_R0_LEGACY_ENSEMBLE", integrity="INVALID")
    _seed_run(root / "validation_runs" / "y_R3_w075_q065_noexit")
    _seed_run(root / "validation_runs" / "z_M1_MOM_BLEND_MATCHED_CONTROLS")
    status = build_background_research_status(root, out)
    r0 = next(e for e in status["entries"] if e["variant_id"] == "R0_LEGACY_ENSEMBLE")
    assert r0["status"] == "FAIL"
    assert r0["is_research_candidate"] is False


def test_p3_pass_shows_research_candidate(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    (out / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": "R3_w075_q065_noexit", "integrity_status": "PASS"}),
        encoding="utf-8",
    )
    _seed_run(root / "validation_runs" / "a_R0_LEGACY_ENSEMBLE")
    champ = root / "validation_runs" / "b_R3_w075_q065_noexit"
    _seed_run(champ)
    rets = pd.read_csv(champ / "strategy_daily_returns.csv", index_col=0, parse_dates=True)
    (rets * 2.0).to_csv(champ / "strategy_daily_returns.csv")
    m1 = root / "validation_runs" / "c_M1_MOM_BLEND_MATCHED_CONTROLS"
    _seed_run(m1)
    (m1 / "backtest_report.txt").write_text(
        "vs_NAIVE_MOMENTUM_MOM_63_TOP12.sharpe_0rf: p05=0.5, p50=1.0, p95=1.5\n",
        encoding="utf-8",
    )
    status = build_background_research_status(root, out)
    r0 = next(e for e in status["entries"] if e["variant_id"] == "R0_LEGACY_ENSEMBLE")
    assert r0["status"] == "PASS"
    assert r0["is_research_candidate"] is True
    assert status["research_status"] == "PASS"
    text = format_background_research_report(status)
    assert "CANDIDATE" in text or "Best research candidate" in text


def test_p3_no_promotion(tmp_path: Path) -> None:
    gate = evaluate_promotion_gate(
        champion={"integrity_pass": True, "metrics": {"sharpe_0rf": 0.5}, "n_days": 300},
        m1={"metrics": {"sharpe_0rf": 2.0}},
    )
    assert gate["status"] == "BLOCKED"


def test_p3_failed_research_does_not_change_pointer(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    pointer = {"integrity_status": "PASS", "run_id": "good", "variant_id": "R3_w075_q065_noexit"}
    (out / "latest_validated_run.json").write_text(json.dumps(pointer), encoding="utf-8")
    status = build_background_research_status(root, out)
    write_background_research_status(root, out, status)
    after = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert after["run_id"] == "good"


def test_p3_run_background_research_writes_status(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    out.mkdir()
    (out / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    _seed_run(root / "validation_runs" / "x_R3_w075_q065_noexit")
    summary = run_background_research(root, out, use_lock=False)
    assert summary["status"] == "OK"
    assert (out / "background_research_status.json").is_file()
    assert (root / "control" / "background_research_status.json").is_file()
