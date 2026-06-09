from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

KING_SCRIPTS = (
    "tools/king_common.sh",
    "tools/king_safe.sh",
    "tools/king_status.sh",
    "tools/king_h1_seal.sh",
    "tools/king_clean.sh",
    "tools/king_verify.sh",
    "tools/king_tune.sh",
    "tools/king_ops.sh",
    "tools/marktanalyse_bash.sh",
    "tools/marktanalyse_common.sh",
    "run_marktanalyse_bash.sh",
)


@pytest.mark.parametrize("rel", KING_SCRIPTS)
def test_king_scripts_exist_and_executable(rel: str) -> None:
    path = ROOT / rel
    assert path.is_file()
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR


def test_king_ops_help() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/king_ops.sh"), "help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0
    assert "king_ops.sh" in proc.stdout
    assert "h1-seal" in proc.stdout
    assert "network" in proc.stdout


def test_king_bash_manifest_layers() -> None:
    import json

    doc = json.loads((ROOT / "control/king_bash_manifest.json").read_text(encoding="utf-8"))
    assert doc.get("schema_version") == 3
    assert doc.get("layer") == "bash"
    assert "layers_de" in doc
    assert "reinforcement_loop_de" in doc
    assert doc.get("matrix_ref") == "control/king_responsibility_matrix_de.md"


def test_king_status_writes_evidence() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/king_status.sh")],
        cwd=str(ROOT),
        env={**os.environ, "AA_PROJECT_ROOT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0
    evidence = ROOT / "evidence/king_status_latest.json"
    assert evidence.is_file()
    text = evidence.read_text(encoding="utf-8")
    assert "h1_status" in text
    assert "next_layer" in text
    assert "matrix_ref" in text
    assert "gpu_returns_enabled" in text or "benchmark_over_eta" in text
    assert "COMPLETE" in text or "UNKNOWN" in text or "RUNNING" in text


def test_king_h1_seal_check_only() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/king_h1_seal.sh"), "--check-only"],
        cwd=str(ROOT),
        env={**os.environ, "AA_PROJECT_ROOT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode in (0, 1, 2)


def test_king_verify_passes() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/king_verify.sh")],
        cwd=str(ROOT),
        env={**os.environ, "AA_PROJECT_ROOT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode in (0, 1)
    assert (ROOT / "evidence/king_verify_latest.json").is_file()


def test_king_clean_dry_run() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "tools/king_clean.sh"), "--dry-run"],
        cwd=str(ROOT),
        env={**os.environ, "AA_PROJECT_ROOT": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0
    assert (ROOT / "evidence/king_clean_latest.json").is_file()
