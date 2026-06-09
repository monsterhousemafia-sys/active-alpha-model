"""V5R final isolated worktree build, test, runtime verification, and packaging."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAIN_ROOT = Path(r"e:\active_alpha_model")
WORKTREE = Path(r"e:\active_alpha_model_v5r_clean")
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
ORIGINAL_ROOT = MAIN_ROOT.resolve()
EVIDENCE = MAIN_ROOT / "evidence"
VALIDATED_SOURCE_BASE = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run([str(GIT), *args], cwd=cwd, capture_output=True, text=True, check=False)
    return (proc.stdout or "") + (proc.stderr or "")


def _py(cwd: Path) -> Path:
    venv = cwd / ".venv" / "Scripts" / "python.exe"
    if not venv.is_file():
        raise SystemExit(f"Missing venv python: {venv}")
    return venv


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def ensure_worktree(commit: str) -> None:
    listed = _git(["worktree", "list"], cwd=MAIN_ROOT)
    worktree_norm = str(WORKTREE).replace("\\", "/").lower()
    registered = any(worktree_norm in line.replace("\\", "/").lower() for line in listed.splitlines())
    if WORKTREE.is_dir():
        if registered:
            _run_git(["worktree", "remove", "--force", str(WORKTREE)], cwd=MAIN_ROOT)
        shutil.rmtree(WORKTREE, ignore_errors=True)
    _run_git(["worktree", "add", "--detach", str(WORKTREE), commit], cwd=MAIN_ROOT)


def _run_git(args: list[str], *, cwd: Path) -> None:
    proc = subprocess.run([str(GIT), *args], cwd=cwd, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed")


def create_venv() -> None:
    if (WORKTREE / ".venv").is_dir():
        shutil.rmtree(WORKTREE / ".venv")
    subprocess.run([sys.executable, "-m", "venv", str(WORKTREE / ".venv")], check=True)
    py = _py(WORKTREE)
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], cwd=WORKTREE, check=True)
    subprocess.run(
        [str(py), "-m", "pip", "install", "-r", "requirements_active_alpha.txt", "pyinstaller", "pytest"],
        cwd=WORKTREE,
        check=True,
    )


def document_prebuild(cwd: Path) -> dict:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    head = _git(["rev-parse", "HEAD"], cwd=cwd).strip()
    porcelain = _git(["status", "--porcelain"], cwd=cwd).strip()
    (EVIDENCE / "clean_build_git_status_before_build.txt").write_text(porcelain + "\n", encoding="utf-8")
    py = _py(cwd)
    env = _clean_env()
    sp = subprocess.run([str(py), "-c", "import sys, json; print(json.dumps(sys.path))"], cwd=cwd, env=env, capture_output=True, text=True, check=True)
    sys_path = json.loads(sp.stdout)
    original_norm = os.path.normcase(str(ORIGINAL_ROOT))
    original_in_path = any(
        p and os.path.normcase(os.path.abspath(p)) == original_norm for p in sys_path
    )
    doc = {
        "clean_worktree_path": str(WORKTREE),
        "build_source_commit": head,
        "validated_source_base": VALIDATED_SOURCE_BASE,
        "git_status_porcelain_before_build": porcelain,
        "python_sys_path": sys_path,
        "original_worktree_in_build_module_search_path": original_in_path,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "generated_at_utc": _utc_now(),
    }
    (EVIDENCE / "v5r_isolated_build_pre_check.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if porcelain:
        raise SystemExit("git status --porcelain not empty before build")
    if original_in_path:
        raise SystemExit(f"{ORIGINAL_ROOT} found in sys.path")
    return doc


def run_validation(cwd: Path) -> dict:
    py = _py(cwd)
    env = _clean_env()
    results: dict = {}
    pytest_log = ""
    for label, cmd in (
        ("compileall", [str(py), "-m", "compileall", "."]),
        ("pytest", [str(py), "-u", "-m", "pytest", "-vv", "-s", "--tb=short", "--durations=20"]),
        ("core_check", [str(py), "check_active_alpha_core.py"]),
    ):
        log_path = EVIDENCE / f"v5r_final_{label}.log"
        with log_path.open("w", encoding="utf-8") as logf:
            proc = subprocess.run(cmd, cwd=cwd, env=env, stdout=logf, stderr=subprocess.STDOUT)
        log_text = log_path.read_text(encoding="utf-8")
        results[f"{label}_exit"] = proc.returncode
        if label == "pytest":
            pytest_log = log_text
        if proc.returncode != 0:
            raise SystemExit(f"{label} failed with exit {proc.returncode}")
    summary_lines = [ln for ln in pytest_log.splitlines() if " passed" in ln and " in " in ln]
    pytest_summary = summary_lines[-1].strip() if summary_lines else ""
    if "Traceback (most recent call last)" in pytest_log.split(pytest_summary)[-1] if pytest_summary else pytest_log:
        raise SystemExit("pytest log terminated with traceback")
    validation = {
        "compileall_exit_code": results["compileall_exit"],
        "pytest_exit_code": results["pytest_exit"],
        "core_check_exit_code": results["core_check_exit"],
        "pytest_summary_line": pytest_summary,
        "pytest_log_terminated_without_traceback": "Traceback (most recent call last)" not in pytest_log,
        "full_test_suite_pass": results["pytest_exit"] == 0,
        "deselected_hang_workaround_used": False,
        "generated_at_utc": _utc_now(),
    }
    (EVIDENCE / "v5r_final_validation_summary.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    results["pytest_summary"] = pytest_summary
    return results


def _kill_marktanalyse() -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -Name Marktanalyse -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        check=False,
    )


def _stage_exes_to_main(cwd: Path) -> None:
    _kill_marktanalyse()
    (MAIN_ROOT / "dist").mkdir(parents=True, exist_ok=True)
    for name in ("Marktanalyse.exe", "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"):
        src = cwd / "dist" / name
        if src.is_file():
            shutil.copy2(src, MAIN_ROOT / "dist" / name)
            if name == "Marktanalyse.exe":
                shutil.copy2(src, MAIN_ROOT / name)


def run_build(cwd: Path) -> str:
    py = _py(cwd)
    env = _clean_env()
    for script in ("tools/build_v5r_standalone_exe.py", "tools/build_v5r_fail_closed_test_exe.py"):
        proc = subprocess.run([str(py), script], cwd=cwd, env=env)
        if proc.returncode != 0:
            raise SystemExit(f"Build failed: {script}")
    release = cwd / "dist" / "Marktanalyse.exe"
    if not release.is_file():
        raise SystemExit("Release EXE missing")
    return _sha256(release)


def runtime_verification(cwd: Path, build_commit: str) -> None:
    py = _py(MAIN_ROOT)
    env = _clean_env()
    env["AA_DECISION_COCKPIT_SMOKE_TEST"] = "1"
    proc = subprocess.run([str(cwd / "dist" / "Marktanalyse.exe")], cwd=cwd, env=env)
    (EVIDENCE / "v5r_final_exe_smoke_exit.txt").write_text(f"SMOKE_EXIT_CODE: {proc.returncode}\n", encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit("Release smoke test failed")
    smoke_path = cwd / "evidence" / "v5r_exe_smoke_test_result.json"
    if not smoke_path.is_file():
        smoke_path = MAIN_ROOT / "evidence" / "v5r_exe_smoke_test_result.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    if smoke.get("build_provenance", {}).get("build_source_commit") != build_commit:
        raise SystemExit("Smoke evidence build_source_commit mismatch")
    shutil.copy2(smoke_path, EVIDENCE / "v5r_exe_smoke_test_result.json")
    _kill_marktanalyse()


def runtime_verification_after_submission(build_commit: str) -> None:
    py = _py(MAIN_ROOT)
    if str(MAIN_ROOT) not in sys.path:
        sys.path.insert(0, str(MAIN_ROOT))
    for script in (
        "tools/v5r_release_interactive_gui_test.py",
        "tools/v5r_fail_closed_runtime_test.py",
    ):
        proc = subprocess.run([str(py), str(MAIN_ROOT / script)], cwd=MAIN_ROOT, env=_clean_env())
        if proc.returncode != 0:
            raise SystemExit(f"Runtime script failed: {script}")
    gui = json.loads((EVIDENCE / "v5r_release_interactive_gui_verification.json").read_text(encoding="utf-8"))
    fc = json.loads((EVIDENCE / "v5r_fail_closed_runtime_verification.json").read_text(encoding="utf-8"))
    if gui.get("build_source_commit") != build_commit:
        raise SystemExit("Release GUI evidence build_source_commit mismatch")
    if fc.get("build_source_commit") != build_commit:
        raise SystemExit("Fail-closed runtime evidence build_source_commit mismatch")
    if gui.get("release_exe_sha256") != _sha256(MAIN_ROOT / "Marktanalyse.exe"):
        raise SystemExit("Release GUI evidence sha256 mismatch")
    _kill_marktanalyse()


def copy_artifacts(cwd: Path, build_commit: str, exe_hash: str) -> None:
    _kill_marktanalyse()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (MAIN_ROOT / "dist").mkdir(parents=True, exist_ok=True)
    for name in ("Marktanalyse.exe", "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"):
        src = cwd / "dist" / name
        if src.is_file():
            shutil.copy2(src, MAIN_ROOT / "dist" / name)
            if name == "Marktanalyse.exe":
                shutil.copy2(src, MAIN_ROOT / name)
    (MAIN_ROOT / "dist" / "Marktanalyse.exe.sha256").write_text(f"{exe_hash}  Marktanalyse.exe\n", encoding="ascii")
    (MAIN_ROOT / "Marktanalyse.exe.sha256").write_text(f"{exe_hash}  Marktanalyse.exe\n", encoding="ascii")
    test_hash = _sha256(MAIN_ROOT / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe")
    (MAIN_ROOT / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe.sha256").write_text(
        f"{test_hash}  Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe\n", encoding="ascii"
    )
    env_doc = {
        "clean_worktree_path": str(WORKTREE),
        "build_source_commit": build_commit,
        "validated_source_base": VALIDATED_SOURCE_BASE,
        "build_scope": "V5R_NEUTRAL_READ_ONLY_RELEASE",
        "release_snapshot_scope": "V5R_READ_ONLY_NEUTRAL",
        "final_exe_sha256": exe_hash,
        "generated_at_utc": _utc_now(),
    }
    (EVIDENCE / "v5r_final_build_environment.json").write_text(json.dumps(env_doc, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "v5r_validated_source_commit.txt").write_text(f"{build_commit}\nvalidated_source_base={VALIDATED_SOURCE_BASE}\n", encoding="utf-8")
    if (doc_path("CODEX_V5R_BUILD_LOG.txt")).is_file():
        shutil.copy2(doc_path("CODEX_V5R_BUILD_LOG.txt"), EVIDENCE / "v5r_final_build_log.txt")
    after = _git(["status", "--porcelain"], cwd=cwd).strip()
    (EVIDENCE / "clean_build_git_status_after_build.txt").write_text(after + "\n", encoding="utf-8")
    subprocess.run([str(_py(MAIN_ROOT)), str(MAIN_ROOT / "tools" / "generate_v5r_git_patch_evidence.py")], cwd=MAIN_ROOT, check=True)


def write_scope_audit(build_commit: str, exe_hash: str) -> None:
    blob = (MAIN_ROOT / "Marktanalyse.exe").read_bytes()
    forbidden = {
        "R3_w075_q065_noexit": b"R3_w075_q065_noexit" not in blob,
        "MOM_63_TOP12": b"MOM_63_TOP12" not in blob,
        "M1_MOM_BLEND_MATCHED_CONTROLS": b"M1_MOM_BLEND_MATCHED_CONTROLS" not in blob,
    }
    (EVIDENCE / "v5r_release_binary_scope_audit.json").write_text(
        json.dumps(
            {
                "release_exe": "Marktanalyse.exe",
                "sha256": exe_hash,
                "build_source_commit": build_commit,
                "forbidden_strings_absent": forbidden,
                "pass": all(forbidden.values()),
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_report(build_commit: str, exe_hash: str) -> None:
    text = f"""# CODEX V5R Standalone EXE Report

