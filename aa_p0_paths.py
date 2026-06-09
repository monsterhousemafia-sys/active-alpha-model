"""P0 directory layout for Active Alpha control plane."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

P0_DIRS = (
    "control",
    "locks",
    "checkpoints",
    "work_runs",
    "validated_runs",
    "failed_runs",
    "logs/jobs",
    "logs/integrity",
    "logs/rollback",
)


def repo_paths(root: Path) -> dict[str, Path]:
    root = Path(root)
    return {
        "control": root / "control",
        "locks": root / "locks",
        "checkpoints": root / "checkpoints",
        "work_runs": root / "work_runs",
        "validated_runs": root / "validated_runs",
        "failed_runs": root / "failed_runs",
        "logs_jobs": root / "logs" / "jobs",
        "logs_integrity": root / "logs" / "integrity",
        "logs_rollback": root / "logs" / "rollback",
    }


def ensure_p0_directories(root: Path) -> None:
    for rel in P0_DIRS:
        (Path(root) / rel).mkdir(parents=True, exist_ok=True)


def work_run_dir(root: Path, job_id: str) -> Path:
    path = Path(root) / "work_runs" / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def failed_run_dir(root: Path, job_id: str) -> Path:
    path = Path(root) / "failed_runs" / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
