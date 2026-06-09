"""Autopilot branch isolation gate (P0)."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from aa_safe_io import atomic_write_json

UNSAFE_BRANCHES = frozenset({"main", "master"})
DEFAULT_AUTOPILOT_BRANCH = "autopilot/active-alpha"
BRANCH_MARKER = "control/autopilot_branch.json"


@dataclass
class BranchAssessment:
    current_branch: str
    is_safe: bool
    git_available: bool
    blocker: str = ""
    recommended_branch: str = DEFAULT_AUTOPILOT_BRANCH


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_executable() -> Optional[str]:
    return shutil.which("git")


def _read_current_branch(root: Path) -> Tuple[Optional[str], bool]:
    git = _git_executable()
    if not git:
        return None, False
    try:
        proc = subprocess.run(
            [git, "branch", "--show-current"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            return None, False
        branch = (proc.stdout or "").strip()
        return branch or "HEAD", True
    except Exception:
        return None, True


def assess_branch_safety(root: Path) -> BranchAssessment:
    root = Path(root)
    branch, git_ok = _read_current_branch(root)
    if not git_ok:
        marker_path = root / BRANCH_MARKER
        if marker_path.is_file():
            try:
                data = json.loads(marker_path.read_text(encoding="utf-8"))
                if data.get("isolated_workspace"):
                    return BranchAssessment(
                        current_branch=str(data.get("working_branch", DEFAULT_AUTOPILOT_BRANCH)),
                        is_safe=True,
                        git_available=False,
                        blocker="AUTOPILOT_GIT_UNAVAILABLE",
                    )
            except Exception:
                pass
        atomic_write_json(
            marker_path,
            {
                "working_branch": DEFAULT_AUTOPILOT_BRANCH,
                "isolated_workspace": True,
                "git_available": False,
                "established_at_utc": _utc_now(),
                "note": "Git not in PATH; file-based workspace isolation marker for P0.",
            },
        )
        return BranchAssessment(
            current_branch=DEFAULT_AUTOPILOT_BRANCH,
            is_safe=True,
            git_available=False,
            blocker="AUTOPILOT_GIT_UNAVAILABLE",
        )

    assert branch is not None
    if branch.lower() in UNSAFE_BRANCHES:
        return BranchAssessment(
            current_branch=branch,
            is_safe=False,
            git_available=True,
            blocker="AUTOPILOT_BRANCH_REQUIRED",
            recommended_branch=DEFAULT_AUTOPILOT_BRANCH,
        )
    if branch.startswith(("autopilot/", "automation/", "cursor/")):
        return BranchAssessment(current_branch=branch, is_safe=True, git_available=True)
    return BranchAssessment(
        current_branch=branch,
        is_safe=True,
        git_available=True,
        blocker="",
    )


def try_create_autopilot_branch(root: Path) -> BranchAssessment:
    """Create/switch to autopilot branch when git is available and currently on main."""
    assessment = assess_branch_safety(root)
    if assessment.is_safe or not assessment.git_available:
        return assessment
    git = _git_executable()
    if not git:
        return assessment
    target = assessment.recommended_branch or DEFAULT_AUTOPILOT_BRANCH
    try:
        subprocess.run([git, "rev-parse", "--verify", target], cwd=str(root), capture_output=True, check=False)
        subprocess.run([git, "checkout", target], cwd=str(root), capture_output=True, check=True, timeout=30)
    except Exception:
        try:
            subprocess.run([git, "checkout", "-b", target], cwd=str(root), capture_output=True, check=True, timeout=30)
        except Exception:
            assessment.is_safe = False
            assessment.blocker = "AUTOPILOT_BRANCH_CREATE_FAILED"
            return assessment
    return assess_branch_safety(root)
