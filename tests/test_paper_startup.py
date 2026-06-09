from __future__ import annotations

from pathlib import Path

import pandas as pd

from aa_paper_startup import is_rebalance_due, mark_recorded_today


def test_mark_recorded_today_true_for_mark_row(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper_output"
    paper_dir.mkdir()
    pd.DataFrame(
        [
            {"date": "2026-05-29", "mode": "rebalance", "total_equity": 400.0},
            {"date": "2026-05-30", "mode": "mark", "total_equity": 401.0},
        ]
    ).to_csv(paper_dir / "paper_equity.csv", index=False)
    assert mark_recorded_today(paper_dir, today="2026-05-30") is True


def test_mark_recorded_today_false_when_missing(tmp_path: Path) -> None:
    paper_dir = tmp_path / "paper_output"
    paper_dir.mkdir()
    pd.DataFrame([{"date": "2026-05-29", "mode": "mark", "total_equity": 400.0}]).to_csv(
        paper_dir / "paper_equity.csv", index=False
    )
    assert mark_recorded_today(paper_dir, today="2026-05-30") is False


def test_is_rebalance_due() -> None:
    assert is_rebalance_due({"is_due": True, "recommendation": "REBALANCE_DUE"}) is True
    assert is_rebalance_due({"is_due": False, "recommendation": "MARK_TO_MARKET_ONLY"}) is False
    assert is_rebalance_due({"is_due": False, "recommendation": "REBALANCE_DUE_NO_HISTORY"}) is True


def test_parse_aa_env_files_reads_paper_settings(tmp_path: Path) -> None:
    from aa_config_env import parse_aa_env_files

    (tmp_path / "active_alpha_settings.bat").write_text(
        'set "AA_PAPER_DIR=paper_output"\nset "AA_PAPER_CAPITAL=400"\n',
        encoding="utf-8",
    )
    (tmp_path / "active_alpha_user_config.bat").write_text(
        'set "AA_PAPER_CAPITAL=500"\n',
        encoding="utf-8",
    )
    env = parse_aa_env_files(tmp_path)
    assert env["AA_PAPER_DIR"] == "paper_output"
    assert env["AA_PAPER_CAPITAL"] == "500"
