from __future__ import annotations

import json
from pathlib import Path

import active_alpha_model as aam


def test_collect_cache_status_reports_missing_caches(tmp_path: Path):
    cfg = aam.BacktestConfig(out_dir=str(tmp_path / "run"), membership_mode="off")
    lines = aam.collect_cache_status_lines(cfg, cfg.out_dir, n_tickers=0)
    text = "\n".join(lines)
    assert "Cache Status" in text
    assert "feature_cache" in text
    assert "price_cache" in text
    assert "prediction_cache" in text


def test_collect_cache_status_reads_feature_meta(tmp_path: Path):
    cfg = aam.BacktestConfig(out_dir=str(tmp_path / "run"), horizon=10, membership_mode="off")
    feat_path, ret_path, meta_path = aam._feature_cache_paths(tmp_path / "run")
    feat_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({"schema_version": aam.FEATURE_CACHE_SCHEMA_VERSION, "fingerprint": "abc", "rows": 10}),
        encoding="utf-8",
    )
    feat_path.touch()
    ret_path.touch()
    lines = aam.collect_cache_status_lines(cfg, cfg.out_dir, n_tickers=1)
    assert any("schema=2" in line or f"schema={aam.FEATURE_CACHE_SCHEMA_VERSION}" in line for line in lines)


def test_cache_status_cli_exits_zero():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "active_alpha_model.py"), "--cache-status", "--membership-mode", "off"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    assert "Cache Status" in proc.stdout


def test_robustness_skip_completed(tmp_path: Path, monkeypatch):
    import run_robustness_tests as rr

    monkeypatch.setattr(rr, "RESULTS_DIR", tmp_path / "results")
    done_dir = rr.variant_output_dir("variant_a")
    done_dir.mkdir(parents=True)
    (done_dir / "backtest_report.txt").write_text(
        "Strategy metrics\n  total_return: 0.10\nBenchmark metrics\n",
        encoding="utf-8",
    )
    variants = [{"name": "variant_a"}, {"name": "variant_b"}]
    pending, skipped = rr.partition_variants(variants, skip_completed=True)
    assert len(skipped) == 1
    assert skipped[0]["name"] == "variant_a"
    assert [v["name"] for v in pending] == ["variant_b"]

    pending_all, skipped_none = rr.partition_variants(variants, skip_completed=False)
    assert len(pending_all) == 2
    assert skipped_none == []
