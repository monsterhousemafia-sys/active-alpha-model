"""Tests for EXE build hash ledger and verification."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_write_and_verify_hash_sidecar(tmp_path: Path) -> None:
    from aa_build_integrity import read_recorded_hash, sha256_file, verify_exe_hash_consistency, write_hash_sidecar

    exe = tmp_path / "Marktanalyse.exe"
    exe.write_bytes(b"test-exe-payload")
    digest = write_hash_sidecar(exe, root=tmp_path)
    assert digest == sha256_file(exe)
    assert read_recorded_hash(tmp_path) == digest
    assert verify_exe_hash_consistency(root=tmp_path)["ok"] is True


def test_verify_fails_on_mismatch(tmp_path: Path) -> None:
    from aa_build_integrity import verify_exe_hash_consistency, write_hash_sidecar

    exe = tmp_path / "Marktanalyse.exe"
    exe.write_bytes(b"v1")
    write_hash_sidecar(exe, root=tmp_path)
    exe.write_bytes(b"v2")
    result = verify_exe_hash_consistency(root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "hash_mismatch"


def test_load_pilot_gap_targets_from_json(tmp_path: Path) -> None:
    from market.live_quote_engine import load_pilot_gap_targets

    cfg_dir = tmp_path / "paper" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "pilot_gap_targets_eur.json").write_text(
        '{"targets_eur": {"OXY": 100.0, "WDC": 50.0}}',
        encoding="utf-8",
    )
    targets = load_pilot_gap_targets(tmp_path)
    assert targets["OXY"] == 100.0
    assert targets["WDC"] == 50.0


def test_high_contrast_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from ui.interactive_cockpit.cockpit_theme import high_contrast_requested

    monkeypatch.setenv("AA_HIGH_CONTRAST", "1")
    assert high_contrast_requested() is True


def test_learning_eod_catchup_headless(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AA_LEARNING_CAPTURE", "1")
    from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout
    from market.learning_pipeline import ensure_learning_policy

    ensure_marktanalyse_runtime_layout(tmp_path)
    ensure_learning_policy(tmp_path)
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "tools/run_learning_eod_catchup.py"),
            "--root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert proc.returncode in (0, 1)
    assert (tmp_path / "evidence" / "learning_eod_catchup_latest.json").is_file()
