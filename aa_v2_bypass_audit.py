"""Static audit of controller helper scripts for completion bypass paths."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List

BYPASS_PATTERNS = (
    re.compile(r"complete_v1r2_phase\s*\("),
    re.compile(r"complete_v1_phase\s*\("),
    re.compile(r"seal_predecessor_review\s*\("),
)

DIRECT_STATE_WRITE = re.compile(
    r"save_automation_state\s*\(|"
    r'["\']current_executed_phase["\']\s*:'
)

ALLOWED_ORCHESTRATORS = {
    "run_authorized_phase_pipeline",
    "register_external_approval",
    "begin_authorized_phase",
    "record_phase_test_pass",
    "complete_authorized_phase",
}

TOOL_GLOB = (
    "tools/complete*.py",
    "tools/build*v*review*.py",
    "tools/bootstrap*v*.py",
)


def _scan_file(path: Path) -> List[str]:
    issues: List[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [f"unreadable: {exc}"]

    if "bypass removed" in text.lower() or "raise RuntimeError" in text:
        for pat in BYPASS_PATTERNS:
            if pat.search(text) and "raise RuntimeError" not in text:
                issues.append(f"calls blocked function via {pat.pattern}")
        if issues:
            return issues
        if path.name in {"complete_v1r2_run.py", "complete_v1_run.py", "complete_v1r_run.py"}:
            return []

    for pat in BYPASS_PATTERNS:
        if pat.search(text):
            issues.append(f"forbidden call pattern: {pat.pattern}")

    if "complete_authorized_phase" in text:
        authorized_orchestrator = "run_authorized_phase_pipeline" in text or (
            "register_external_approval" in text
            and "begin_authorized_phase" in text
            and "record_phase_test_pass" in text
        )
        if not authorized_orchestrator:
            issues.append("calls complete_authorized_phase outside authorized orchestrator")
        direct_state = bool(re.search(r'state\["current_executed_phase"\]', text))
        if direct_state and "remediate_expected_next" not in text:
            issues.append("direct automation_state.current_executed_phase write")

    if path.name.startswith("complete_v1") and path.name not in {
        "complete_v1r3_run.py",
        "complete_v2_run.py",
    }:
        if "run_authorized_phase_pipeline" not in text and "raise RuntimeError" not in text:
            issues.append("legacy completion orchestrator without authorized pipeline")

    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "complete_v1_phase":
                    issues.append("ast: complete_v1_phase call")
    except SyntaxError:
        pass

    return issues


def audit_helper_scripts(root: Path) -> Dict[str, Any]:
    root = Path(root)
    findings: List[Dict[str, Any]] = []
    scanned: List[str] = []
    seen: set[str] = set()

    for pattern in TOOL_GLOB:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)
            scanned.append(rel)
            issues = _scan_file(path)
            if issues:
                findings.append({"path": rel, "issues": issues})

    return {
        "ok": len(findings) == 0,
        "scanned_files": scanned,
        "findings": findings,
        "blocker": None if not findings else "UNREVIEWED_CONTROLLER_HELPER_BYPASS",
    }
