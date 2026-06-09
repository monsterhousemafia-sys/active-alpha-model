#!/usr/bin/env python3
"""Reset regenerable tracked files and refresh governance exports (no model runs)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGENERABLE_TRACKED = (
    doc_rel("CODEX_V1R3_GIT_STATUS.txt"),
    doc_rel("CODEX_V2_GIT_STATUS.txt"),
    doc_rel("CODEX_V5R_BUILD_LOG.txt"),
    doc_rel("CODEX_V5R_PREBUILD_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V5_PREBUILD_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V5_RECOVERY_GIT_STATUS.txt"),
)


def main() -> int:
    for rel in REGENERABLE_TRACKED:
        path = ROOT / rel
        if path.is_file():
            subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=ROOT, check=False)
    from tools.reconcile_governance_drift import main as reconcile

    return reconcile()


if __name__ == "__main__":
    raise SystemExit(main())
