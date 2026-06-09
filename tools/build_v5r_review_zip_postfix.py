"""Build codex_v5r_standalone_exe_review.zip after V5R repair."""
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
    doc_rel("CODEX_V5R_STATIC_EXE_VERIFICATION.md"),
    "dist/Marktanalyse.exe.sha256",
    "evidence/v5r_exe_smoke_test_result.json",
    "evidence/v5r_runtime_process_result.json",
    "evidence/v5r_interactive_gui_verification.json",
    "evidence/v5r_fix_validation_summary_20260531_025356.txt",
    "evidence/pytest_full_v5r_fix_20260531_025356.log",
    "tools/decision_cockpit_readonly_launcher.py",
    "tools/build_v5r_standalone_exe.py",
    "aa_config_env.py",
    "tests/test_aa_config_env.py",
    "tests/test_decision_cockpit_readonly_launcher.py",
]


def main() -> None:
    zip_path = ROOT / ZIP_NAME
    if zip_path.is_file():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = ROOT / rel
            if path.is_file():
                zf.write(path, rel.replace("\\", "/"))
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (ROOT / f"{ZIP_NAME}.sha256").write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    print(f"Wrote {ZIP_NAME} sha256={digest}")


if __name__ == "__main__":
    main()
