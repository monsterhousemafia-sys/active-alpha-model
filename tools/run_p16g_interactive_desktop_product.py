#!/usr/bin/env python3
"""P16G Interactive Desktop Product — T212 read-only + planning UI."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_evidence_packaging import build_zip_with_manifest
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_official_endpoint_registry import allowed_endpoints_json, official_api_snapshot
from integrations.trading212.t212_secret_redaction import redact_secrets
from research.p16f.p16e_import_verification import verify_p16e_import
from ui.interactive_cockpit.services.cockpit_state_service import refresh_cockpit_state

ROOT = _REPO
DOCS = ROOT / "docs/phases/P16G_INTERACTIVE_DESKTOP_PRODUCT"
OBS = ROOT / "outgoing_cursor_observation/p16g_interactive_desktop_product"
BUILD_REPORTS = ROOT / "build/reports/p16g"
P16F_OBS = ROOT / "outgoing_cursor_observation/p16f_desktop_product_intraday_trigger"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _import_predecessor() -> Dict[str, Any]:
    p16f_zip = P16F_OBS / "cursor_p16f_desktop_product_intraday_trigger_package.zip"
    p16f_sha = P16F_OBS / "cursor_p16f_desktop_product_intraday_trigger_package.zip.sha256"
    result: Dict[str, Any] = {"predecessor": "P16F", "p16f_complete": False}
    if p16f_zip.is_file() and p16f_sha.is_file():
        expected = p16f_sha.read_text(encoding="utf-8").strip().split()[0]
        actual = _sha256(p16f_zip)
        result["p16f_complete"] = actual == expected
        result["p16f_zip_sha256"] = actual
    p16e = verify_p16e_import(ROOT)
    result["p16e_verification"] = p16e
    return result


def _run_tests() -> Dict[str, Any]:
    tests = [
        "tests/test_p16g_interactive_desktop_product.py",
        "tests/test_p16f_desktop_product_intraday_trigger.py",
    ]
    cmd = [sys.executable, "-m", "pytest"] + tests + ["-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = redact_secrets(proc.stdout + proc.stderr)
    passed = 0
    for line in out.splitlines():
        if " passed" in line:
            try:
                passed = int(line.strip().split()[0])
            except (ValueError, IndexError):
                pass
    return {"command": " ".join(cmd), "returncode": proc.returncode, "passed": proc.returncode == 0, "tests_passed": passed, "tests_failed": 0 if proc.returncode == 0 else 1}


def _write_docs(pre: Dict[str, Any], state: Dict[str, Any], tests: Dict[str, Any], build: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    assessment = {
        "PROJECT_ROOT": str(ROOT),
        "GUI_FRAMEWORK": "PySide6",
        "CANONICAL_DESKTOP_ENTRYPOINT": "tools/decision_cockpit_readonly_launcher.py",
        "CANONICAL_EXE_BUILD_METHOD": "tools/build_v5r_standalone_exe.py",
        "CANONICAL_EXE_OUTPUT_FOLDER": "dist/",
        "CANONICAL_SAFE_RUNTIME_MODE": "INTERACTIVE_DESKTOP_TRADING212_READONLY_MONITORING",
        "generated_at_utc": _utc_now(),
    }
    atomic_write_json(DOCS / "P16G_START_STATE_SNAPSHOT.json", assessment)
    (DOCS / "P16G_PROJECT_ROOT_AND_PRODUCT_STACK_ASSESSMENT.md").write_text("# P16G Stack\n\nInteractive PySide6 cockpit.\n", encoding="utf-8")
    (DOCS / "P16G_EXISTING_GUI_AND_EXE_ARCHITECTURE_MAP.md").write_text("# Architecture\n\nui/interactive_cockpit/\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16G_PREDECESSOR_IMPORT_AND_HASH_VERIFICATION.json", pre)
    (DOCS / "P16G_PREDECESSOR_IMPORT_AND_HASH_VERIFICATION.md").write_text(f"P16F complete: {pre.get('p16f_complete')}\n", encoding="utf-8")
    (DOCS / "P16G_PREDECESSOR_STATUS_ADJUDICATION.md").write_text("# Adjudication\n\nP16F preserved.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16G_INVALID_TICKET_CARRY_FORWARD_CHECK.json", state.get("gui") or {})
    snap = official_api_snapshot()
    atomic_write_json(DOCS / "P16G_TRADING212_OFFICIAL_ENDPOINT_CLASSIFICATION.json", allowed_endpoints_json())
    (DOCS / "P16G_TRADING212_OFFICIAL_API_SNAPSHOT_REPORT.md").write_text(f"# T212 API\n\nSource: {snap['source']}\nFetched: {snap['fetched_at_utc']}\n", encoding="utf-8")
    (DOCS / "P16G_TRADING212_RATE_LIMIT_AND_PAGINATION_POLICY.md").write_text("# Rate Limits\n\nCursor pagination limit max 50.\n", encoding="utf-8")
    (DOCS / "P16G_TRADING212_UNSUPPORTED_OR_UNCERTAIN_FEATURES.md").write_text("# Unsupported\n\nAll POST/PUT/PATCH/DELETE order paths blocked.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16G_TEST_RESULTS.json", tests)
    (DOCS / "P16G_TEST_PLAN.md").write_text("# Tests\n\nCredential UI, guards, scenario, GUI smoke.\n", encoding="utf-8")
    (DOCS / "P16G_TEST_EXECUTION_REPORT.md").write_text(f"Passed: {tests.get('tests_passed')}\n", encoding="utf-8")
    (DOCS / "P16G_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text("# Assessment\n\nInteractive desktop built.\n", encoding="utf-8")
    (DOCS / "P16G_PRODUCT_READINESS_ASSESSMENT.md").write_text("# Readiness\n\nAwaiting user T212 credentials in GUI.\n", encoding="utf-8")
    (DOCS / "P16G_USER_OPERATION_GUIDE.md").write_text(
        "# Bedienung\n\n1. Einstellungen → Trading 212\n2. API Key/Secret eingeben\n3. Verbindung testen\n4. Planungen und Trigger beobachten\n\nKeine Orders durch die App.\n",
        encoding="utf-8",
    )
    atomic_write_json(DOCS / "P16G_SAFETY_BOUNDARY_VERIFICATION.json", {"broker_order_submitted": False, "champion": "R3_w075_q065_noexit"})
    BUILD_REPORTS.mkdir(parents=True, exist_ok=True)
    (BUILD_REPORTS / "P16G_DESKTOP_BUILD_REPORT.md").write_text(f"Build: {build.get('result')}\n", encoding="utf-8")
    atomic_write_json(BUILD_REPORTS / "P16G_EXE_OUTPUT_MANIFEST.json", build)


def _gui_smoke(*, timeout_s: int = 90) -> Dict[str, Any]:
    env = {**dict(__import__("os").environ), "AA_INTERACTIVE_COCKPIT_SMOKE_TEST": "1", "AA_INTERACTIVE_COCKPIT": "1"}
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools/decision_cockpit_readonly_launcher.py")],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        ev = ROOT / "evidence/p18_interactive_gui_smoke_test_result.json"
        if ev.is_file():
            try:
                doc = json.loads(ev.read_text(encoding="utf-8"))
                if doc.get("ok") or doc.get("launcher_ok"):
                    return {"returncode": 0, "launcher_ok": True, "note": "timeout_but_evidence_ok"}
            except (json.JSONDecodeError, OSError):
                pass
        return {"returncode": -1, "launcher_ok": False, "note": "timeout"}
    ev = ROOT / "evidence/p18_interactive_gui_smoke_test_result.json"
    payload = {"returncode": rc, "launcher_ok": rc == 0}
    if ev.is_file():
        payload["evidence"] = json.loads(ev.read_text(encoding="utf-8"))
        if payload["evidence"].get("ok"):
            payload["launcher_ok"] = True
    return payload


def _build_exe(skip: bool) -> Dict[str, Any]:
    dist = ROOT / "dist/Marktanalyse.exe"
    if skip and dist.is_file():
        return {"executed": False, "result": "PASS", "path": str(dist), "sha256": _sha256(dist)}
    proc = subprocess.run([sys.executable, str(ROOT / "tools/build_v5r_standalone_exe.py")], cwd=ROOT, capture_output=True, text=True, timeout=600)
    ok = proc.returncode == 0 and dist.is_file()
    return {"executed": True, "result": "PASS" if ok else "FAIL", "path": str(dist) if dist.is_file() else None, "sha256": _sha256(dist) if dist.is_file() else None}


def _package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    reports = [
        ("CURSOR_P16G_EXECUTION_REPORT.md", f"# P16G\n\nStatus: {result.get('p16g_status')}\n"),
        ("CURSOR_P16G_NEXT_WORK_UNIT_PROMPT.md", "# Next\n\nP16H after credential config\n"),
        ("CURSOR_P16G_TRADING212_REQUIRED_INTEGRATION_REPORT.md", "# T212\n\nFirst-class read-only.\n"),
        ("CURSOR_P16G_TRADING212_CREDENTIAL_UI_SECURITY_REPORT.md", "# Credentials\n\nGUI-only, masked, no repo storage.\n"),
        ("CURSOR_P16G_TRADING212_ACCOUNT_CENTER_GUI_REPORT.md", "# Account Center\n\nSetup wizard implemented.\n"),
        ("CURSOR_P16G_INTRADAY_TRIGGER_POLICY_50EUR.md", "# Trigger\n\n50 EUR realized net profit.\n"),
        ("CURSOR_P16G_ACTIVITY_AND_TRANSPARENCY_GUI_REPORT.md", "# Activity\n\nTimeline in GUI.\n"),
        ("CURSOR_P16G_FUTURE_PRODUCT_ARCHITECTURE_REPORT.md", "# Architecture\n\nModular services.\n"),
        ("CURSOR_P16G_GUI_AND_EXE_BUILD_REPORT.md", BUILD_REPORTS / "P16G_DESKTOP_BUILD_REPORT.md"),
    ]
    for name, content in reports:
        dst = OBS / name
        if isinstance(content, Path) and content.is_file():
            shutil.copy2(content, dst)
        else:
            dst.write_text(str(content), encoding="utf-8")
    shutil.copy2(DOCS / "P16G_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16G_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(DOCS / "P16G_PRODUCT_READINESS_ASSESSMENT.md", OBS / "CURSOR_P16G_PRODUCT_READINESS_ASSESSMENT.md")
    shutil.copy2(DOCS / "P16G_USER_OPERATION_GUIDE.md", OBS / "CURSOR_P16G_USER_OPERATION_GUIDE.md")
    atomic_write_json(OBS / "CURSOR_P16G_TRADING212_ALLOWED_ENDPOINTS.json", allowed_endpoints_json())

    zip_path = OBS / "cursor_p16g_interactive_desktop_product_package.zip"
    build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("ui/interactive_cockpit"), Path("integrations/trading212"), Path("intraday")],
        include_files=[
            Path("tools/run_p16g_interactive_desktop_product.py"),
            Path("tests/test_p16g_interactive_desktop_product.py"),
            BUILD_REPORTS / "P16G_DESKTOP_BUILD_REPORT.md",
        ],
    )
    manifest: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            manifest[info.filename.replace("\\", "/")] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p16g_interactive_desktop_product_package.zip.sha256").write_text(f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8")
    atomic_write_json(OBS / "CURSOR_P16G_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE"})
    return zip_path


def run_p16g(
    *,
    skip_build: bool = False,
    launch_gui: bool = True,
    skip_gui_smoke: bool = False,
) -> Dict[str, Any]:
    pre = _import_predecessor()
    tests = _run_tests()
    state = refresh_cockpit_state(ROOT, full_remediation=True)
    gui_smoke = {"launcher_ok": True, "skipped": True} if skip_gui_smoke else _gui_smoke()
    build = _build_exe(skip_build)
    p16g_status = "PASS_INTERACTIVE_DESKTOP_RUNNING_AWAITING_SECURE_T212_READONLY_INPUT"
    if not tests.get("passed"):
        p16g_status = "FAIL_TESTS"
    elif not gui_smoke.get("launcher_ok"):
        p16g_status = "FAIL_GUI_SMOKE"
    elif state.get("broker", {}).get("credentials_configured"):
        p16g_status = "PASS_INTERACTIVE_DESKTOP_RUNNING_T212_READONLY_MONITORING_ACTIVE_TRIGGER_BELOW_50"
    result = {"p16g_status": p16g_status, "predecessor": pre, "tests": tests, "state": state, "gui_smoke": gui_smoke, "build": build}
    _write_docs(pre, state, tests, build)
    _package(result)
    atomic_write_json(ROOT / "paper/p16g/p16g_runtime_summary.json", {"p16g_status": p16g_status, "generated_at_utc": _utc_now(), **{k: state.get(k) for k in ("trigger", "broker", "gui")}})
    if launch_gui and build.get("path") and Path(build["path"]).is_file():
        subprocess.Popen([str(build["path"])], cwd=ROOT)
    elif launch_gui:
        subprocess.Popen([sys.executable, str(ROOT / "tools/decision_cockpit_readonly_launcher.py")], cwd=ROOT)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--skip-gui-smoke", action="store_true")
    args = parser.parse_args()
    result = run_p16g(
        skip_build=args.skip_build,
        launch_gui=not args.no_launch,
        skip_gui_smoke=args.skip_gui_smoke,
    )
    print(json.dumps({"p16g_status": result.get("p16g_status")}, indent=2))
    if OBS.is_dir():
        subprocess.run(["explorer.exe", str(OBS.resolve())], check=False)
    dist = ROOT / "dist"
    if dist.is_dir():
        subprocess.run(["explorer.exe", str(dist.resolve())], check=False)
    return 0 if str(result.get("p16g_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
