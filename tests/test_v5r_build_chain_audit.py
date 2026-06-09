"""Build chain audit tests for V5R."""

from __future__ import annotations

from aa_doc_paths import doc_path, doc_rel

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BUILD_SCRIPTS = [
    "tools/build_v5r_standalone_exe.py",
    "tools/static_verify_v5r_standalone_exe.py",
]


def test_build_scripts_do_not_launch_exe():
    for rel in BUILD_SCRIPTS:
        text = (ROOT / rel).read_text(encoding="utf-8").lower()
        assert "run_exe_once" not in text
        assert "popen(" not in text or rel.endswith("static_verify_v5r_standalone_exe.py")


def test_build_v5r_uses_onefile_spec():
    text = (ROOT / "tools/build_v5r_standalone_exe.py").read_text(encoding="utf-8")
    assert "Marktanalyse.spec" in text
    assert "smoke_test_launcher" not in text


def test_audit_report_exists_after_orchestration():
    path = doc_path("CODEX_V5R_BUILD_CHAIN_AUDIT.md")
    assert path.is_file(), "run complete_v5r_run to generate audit report"