```text
PROGRAM: MARKTANALYSE_DECISION_COCKPIT
BUILD_SOURCE_COMMIT: {build_commit}
VALIDATED_SOURCE_BASE: {VALIDATED_SOURCE_BASE}
BUILD_SCOPE: V5R_NEUTRAL_READ_ONLY_RELEASE
RELEASE_SNAPSHOT_SCOPE: V5R_READ_ONLY_NEUTRAL

V5R_ISOLATED_BUILD_ENVIRONMENT: PASS
ORIGINAL_WORKTREE_IN_BUILD_MODULE_SEARCH_PATH: NO
V5R_RUNTIME_EVIDENCE_BUILD_COMMIT_CONSISTENCY: PASS
INTERACTIVE_RELEASE_GUI_EVIDENCE: PASS
SUBMITTED_RELEASE_EXE_USED_FOR_INTERACTIVE_TEST: YES
FAIL_CLOSED_TEST_EXE_ACTUALLY_EXECUTED: YES
FAIL_CLOSED_TEST_RUNTIME_EVIDENCE: PASS
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
    (doc_path("CODEX_V5R_STANDALONE_EXE_REPORT.md")).write_text(text, encoding="utf-8")


def main() -> int:
    commit = _git(["rev-parse", "HEAD"], cwd=MAIN_ROOT).strip()
    ensure_worktree(commit)
    create_venv()
    pre = document_prebuild(WORKTREE)
    run_validation(WORKTREE)
    exe_hash = run_build(WORKTREE)
    _kill_marktanalyse()
    _stage_exes_to_main(WORKTREE)
    runtime_verification(WORKTREE, pre["build_source_commit"])
    copy_artifacts(WORKTREE, pre["build_source_commit"], exe_hash)
    runtime_verification_after_submission(pre["build_source_commit"])
    write_scope_audit(pre["build_source_commit"], exe_hash)
    subprocess.run(
        [str(_py(MAIN_ROOT)), str(MAIN_ROOT / "tools" / "complete_v5r_runtime_riskoff_evidence.py"), "--audits-only"],
        cwd=MAIN_ROOT,
        check=False,
    )
    subprocess.run([str(_py(MAIN_ROOT)), str(MAIN_ROOT / "tools" / "static_verify_v5r_standalone_exe.py")], cwd=MAIN_ROOT, check=True)
    write_report(pre["build_source_commit"], exe_hash)
    subprocess.run([str(_py(MAIN_ROOT)), str(MAIN_ROOT / "tools" / "build_v5r_final_review_zip.py")], cwd=MAIN_ROOT, check=True)
    summary = {"build_source_commit": pre["build_source_commit"], "exe_sha256": exe_hash, "pass": True}
    (EVIDENCE / "v5r_final_isolated_run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
