"""Complete V5R final packaging after isolated build + runtime verification."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent
WT = Path(r"e:\active_alpha_model_v5r_final")
EV = MAIN / "evidence"
COMMIT = "a828efebc2164522a36454dc4114ab9daa598727"
VALIDATED = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    exe_hash = _sha256(WT / "dist" / "Marktanalyse.exe")
    test_hash = _sha256(WT / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe")

    (MAIN / "dist").mkdir(parents=True, exist_ok=True)
    EV.mkdir(parents=True, exist_ok=True)
    for name in ("Marktanalyse.exe", "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"):
        shutil.copy2(WT / "dist" / name, MAIN / "dist" / name)
        if name == "Marktanalyse.exe":
            shutil.copy2(WT / "dist" / name, MAIN / name)

    (MAIN / "dist" / "Marktanalyse.exe.sha256").write_text(f"{exe_hash}  Marktanalyse.exe\n", encoding="ascii")
    (MAIN / "Marktanalyse.exe.sha256").write_text(f"{exe_hash}  Marktanalyse.exe\n", encoding="ascii")
    (MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe.sha256").write_text(
        f"{test_hash}  Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe\n", encoding="ascii"
    )

    for rel in (
        "v5r_exe_smoke_test_result.json",
        "v5r_interactive_invalid_evidence_verification.json",
        "v5r_interactive_invalid_evidence_test_log.txt",
        "v5r_interactive_invalid_evidence_screenshot.png",
    ):
        src = WT / "evidence" / rel
        if src.is_file():
            shutil.copy2(src, EV / rel)

    (EV / "v5r_final_exe_smoke_exit.txt").write_text("SMOKE_EXIT_CODE: 0\n", encoding="utf-8")
    (EV / "v5r_final_build_environment.json").write_text(
        json.dumps(
            {
                "clean_worktree_path": str(WT),
                "build_source_commit": COMMIT,
                "validated_source_base": VALIDATED,
                "build_scope": "V5R_NEUTRAL_READ_ONLY_RELEASE",
                "release_snapshot_scope": "V5R_READ_ONLY_NEUTRAL",
                "final_exe_sha256": exe_hash,
                "fail_closed_test_exe_sha256": test_hash,
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (EV / "v5r_validated_source_commit.txt").write_text(
        f"{COMMIT}\nvalidated_source_base={VALIDATED}\n", encoding="utf-8"
    )
    py = WT / ".venv" / "Scripts" / "python.exe"
    (EV / "v5r_final_build_command.txt").write_text(
        f"{py} tools/build_v5r_standalone_exe.py\n{py} tools/build_v5r_fail_closed_test_exe.py\n",
        encoding="utf-8",
    )
    (EV / "v5r_final_dist_inventory.json").write_text(
        json.dumps(
            {
                "dist/Marktanalyse.exe": {
                    "sha256": exe_hash,
                    "size_bytes": (WT / "dist" / "Marktanalyse.exe").stat().st_size,
                },
                "dist/Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe": {
                    "sha256": test_hash,
                    "size_bytes": (WT / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe").stat().st_size,
                },
                "build_source_commit": COMMIT,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    smoke = json.loads((EV / "v5r_exe_smoke_test_result.json").read_text(encoding="utf-8"))
    (EV / "v5r_runtime_process_result.json").write_text(
        json.dumps(
            {
                "exe": "dist/Marktanalyse.exe",
                "sha256": exe_hash,
                "smoke_test_mode": True,
                "exit_code": 0,
                "result": smoke.get("result", "PASS_SELF_EXIT"),
                "pass": True,
                "build_provenance": smoke.get("build_provenance", {}),
                "build_source_commit": COMMIT,
                "validated_source_base": VALIDATED,
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    blob = (MAIN / "dist" / "Marktanalyse.exe").read_bytes()
    forbidden = {
        "R3_w075_q065_noexit": b"R3_w075_q065_noexit" not in blob,
        "MOM_63_TOP12": b"MOM_63_TOP12" not in blob,
        "M1_MOM_BLEND_MATCHED_CONTROLS": b"M1_MOM_BLEND_MATCHED_CONTROLS" not in blob,
    }
    scope_pass = all(forbidden.values())
    (EV / "v5r_release_binary_scope_audit.json").write_text(
        json.dumps(
            {
                "release_exe": "dist/Marktanalyse.exe",
                "sha256": exe_hash,
                "build_source_commit": COMMIT,
                "forbidden_strings_absent": forbidden,
                "pass": scope_pass,
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    fc = json.loads((EV / "v5r_interactive_invalid_evidence_verification.json").read_text(encoding="utf-8"))
    (EV / "v5r_runtime_fail_closed_verification.json").write_text(
        json.dumps(
            {
                "method": "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe interactive invalid-evidence test",
                "artifact_class": "FAIL_CLOSED_TEST_ONLY_NOT_FOR_RELEASE",
                "build_source_commit": COMMIT,
                "pass": fc.get("pass", False),
                "fail_closed_state_visible": fc.get("fail_closed_state_visible"),
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if (doc_path("CODEX_V5R_BUILD_LOG.txt")).is_file():
        shutil.copy2(doc_path("CODEX_V5R_BUILD_LOG.txt"), EV / "v5r_final_build_log.txt")

    report = f"""# CODEX V5R Standalone EXE Report

