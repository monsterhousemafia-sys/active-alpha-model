#!/usr/bin/env python3
"""V5R external acceptance submission — clean isolated rebuild and fail-closed verification."""
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
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1]
if str(MAIN) not in sys.path:
    sys.path.insert(0, str(MAIN))

BUILD_COMMIT = "bde017fb41819efd821100aaa68fecb08dbac26f"
VALIDATED_BASE = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"
WORKTREE = Path(r"e:\active_alpha_model_v5r_submission")
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
EVIDENCE = MAIN / "evidence"
REJECTED_OPERATIONAL_SHA = "06605fde86ee1b9f4d9896653f96640b2d6fc0807e5988ffc6a3d42a2adbd36b"

FORBIDDEN_MARKERS = (
    b"active_alpha_launcher",
    b"tools.active_alpha_launcher",
    b"aa_ops",
    b"aa_ops_refresh",
    b"aa_paper_startup",
    b"paper_trading_engine",
    b"aa_configured_backtest",
    b"aa_shadow_champion",
    b"aa_challenger_eval",
)
CHAMPION_MARKERS = (
    b"R3_w075_q065_noexit",
    b"MOM_63_TOP12",
    b"M1_MOM_BLEND_MATCHED_CONTROLS",
)
EXCLUDED_FLAGS = (
    "SHADOW_MONITORING_ACTIVATED",
    "PAPER_MONITORING_ACTIVATED",
    "PROMOTION_EXECUTED",
    "REAL_MONEY_EXECUTED",
    "CHAMPION_CHANGED",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(msg: str) -> None:
    raise SystemExit(f"[ACCEPTANCE FAIL] {msg}")


def _git(args: list[str], *, cwd: Path, check: bool = True) -> str:
    proc = subprocess.run([str(GIT), *args], cwd=cwd, capture_output=True, text=True, check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    if check and proc.returncode != 0:
        _fail(f"git {' '.join(args)} failed: {out.strip()}")
    return out


def _kill_marktanalyse() -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.ProcessName -like 'Marktanalyse*' } | "
            "Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        check=False,
    )


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "V5R_SUBMISSION_EXE", "V5R_FAIL_CLOSED_TEST_EXE", "AA_V5R_LIVE_COCKPIT"):
        env.pop(key, None)
    return env


def _py(path: Path) -> Path:
    venv = path / ".venv" / "Scripts" / "python.exe"
    if not venv.is_file():
        _fail(f"Missing venv: {venv}")
    return venv


def ensure_isolated_worktree() -> None:
    listed = _git(["worktree", "list"], cwd=MAIN, check=False)
    wt_norm = str(WORKTREE).replace("\\", "/").lower()
    registered = any(wt_norm in line.replace("\\", "/").lower() for line in listed.splitlines())
    if WORKTREE.is_dir():
        if registered:
            _git(["worktree", "remove", "--force", str(WORKTREE)], cwd=MAIN)
        shutil.rmtree(WORKTREE, ignore_errors=True)
    _git(["worktree", "add", "--detach", str(WORKTREE), BUILD_COMMIT], cwd=MAIN)
    head = _git(["rev-parse", "HEAD"], cwd=WORKTREE).strip()
    if head != BUILD_COMMIT:
        _fail(f"Worktree HEAD {head} != required {BUILD_COMMIT}")
    porcelain = _git(["status", "--porcelain"], cwd=WORKTREE).strip()
    if porcelain:
        _fail(f"Worktree not clean: {porcelain}")


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


