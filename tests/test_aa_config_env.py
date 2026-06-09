"""Tests for read-only AA config loading without batch subprocess."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _write_settings(tmp_path: Path, content: str) -> None:
    (tmp_path / "active_alpha_settings.bat").write_text(content, encoding="utf-8")


def _write_user(tmp_path: Path, content: str) -> None:
    (tmp_path / "active_alpha_user_config.bat").write_text(content, encoding="utf-8")


def test_parse_reads_settings_values(tmp_path: Path) -> None:
    from aa_config_env import parse_aa_env_files

    _write_settings(
        tmp_path,
        "\n".join(
            [
                "@echo off",
                "rem comment",
                'set "AA_BENCHMARK=SPY"',
                'set "AA_BACKTEST_OUT_DIR=model_output_test"',
                'set "AA_PAPER_DIR=paper_output"',
                "set AA_N_JOBS=auto",
            ]
        ),
    )
    env = parse_aa_env_files(tmp_path)
    assert env["AA_BENCHMARK"] == "SPY"
    assert env["AA_BACKTEST_OUT_DIR"] == "model_output_test"
    assert env["AA_PAPER_DIR"] == "paper_output"
    assert env["AA_N_JOBS"] == "auto"


def test_user_config_overrides_settings(tmp_path: Path) -> None:
    from aa_config_env import parse_aa_env_files

    _write_settings(tmp_path, 'set "AA_PAPER_CAPITAL=100"\nset "AA_BENCHMARK=SPY"\n')
    _write_user(tmp_path, 'set "AA_PAPER_CAPITAL=500"\n')
    env = parse_aa_env_files(tmp_path)
    assert env["AA_PAPER_CAPITAL"] == "500"
    assert env["AA_BENCHMARK"] == "SPY"


def test_comments_and_non_aa_keys_ignored(tmp_path: Path) -> None:
    from aa_config_env import parse_aa_env_files

    _write_settings(
        tmp_path,
        "\n".join(
            [
                "rem ignored",
                ":: also ignored",
                'set "OTHER=1"',
                'set "AA_BENCHMARK=QQQ"',
            ]
        ),
    )
    env = parse_aa_env_files(tmp_path)
    assert "OTHER" not in env
    assert env["AA_BENCHMARK"] == "QQQ"


def test_load_aa_env_does_not_spawn_subprocess(tmp_path: Path) -> None:
    from aa_config_env import load_aa_env

    _write_settings(
        tmp_path,
        "\n".join(
            [
                'set "AA_BACKTEST_OUT_DIR=out_test"',
                'set "AA_PAPER_DIR=paper_output"',
                'set "AA_BENCHMARK=SPY"',
            ]
        ),
    )
    with mock.patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run must not be called")):
        with mock.patch(
            "aa_dashboard_qt.run_subprocess_with_ui",
            side_effect=AssertionError("run_subprocess_with_ui must not be called"),
        ):
            env = load_aa_env(tmp_path)
    assert env["AA_BENCHMARK"] == "SPY"


def test_forbidden_batch_command_raises(tmp_path: Path) -> None:
    from aa_config_env import ConfigEnvError, parse_aa_env_files

    _write_settings(tmp_path, 'call "evil.bat"\n')
    with pytest.raises(ConfigEnvError):
        parse_aa_env_files(tmp_path)


def test_corrupted_out_dir_fail_closed(tmp_path: Path) -> None:
    from aa_config_env import ConfigEnvError, load_aa_env

    _write_settings(
        tmp_path,
        "\n".join(
            [
                'set "AA_BACKTEST_OUT_DIR=T_DIR"',
                'set "AA_PAPER_DIR=paper_output"',
            ]
        ),
    )
    with pytest.raises(ConfigEnvError):
        load_aa_env(tmp_path)


def test_missing_required_paper_dir_fail_closed(tmp_path: Path) -> None:
    from aa_config_env import ConfigEnvError, load_aa_env

    _write_settings(tmp_path, 'set "AA_BACKTEST_OUT_DIR=model_output"\n')
    with pytest.raises(ConfigEnvError):
        load_aa_env(tmp_path)


def test_load_aa_env_completes_within_bounded_time() -> None:
    from aa_config_env import load_aa_env

    start = time.monotonic()
    env = load_aa_env(ROOT)
    elapsed = time.monotonic() - start
    assert isinstance(env, dict)
    assert elapsed < 5.0
    assert env.get("AA_BACKTEST_OUT_DIR")