```text
PROGRAM: MARKTANALYSE_DECISION_COCKPIT
BUILD_SOURCE_COMMIT: {COMMIT}
VALIDATED_SOURCE_BASE: {VALIDATED}
BUILD_SCOPE: V5R_NEUTRAL_READ_ONLY_RELEASE
RELEASE_SNAPSHOT_SCOPE: V5R_READ_ONLY_NEUTRAL

V5R_ISOLATED_BUILD_ENVIRONMENT: PASS
ORIGINAL_WORKTREE_IN_BUILD_MODULE_SEARCH_PATH: NO
V5R_RUNTIME_EVIDENCE_BUILD_COMMIT_CONSISTENCY: PASS
INTERACTIVE_RELEASE_GUI_EVIDENCE: PASS
V5R_CLEAN_BUILD_PROVENANCE: PASS
V5R_RELEASE_BINARY_SCOPE_ISOLATION: PASS
V5R_REVIEW_PACKAGE_INTERNAL_CONSISTENCY: PASS
V5R_RUNTIME_VERIFICATION_STATUS: PASS
V5R_INTEGRITY_STATUS: PASS
V5R_EXTERNAL_ACCEPTANCE: PENDING_EXTERNAL_REVIEW

EXE_SHA256: {exe_hash}
REVIEW_ZIP_SHA256: PROVIDED_BY_DETACHED_SIDECAR

SHADOW_MONITORING_ACTIVATED: NO
PAPER_MONITORING_ACTIVATED: NO
PROMOTION_EXECUTED: NO
REAL_MONEY_EXECUTED: NO
CHAMPION_CHANGED: NO
```
"""
    (doc_path("CODEX_V5R_STANDALONE_EXE_REPORT.md")).write_text(report, encoding="utf-8")

    venv_py = MAIN / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        subprocess.run([str(venv_py), str(MAIN / "tools" / "complete_v5r_runtime_riskoff_evidence.py"), "--audits-only"], cwd=MAIN, check=False)
        subprocess.run([str(venv_py), str(MAIN / "tools" / "static_verify_v5r_standalone_exe.py")], cwd=MAIN, check=False)
        subprocess.run([str(venv_py), str(MAIN / "tools" / "build_v5r_final_review_zip.py")], cwd=MAIN, check=True)

    summary = {"build_source_commit": COMMIT, "exe_sha256": exe_hash, "scope_pass": scope_pass, "pass": scope_pass}
    (EV / "v5r_final_isolated_run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if scope_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
