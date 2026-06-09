"""Build final codex_v5r_standalone_exe_review.zip for V5R clean release."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP_NAME = "codex_v5r_standalone_exe_review.zip"

INCLUDE = [
    doc_rel("CODEX_V5R_STANDALONE_EXE_REPORT.md"),
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md",
    doc_rel("CODEX_V5R_STATIC_EXE_VERIFICATION.md"),
    "evidence/v5r_validated_source_commit.txt",
    "evidence/clean_build_git_status_before_build.txt",
    "evidence/clean_build_git_status_after_build.txt",
    "evidence/full_changed_source_inventory.txt",
    "evidence/v5r_isolated_build_pre_check.json",
    "evidence/v5r_final_validation_summary.json",
    "evidence/v5r_release_interactive_gui_verification.json",
    "evidence/v5r_release_interactive_gui_test_log.txt",
    "evidence/v5r_release_interactive_gui_screenshot.png",
    "evidence/v5r_final_pytest.log",
    "evidence/v5r_final_core_check.log",
    "evidence/v5r_final_compileall.log",
    "evidence/v5r_final_build_command.txt",
    "evidence/v5r_final_build_environment.json",
    "evidence/v5r_final_build_log.txt",
    "evidence/v5r_final_dist_inventory.json",
    "evidence/v5r_final_exe_smoke_exit.txt",
    "evidence/v5r_exe_smoke_test_result.json",
    "evidence/v5r_runtime_process_result.json",
    "evidence/v5r_release_binary_scope_audit.json",
    "evidence/v5r_fail_closed_runtime_verification.json",
    "evidence/v5r_fail_closed_runtime_test_log.txt",
    "evidence/v5r_fail_closed_runtime_test_result.json",
    "evidence/v5r_fail_closed_runtime_supplementary_render.png",
    "evidence/v5r_git_patch_manifest.txt",
    "evidence/v5r_static_import_audit.json",
    "evidence/v5r_ui_action_audit.json",
    "evidence/v5r_fail_closed_test_results.json",
    "dist/Marktanalyse.exe",
    "dist/Marktanalyse.exe.sha256",
    "dist/Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe.sha256",
    "aa_config_env.py",
    "aa_dashboard_qt.py",
    "aa_decision_cockpit_readonly_snapshot.py",
    "tools/decision_cockpit_readonly_launcher.py",
    "tools/generate_v5r_build_provenance.py",
    "tools/build_v5r_standalone_exe.py",
    "tools/build_v5r_fail_closed_test_exe.py",
    "tools/static_verify_v5r_standalone_exe.py",
    "tools/v5r_release_interactive_gui_test.py",
    "tools/v5r_fail_closed_runtime_test.py",
    "build/decision_cockpit/Marktanalyse.spec",
    "build/decision_cockpit/Marktanalyse_FAIL_CLOSED_TEST_ONLY.spec",
    "tests/test_aa_config_env.py",
    "tests/test_dashboard_gui.py",
    "tests/test_subprocess_runner.py",
    "tests/test_decision_cockpit_readonly_launcher.py",
    "tests/test_v5r_snapshot.py",
    "tests/test_v5r_static_verify.py",
]


def _patch_files() -> list[str]:
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "evidence").glob("git_show_*.patch")
        if p.is_file()
    )


def main() -> None:
    zip_path = ROOT / ZIP_NAME
    if zip_path.is_file():
        zip_path.unlink()
    include = INCLUDE + _patch_files()
    missing = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in include:
            path = ROOT / rel
            if path.is_file():
                zf.write(path, rel.replace("\\", "/"))
            else:
                missing.append(rel)
    if missing:
        print(f"WARNING missing {len(missing)} files:")
        for m in missing:
            print(f"  - {m}")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (ROOT / f"{ZIP_NAME}.sha256").write_text(f"{digest}  {ZIP_NAME}\n", encoding="ascii")
    print(f"Wrote {ZIP_NAME} sha256={digest} entries={len(include)-len(missing)}")


if __name__ == "__main__":
    main()
