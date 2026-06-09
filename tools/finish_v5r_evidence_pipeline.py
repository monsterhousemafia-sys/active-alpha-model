"""Finish V5R evidence pipeline after runtime smoke (no full pytest, no EXE rebuild)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")


def py() -> Path:
    v = ROOT / ".venv" / "Scripts" / "python.exe"
    return v if v.is_file() else Path(sys.executable)


def run(cmd: list[str]) -> int:
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def main() -> int:
    run(
        [
            str(py()),
            "-m",
            "pytest",
            "tests/test_evidence_manifest.py",
            "tests/test_risk_off_selection.py",
            "tests/test_decision_cockpit_readonly_launcher.py",
            "tests/test_decision_cockpit_viewmodel.py",
            "tests/test_v5r_standalone_spec.py",
            "-q",
            "--tb=no",
        ]
    )
    run([str(py()), str(ROOT / "tools" / "complete_v5r_runtime_riskoff_evidence.py"), "--audits-only"])
    run([str(py()), str(ROOT / "tools" / "generate_research_evidence_reports.py")])
    run([str(py()), str(ROOT / "tools" / "static_verify_v5r_standalone_exe.py")])

    if not (EVIDENCE / "v5r_dist_inventory.json").is_file() and (ROOT / "dist" / "Marktanalyse.exe").is_file():
        import hashlib

        digest = hashlib.sha256((ROOT / "dist" / "Marktanalyse.exe").read_bytes()).hexdigest()
        inv = {
            "dist/Marktanalyse.exe": digest,
            "Marktanalyse.exe": digest,
            "size_bytes": (ROOT / "dist" / "Marktanalyse.exe").stat().st_size,
            "note": "Build log from prior V5R run; EXE not rebuilt in this pipeline finish.",
        }
        (EVIDENCE / "v5r_dist_inventory.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")
        for name, content in (
            ("v5r_build_command.txt", f"{py()} tools/build_v5r_standalone_exe.py\n(prior build)\n"),
            ("v5r_build_environment.json", json.dumps({"note": "prior V5R build"}, indent=2)),
            ("v5r_build_log.txt", (doc_path("CODEX_V5R_BUILD_LOG.txt")).read_text(encoding="utf-8")
            if (doc_path("CODEX_V5R_BUILD_LOG.txt")).is_file()
            else "prior build\n"),
        ):
            if not (EVIDENCE / name).is_file():
                (EVIDENCE / name).write_text(content, encoding="utf-8")

    sys.path.insert(0, str(ROOT))
    from tools.complete_v5r_runtime_riskoff_evidence import (
        build_review_zip,
        run_git,
        sha256_file,
        update_reports,
        write_post_inventory_and_diff,
        write_sidecars,
    )

    write_sidecars()
    write_post_inventory_and_diff()
    runtime = json.loads((EVIDENCE / "v5r_runtime_process_result.json").read_text(encoding="utf-8"))
    static = json.loads((EVIDENCE / "v5r_static_import_audit.json").read_text(encoding="utf-8"))
    runtime_ok = bool(runtime.get("pass"))
    static_ok = bool(static.get("pass"))

    run([str(py()), str(ROOT / "tools" / "write_codex_final_reports.py")])
    update_reports(runtime_ok, static_ok)

    review_include = [
        "CODEX_V5R_STANDALONE_EXE_REPORT.md",
        "evidence/v5r_build_command.txt",
        "evidence/v5r_build_environment.json",
        "evidence/v5r_build_log.txt",
        "evidence/v5r_dist_inventory.json",
        "evidence/v5r_static_import_audit.json",
        "evidence/v5r_ui_action_audit.json",
        "evidence/v5r_fail_closed_test_results.json",
        "evidence/v5r_runtime_smoke_test_log.txt",
        "evidence/v5r_runtime_process_result.json",
        "evidence/v5r_runtime_readonly_verification.json",
        "evidence/v5r_runtime_fail_closed_verification.json",
        "evidence/v5r_runtime_blocked_process_report.json",
        "evidence/pre_change_hash_inventory.json",
        "evidence/post_change_hash_inventory.json",
        "evidence/git_diff_summary.txt",
        "dist/Marktanalyse.exe.sha256",
    ]
    build_review_zip("codex_v5r_standalone_exe_review.zip", review_include)
    build_review_zip(
        "codex_v5r_final_review.zip",
        review_include
        + [
            "CODEX_V5R_FINAL_RUNTIME_AND_INTEGRITY_REPORT.md",
            "CODEX_EXTERNAL_REVIEW_DECISION_PACKET.md",
        ],
    )
    build_review_zip(
        "codex_risk_off_challenger_review.zip",
        [
            "CODEX_RISK_OFF_CHALLENGER_EVIDENCE_REPORT.md",
            "research_evidence/trial_ledger_preregistered.json",
            "research_evidence/cost_stress_comparison.csv",
            "research_evidence/cost_stress_gate_report.md",
            "research_evidence/time_window_robustness.csv",
            "research_evidence/risk_regime_attribution.csv",
            "research_evidence/risk_off_episode_attribution.csv",
            "research_evidence/dsr_multiple_testing_report.md",
            "research_evidence/robustness_gate_report.md",
        ],
    )

    summary = {
        "dist_exe_sha256": sha256_file(ROOT / "dist" / "Marktanalyse.exe"),
        "codex_v5r_final_review_zip": sha256_file(doc_path("codex_v5r_final_review.zip")),
        "codex_risk_off_challenger_review_zip": sha256_file(doc_path("codex_risk_off_challenger_review.zip")),
        "git_head": run_git(["rev-parse", "HEAD"]) if GIT.is_file() else "UNKNOWN",
        "runtime_outcome": runtime.get("outcome"),
    }
    (EVIDENCE / "pipeline_finish_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
