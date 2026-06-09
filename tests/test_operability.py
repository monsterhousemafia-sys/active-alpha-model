from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import active_alpha_model as aam


def test_shared_cache_dir_uses_fingerprint_subdir(tmp_path: Path):
    cfg = aam.BacktestConfig(out_dir=str(tmp_path / "variant_a"), shared_cache_dir=str(tmp_path / "shared"), horizon=10)
    feat_dir = aam.resolve_feature_cache_dir(cfg, 500)
    assert feat_dir == tmp_path / "shared" / "features" / f"fp_{aam._feature_build_fingerprint(cfg, 500)}"
    price_dir = aam.resolve_price_cache_dir(cfg)
    assert price_dir == tmp_path / "shared" / "price"


def test_without_shared_cache_uses_out_dir(tmp_path: Path):
    cfg = aam.BacktestConfig(out_dir=str(tmp_path / "run"), horizon=21)
    assert aam.resolve_feature_cache_dir(cfg, 100) == tmp_path / "run"
    assert aam.resolve_price_cache_dir(cfg) == tmp_path / "run" / "price_cache"
    assert not aam.using_shared_cache_dir(cfg)


def test_dry_run_exits_zero():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "active_alpha_model.py"), "--dry-run", "--mode", "backtest", "--membership-mode", "off"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    assert "Dry Run" in proc.stdout
    assert "planned phases" in proc.stdout


def test_robustness_dry_run_lists_shared_cache():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "run_robustness_tests.py"), "--dry-run", "--max-variants", "1"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    assert "shared_cache_dir:" in proc.stdout
    assert "--shared-cache-dir" in proc.stdout
