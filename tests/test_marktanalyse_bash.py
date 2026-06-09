from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = (
    "tools/marktanalyse_bash.sh",
    "tools/marktanalyse_common.sh",
    "run_marktanalyse_bash.sh",
)


@pytest.mark.parametrize("rel", SCRIPTS)
def test_marktanalyse_scripts_executable(rel: str) -> None:
    path = ROOT / rel
    assert path.is_file()
    assert path.stat().st_mode & stat.S_IXUSR


def test_marktanalyse_bash_help() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/marktanalyse_bash.sh"), "help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0
    assert "marktanalyse_bash.sh" in proc.stdout
    assert "preflight" in proc.stdout


def test_marktanalyse_view_picks(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps(
            {
                "ok": True,
                "profile_used": "daily_alpha_h1",
                "signal_date": "2026-06-05",
                "top_picks": [{"ticker": "INTC", "target_weight": 0.12}],
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "tools/marktanalyse_bash_view.py"),
            "picks",
            "--root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0
    assert "INTC" in proc.stdout


def test_king_ops_marktanalyse_alias() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/king_ops.sh"), "ma", "help"],
        cwd=str(ROOT),
        env={**os.environ, "AA_PROJECT_ROOT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0
    assert "Bash-Cockpit" in proc.stdout


def test_marktanalyse_status_writes_evidence() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/marktanalyse_bash.sh"), "status"],
        cwd=str(ROOT),
        env={**os.environ, "AA_PROJECT_ROOT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode in (0, 1)
    evidence = ROOT / "evidence/marktanalyse_bash_latest.json"
    assert evidence.is_file()
    doc = json.loads(evidence.read_text(encoding="utf-8"))
    assert doc.get("schema_version") == 1
    assert "product" in doc
