"""V5R clean-build release remediation — worktree provenance, neutral release EXE, review package."""

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

ROOT = Path(__file__).resolve().parent.parent
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
SOURCE_BASE = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"
WORKTREE = Path(r"e:\active_alpha_model_v5r_clean")
EVIDENCE = ROOT / "evidence"
V5R_CHANGED = [
    "aa_config_env.py",
    "aa_dashboard_qt.py",
    "aa_decision_cockpit_readonly_snapshot.py",
    "tools/decision_cockpit_readonly_launcher.py",
    "tools/build_v5r_standalone_exe.py",
    "tools/build_v5r_fail_closed_test_exe.py",
    "build/decision_cockpit/Marktanalyse_FAIL_CLOSED_TEST_ONLY.spec",
    "tests/test_aa_config_env.py",
    "tests/test_dashboard_gui.py",
    "tests/test_subprocess_runner.py",
    "tests/test_decision_cockpit_readonly_launcher.py",
    "tests/test_v5r_snapshot.py",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def _git(args: list[str], *, cwd: Path) -> str:
    proc = _run([str(GIT), *args], cwd=cwd, check=False)
    return (proc.stdout or "") + (proc.stderr or "")


def _py(cwd: Path) -> Path:
    for candidate in (cwd / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def ensure_worktree(remediation_head: str) -> None:
    if WORKTREE.is_dir():
        status = _git(["worktree", "list"], cwd=ROOT)
        if str(WORKTREE) not in status:
            raise SystemExit(f"Path exists but is not a git worktree: {WORKTREE}")
    else:
        _run([str(GIT), "worktree", "add", "--detach", str(WORKTREE), remediation_head], cwd=ROOT)
    porcelain = _git(["status", "--porcelain"], cwd=WORKTREE).strip()
    if porcelain:
        raise SystemExit(f"Clean worktree not empty before build:\n{porcelain}")


def write_git_patches(out_dir: Path, base: str) -> None:
    for commit, name in (("70652b9", "git_show_70652b9.patch"), ("a47a8fe", "git_show_a47a8fe.patch")):
        patch = _git(["show", "--patch", commit], cwd=ROOT)
        (out_dir / name).write_text(patch, encoding="utf-8")


def write_changed_source_inventory(out_dir: Path, head: str) -> None:
    names = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", head, f"{SOURCE_BASE}..{head}"], cwd=ROOT).strip()
    extra = "\n".join(V5R_CHANGED)
    body = (
        f"validated_source_base={SOURCE_BASE}\n"
        f"remediation_head={head}\n\n"
        f"=== files changed since validated base ===\n{names}\n\n"
        f"=== full V5R changed source inventory ===\n{extra}\n"
    )
    (out_dir / "full_changed_source_inventory.txt").write_text(body, encoding="utf-8")


def validate_and_build(cwd: Path, evidence: Path) -> dict:
    py = _py(cwd)
    env = os.environ.copy()
    results: dict = {"started_utc": _utc_now()}

    before = _git(["status", "--porcelain"], cwd=cwd).strip()
    (evidence / "clean_build_git_status_before_build.txt").write_text(before + "\n", encoding="utf-8")
    if before:
        raise SystemExit("GIT_STATUS_PORCELAIN_BEFORE_BUILD not empty")

    compileall = _run([str(py), "-m", "compileall", "-q", "."], cwd=cwd, check=False)
    results["compileall_exit"] = compileall.returncode

    pytest = _run([str(py), "-m", "pytest", "-q", "--tb=no"], cwd=cwd, check=False)
    results["pytest_exit"] = pytest.returncode
    results["pytest_tail"] = (pytest.stdout or "")[-2000:]
    tc = [ln for ln in (pytest.stdout or "").splitlines() if "passed" in ln]
    results["pytest_summary"] = tc[-1] if tc else ""

    core = _run([str(py), str(cwd / "check_active_alpha_core.py")], cwd=cwd, check=False)
    results["core_check_exit"] = core.returncode

    if compileall.returncode or pytest.returncode or core.returncode:
        raise SystemExit(f"Validation failed: {results}")

    build_release = _run([str(py), str(cwd / "tools" / "build_v5r_standalone_exe.py")], cwd=cwd, check=False)
    results["release_build_exit"] = build_release.returncode
    if build_release.returncode:
        raise SystemExit("Release EXE build failed")

    build_test = _run([str(py), str(cwd / "tools" / "build_v5r_fail_closed_test_exe.py")], cwd=cwd, check=False)
    results["fail_closed_test_build_exit"] = build_test.returncode
    if build_test.returncode:
        raise SystemExit("Fail-closed test EXE build failed")

    after = _git(["status", "--porcelain"], cwd=cwd).strip()
    (evidence / "clean_build_git_status_after_build.txt").write_text(after + "\n", encoding="utf-8")

    release_exe = cwd / "dist" / "Marktanalyse.exe"
    test_exe = cwd / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"
    release_hash = _sha256(release_exe)
    test_hash = _sha256(test_exe)

    env_doc = {
        "clean_worktree_path": str(WORKTREE),
        "source_commit": _git(["rev-parse", "HEAD"], cwd=cwd).strip(),
        "validated_source_base": SOURCE_BASE,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "build_command_release": f"{py} tools/build_v5r_standalone_exe.py",
        "build_command_fail_closed_test": f"{py} tools/build_v5r_fail_closed_test_exe.py",
        "final_exe_sha256": release_hash,
        "fail_closed_test_exe_sha256": test_hash,
        "generated_at_utc": _utc_now(),
    }
    (evidence / "v5r_final_build_environment.json").write_text(json.dumps(env_doc, indent=2) + "\n", encoding="utf-8")
    (evidence / "v5r_final_build_command.txt").write_text(
        env_doc["build_command_release"] + "\n" + env_doc["build_command_fail_closed_test"] + "\n",
        encoding="utf-8",
    )
    log = (doc_path("CODEX_V5R_BUILD_LOG.txt")).read_text(encoding="utf-8") if (doc_path("CODEX_V5R_BUILD_LOG.txt")).is_file() else ""
    (evidence / "v5r_final_build_log.txt").write_text(log, encoding="utf-8")

    inv = {
        "dist/Marktanalyse.exe": {"sha256": release_hash, "size_bytes": release_exe.stat().st_size},
        "dist/Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe": {"sha256": test_hash, "size_bytes": test_exe.stat().st_size},
        "CLEAN_BUILD_WORKTREE": "YES",
        "GIT_STATUS_PORCELAIN_BEFORE_BUILD": "EMPTY",
    }
    (evidence / "v5r_final_dist_inventory.json").write_text(json.dumps(inv, indent=2) + "\n", encoding="utf-8")

    results.update(env_doc)
    return results


def runtime_smoke(cwd: Path, evidence: Path) -> int:
    py = _py(cwd)
    env = os.environ.copy()
    env["AA_DECISION_COCKPIT_SMOKE_TEST"] = "1"
    proc = subprocess.run(
        [str(cwd / "dist" / "Marktanalyse.exe")],
        cwd=cwd,
        env=env,
        check=False,
    )
    code = proc.returncode
    (evidence / "v5r_final_exe_smoke_exit.txt").write_text(f"SMOKE_EXIT_CODE: {code}\n", encoding="utf-8")
    return code


def copy_artifacts_to_root(cwd: Path) -> None:
    for name in ("Marktanalyse.exe", "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"):
        src = cwd / "dist" / name
        if src.is_file():
            shutil.copy2(src, ROOT / "dist" / name)
            shutil.copy2(src, ROOT / name if name == "Marktanalyse.exe" else ROOT / "dist" / name)
    release = ROOT / "dist" / "Marktanalyse.exe"
    if release.is_file():
        digest = _sha256(release)
        (ROOT / "dist" / "Marktanalyse.exe.sha256").write_text(f"{digest}  Marktanalyse.exe\n", encoding="ascii")
        (ROOT / "Marktanalyse.exe.sha256").write_text(f"{digest}  Marktanalyse.exe\n", encoding="ascii")


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    head = _git(["rev-parse", "HEAD"], cwd=ROOT).strip()
    ensure_worktree(head)
    write_git_patches(EVIDENCE, head)
    write_changed_source_inventory(EVIDENCE, head)
    results = validate_and_build(WORKTREE, EVIDENCE)
    smoke = runtime_smoke(WORKTREE, EVIDENCE)
    if smoke != 0:
        raise SystemExit(f"Release EXE smoke test failed: exit {smoke}")
    copy_artifacts_to_root(WORKTREE)
    summary = {**results, "smoke_exit_code": smoke, "clean_build_provenance": "PASS"}
    (EVIDENCE / "v5r_clean_release_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