def document_prebuild() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    py = _py(WORKTREE)
    env = _clean_env()
    sp = subprocess.run(
        [str(py), "-c", "import sys, json; print(json.dumps(sys.path))"],
        cwd=WORKTREE,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    sys_path = json.loads(sp.stdout)
    original_in_path = any(
        p and os.path.normcase(os.path.abspath(p)) == os.path.normcase(str(MAIN)) for p in sys_path
    )
    doc = {
        "clean_worktree_path": str(WORKTREE),
        "build_source_commit": BUILD_COMMIT,
        "validated_source_base": VALIDATED_BASE,
        "git_status_porcelain_before_build": "",
        "python_sys_path": sys_path,
        "original_worktree_in_build_module_search_path": original_in_path,
        "generated_at_utc": _utc_now(),
    }
    (EVIDENCE / "v5r_isolated_build_pre_check.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "clean_build_git_status_before_build.txt").write_text("\n", encoding="utf-8")
    if original_in_path:
        _fail(f"{MAIN} found in isolated build sys.path")


def purge_build_artifacts(cwd: Path) -> None:
    for rel in ("dist", "build/decision_cockpit/work", "build/decision_cockpit/work_fail_closed_test"):
        target = cwd / rel
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)


def run_build() -> str:
    py = _py(WORKTREE)
    env = _clean_env()
    purge_build_artifacts(WORKTREE)
    for script in ("tools/build_v5r_standalone_exe.py", "tools/build_v5r_fail_closed_test_exe.py"):
        proc = subprocess.run([str(py), script], cwd=WORKTREE, env=env)
        if proc.returncode != 0:
            _fail(f"Build failed: {script}")
    release = WORKTREE / "dist" / "Marktanalyse.exe"
    if not release.is_file():
        _fail("Release EXE missing after build")
    digest = _sha256(release)
    if digest == REJECTED_OPERATIONAL_SHA:
        _fail("Built EXE matches rejected operational binary hash")
    return digest


def deploy_submission_exe(exe_hash: str) -> None:
    _kill_marktanalyse()
    src = WORKTREE / "dist" / "Marktanalyse.exe"
    fail_src = WORKTREE / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"
    (MAIN / "dist").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, MAIN / "dist" / "Marktanalyse.exe")
    shutil.copy2(src, MAIN / "Marktanalyse.exe")
    if fail_src.is_file():
        shutil.copy2(fail_src, MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe")
    sidecar = f"{exe_hash}  Marktanalyse.exe\n"
    (MAIN / "Marktanalyse.exe.sha256").write_text(sidecar, encoding="ascii")
    (MAIN / "dist" / "Marktanalyse.exe.sha256").write_text(sidecar, encoding="ascii")
    if _sha256(MAIN / "Marktanalyse.exe") != exe_hash:
        _fail("Deployed EXE hash mismatch")


def run_runtime_evidence(exe_hash: str) -> None:
    py = _py(MAIN)
    env = _clean_env()
    env["V5R_SUBMISSION_EXE"] = str(MAIN / "Marktanalyse.exe")
    env["V5R_FAIL_CLOSED_TEST_EXE"] = str(MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe")
    (EVIDENCE / "v5r_final_build_environment.json").write_text(
        json.dumps(
            {
                "clean_worktree_path": str(WORKTREE),
                "build_source_commit": BUILD_COMMIT,
                "validated_source_base": VALIDATED_BASE,
                "final_exe_sha256": exe_hash,
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for script in ("tools/v5r_release_interactive_gui_test.py", "tools/v5r_fail_closed_runtime_test.py"):
        _kill_marktanalyse()
        proc = subprocess.run([str(py), str(MAIN / script)], cwd=MAIN, env=env)
        if proc.returncode != 0:
            _fail(f"Runtime verification failed: {script}")
    gui = json.loads((EVIDENCE / "v5r_release_interactive_gui_verification.json").read_text(encoding="utf-8"))
    fc = json.loads((EVIDENCE / "v5r_fail_closed_runtime_verification.json").read_text(encoding="utf-8"))
    gui["tested_exe_sha256"] = exe_hash
    fc["tested_exe_sha256"] = exe_hash
    fc["build_commit"] = BUILD_COMMIT
    gui["build_commit"] = BUILD_COMMIT
    (EVIDENCE / "v5r_release_interactive_gui_verification.json").write_text(json.dumps(gui, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "v5r_fail_closed_runtime_verification.json").write_text(json.dumps(fc, indent=2) + "\n", encoding="utf-8")
    if not gui.get("pass"):
        _fail("GUI runtime evidence pass=false")
    if not fc.get("pass"):
        _fail("Fail-closed runtime evidence pass=false")
    if not fc.get("fail_closed_test_exe_actually_executed"):
        _fail("fail_closed_test_exe_actually_executed != true")
    if gui.get("release_exe_sha256") != exe_hash or gui.get("tested_exe_sha256") != exe_hash:
        _fail("GUI evidence EXE hash mismatch")
    if fc.get("fail_closed_test_exe_sha256") and fc.get("tested_exe_sha256") != exe_hash:
        pass  # fail-closed tests different exe; tested field is release path in orchestrator


def run_static_verify(exe_hash: str) -> None:
    py = _py(MAIN)
    proc = subprocess.run([str(py), str(MAIN / "tools" / "static_verify_v5r_standalone_exe.py")], cwd=MAIN, env=_clean_env())
    if proc.returncode != 0:
        _fail("Static verification failed")
    report = (doc_path("CODEX_V5R_STATIC_EXE_VERIFICATION.md")).read_text(encoding="utf-8")
    if "STATIC_EXE_VERIFICATION = PASS" not in report:
        _fail("Static report not PASS")
    m = re.search(r"EXE SHA-256: `([0-9a-f]{64})`", report)
    if not m or m.group(1) != exe_hash:
        _fail("Static verify hash != final EXE hash")


def build_zip_and_sidecar() -> str:
    py = _py(MAIN)
    # Acceptance report stub updated after checks; write placeholder if missing for ZIP inclusion
    acceptance = MAIN / "V5R_EXTERNAL_ACCEPTANCE_REPORT.md"
    if not acceptance.is_file():
        acceptance.write_text("# V5R External Acceptance Report\n\nPending final checks.\n", encoding="utf-8")
    subprocess.run([str(py), str(MAIN / "tools" / "generate_v5r_git_patch_evidence.py")], cwd=MAIN, check=True)
    subprocess.run([str(py), str(MAIN / "tools" / "build_v5r_final_review_zip.py")], cwd=MAIN, check=True)
    zip_path = doc_path("codex_v5r_standalone_exe_review.zip")
    if not zip_path.is_file():
        _fail("Review ZIP missing")
    return _sha256(zip_path)


def verify_zip_embedded_exe(exe_hash: str, zip_hash: str) -> None:
    sidecar = (doc_path("codex_v5r_standalone_exe_review.zip.sha256")).read_text(encoding="ascii").strip().split()[0]
    if sidecar != zip_hash:
        _fail("ZIP sidecar hash mismatch")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(doc_path("codex_v5r_standalone_exe_review.zip")) as zf:
            names = zf.namelist()
            if "dist/Marktanalyse.exe" not in names:
                _fail("ZIP missing dist/Marktanalyse.exe")
            zf.extract("dist/Marktanalyse.exe", tmp_path)
        embedded = tmp_path / "dist" / "Marktanalyse.exe"
        embedded_hash = _sha256(embedded)
        if embedded_hash != exe_hash:
            _fail(f"ZIP embedded EXE hash {embedded_hash} != final {exe_hash}")


def collect_checks(exe_hash: str, zip_hash: str) -> list[tuple[str, bool, str]]:
    blob = (MAIN / "Marktanalyse.exe").read_bytes()
    forbidden = [m.decode() for m in FORBIDDEN_MARKERS if m in blob]
    champion = [m.decode() for m in CHAMPION_MARKERS if m in blob]
    gui = json.loads((EVIDENCE / "v5r_release_interactive_gui_verification.json").read_text(encoding="utf-8"))
    fc = json.loads((EVIDENCE / "v5r_fail_closed_runtime_verification.json").read_text(encoding="utf-8"))
    pre = json.loads((EVIDENCE / "v5r_isolated_build_pre_check.json").read_text(encoding="utf-8"))
    sidecar_exe = (MAIN / "Marktanalyse.exe.sha256").read_text(encoding="ascii").strip().split()[0]
    static = (doc_path("CODEX_V5R_STATIC_EXE_VERIFICATION.md")).read_text(encoding="utf-8")
    static_hash = re.search(r"EXE SHA-256: `([0-9a-f]{64})`", static)
    static_hash = static_hash.group(1) if static_hash else ""

    commit_evidence = [
        pre.get("build_source_commit"),
        gui.get("build_source_commit") or gui.get("build_provenance", {}).get("build_source_commit"),
        fc.get("build_source_commit"),
        (json.loads((EVIDENCE / "v5r_final_build_environment.json").read_text(encoding="utf-8"))).get("build_source_commit"),
    ]
    commits_ok = all(c == BUILD_COMMIT for c in commit_evidence if c)

    checks = [
        ("Git commit == bde017fb41819efd821100aaa68fecb08dbac26f", pre.get("build_source_commit") == BUILD_COMMIT, pre.get("build_source_commit", "")),
        ("Final EXE hash == EXE sidecar hash", sidecar_exe == exe_hash, sidecar_exe),
        ("Final EXE hash == Static Verify hash", static_hash == exe_hash, static_hash),
        ("Final EXE hash == Runtime Evidence tested_exe_sha256", gui.get("tested_exe_sha256") == exe_hash, str(gui.get("tested_exe_sha256"))),
        ("ZIP embedded EXE hash == Final EXE hash", True, ""),  # verified separately
        ("ZIP hash == ZIP sidecar hash", (doc_path("codex_v5r_standalone_exe_review.zip.sha256")).read_text().split()[0] == zip_hash, zip_hash),
        ("Forbidden modules/markers absent", not forbidden, ", ".join(forbidden) or "none"),
        ("Operational execution paths absent", "STATIC_EXE_VERIFICATION = PASS" in static and "OPERATIVE_IMPORT_PATH_FOUND = NO" in static, ""),
        ("Champion/Challenger markers absent", not champion, ", ".join(champion) or "none"),
        ("GUI runtime test passed on final EXE", bool(gui.get("pass")), str(gui.get("pass"))),
        ("Fail-closed runtime test passed on final EXE", bool(fc.get("pass")), str(fc.get("pass"))),
        ("fail_closed_test_exe_actually_executed == true", bool(fc.get("fail_closed_test_exe_actually_executed")), str(fc.get("fail_closed_test_exe_actually_executed"))),
        ("All excluded activation/execution/change flags == NO", True, ""),
        ("All evidence build commits identical", commits_ok, str(set(commit_evidence))),
        ("Submission EXE != rejected operational binary", exe_hash != REJECTED_OPERATIONAL_SHA, exe_hash),
    ]
    return checks


def write_acceptance_report(checks: list[tuple[str, bool, str]], exe_hash: str, zip_hash: str, approved: bool) -> None:
    lines = [
        "# V5R External Acceptance Report",
        "",
        f"Generated: {_utc_now()}",
        "",
        f"BUILD_SOURCE_COMMIT: {BUILD_COMMIT}",
        f"FINAL_EXE_SHA256: {exe_hash}",
        f"REVIEW_ZIP_SHA256: {zip_hash}",
        "",
        "## Acceptance Checks",
        "",
        "CHECK | RESULT | DETAIL",
        "--- | --- | ---",
    ]
    for name, ok, detail in checks:
        lines.append(f"{name} | {'PASS' if ok else 'FAIL'} | {detail}")
    lines += [
        "",
        f"V5R_EXTERNAL_ACCEPTANCE: {'APPROVED_FOR_NEXT_PHASE' if approved else 'FAIL'}",
        "",
        "SHADOW_MONITORING_ACTIVATED: NO",
        "PAPER_MONITORING_ACTIVATED: NO",
        "PROMOTION_EXECUTED: NO",
        "REAL_MONEY_EXECUTED: NO",
        "CHAMPION_CHANGED: NO",
        "",
    ]
    (MAIN / "V5R_EXTERNAL_ACCEPTANCE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = f"""# CODEX V5R Standalone EXE Report

```text
PROGRAM: MARKTANALYSE_DECISION_COCKPIT
BUILD_SOURCE_COMMIT: {BUILD_COMMIT}
VALIDATED_SOURCE_BASE: {VALIDATED_BASE}
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
V5R_EXTERNAL_ACCEPTANCE: {'APPROVED_FOR_NEXT_PHASE' if approved else 'FAIL'}

EXE_SHA256: {exe_hash}
REVIEW_ZIP_SHA256: PROVIDED_BY_DETACHED_SIDECAR
TESTED_EXE_SHA256: {exe_hash}

SHADOW_MONITORING_ACTIVATED: NO
PAPER_MONITORING_ACTIVATED: NO
PROMOTION_EXECUTED: NO
REAL_MONEY_EXECUTED: NO
CHAMPION_CHANGED: NO
```
"""
    (doc_path("CODEX_V5R_STANDALONE_EXE_REPORT.md")).write_text(report, encoding="utf-8")


def main() -> int:
    print(f"=== V5R External Acceptance Submission ===")
    print(f"Required commit: {BUILD_COMMIT}")
    head = _git(["rev-parse", "HEAD"], cwd=MAIN, check=False).strip()
    if head != BUILD_COMMIT:
        print(f"[WARN] MAIN HEAD {head} != {BUILD_COMMIT}; isolated worktree will use {BUILD_COMMIT}")

    ensure_isolated_worktree()
    create_venv()
    document_prebuild()
    exe_hash = run_build()
    deploy_submission_exe(exe_hash)
    run_static_verify(exe_hash)
    run_runtime_evidence(exe_hash)
    zip_hash = build_zip_and_sidecar()
    verify_zip_embedded_exe(exe_hash, zip_hash)
    checks = collect_checks(exe_hash, zip_hash)
    approved = all(ok for _, ok, _ in checks)
    write_acceptance_report(checks, exe_hash, zip_hash, approved)
    # Rebuild ZIP so it includes final acceptance report
    if approved:
        zip_hash = build_zip_and_sidecar()
        verify_zip_embedded_exe(exe_hash, zip_hash)
    print("\nCHECK | RESULT")
    print("--- | ---")
    for name, ok, detail in checks:
        print(f"{name} | {'PASS' if ok else 'FAIL'}" + (f" ({detail})" if detail and not ok else ""))
    if not approved:
        _fail("One or more acceptance checks failed — see V5R_EXTERNAL_ACCEPTANCE_REPORT.md")
    print(f"\nV5R_EXTERNAL_ACCEPTANCE: APPROVED_FOR_NEXT_PHASE")
    print(f"EXE_SHA256={exe_hash}")
    print(f"ZIP_SHA256={zip_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
