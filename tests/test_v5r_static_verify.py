"""Static V5R verify tolerates operational onedir bundle alongside submission onefile."""

from __future__ import annotations

from aa_doc_paths import doc_path, doc_rel

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_static_verify_passes_with_operational_bundle_present():
    operational_internal = ROOT / "Marktanalyse" / "_internal"
    if not operational_internal.is_dir():
        return
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "static_verify_v5r_standalone_exe.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    report = (doc_path("CODEX_V5R_STATIC_EXE_VERIFICATION.md")).read_text(encoding="utf-8")
    assert "STATIC_EXE_VERIFICATION = PASS" in report
    assert "REQUIRES_COMPANION_INTERNAL_FOLDER = NO" in report
    assert "OPERATIONAL_BUNDLE_COLOCATED = YES" in report
