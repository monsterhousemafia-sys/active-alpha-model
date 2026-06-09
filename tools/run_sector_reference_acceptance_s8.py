"""Phase S8 — operational acceptance (DoD + manual plan M1–M6, read-only)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_JSON = "evidence/sector_reference_acceptance_s8.json"
EVIDENCE_MD = "evidence/sector_reference_acceptance_s8.md"
REFRESH_LATEST = "evidence/sector_reference_refresh_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _check(name: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"id": name, "pass": bool(ok), "detail": detail}


def _file_contains(path: Path, needle: str) -> bool:
    if not path.is_file():
        return False
    try:
        return needle in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def run_acceptance(root: Path, *, run_pytest: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []

    os_bat = root / "active_alpha_marktanalyse_os.bat"
    settings_bat = root / "active_alpha_settings.bat"
    m1 = _file_contains(os_bat, "AA_SECTOR_REFERENCE_MODE=auto") and _file_contains(
        settings_bat, "AA_SECTOR_REFERENCE_MODE=auto"
    )
    checks.append(_check("M1_os_env", m1, "active_alpha_marktanalyse_os.bat + settings"))

    live_ops = root / "analytics" / "live_trading_operations.py"
    m2 = _file_contains(live_ops, "ensure_sector_reference_fresh") and _file_contains(
        live_ops, "run_daily_live_cycle"
    )
    checks.append(_check("M2_live_daily_sector_hook", m2, str(live_ops)))

    from aa_sector_reference import (
        audit_sp500_snapshot_sector_columns,
        build_sector_rollout_summary,
        champion_sector_coverage,
        load_sector_reference_status,
        resolve_reference_path,
    )

    try:
        from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
    except Exception:
        CHAMPION_SYMBOLS = ()

    ref_path = resolve_reference_path(root)
    cov = champion_sector_coverage(root, CHAMPION_SYMBOLS)
    m3 = ref_path.is_file() and bool(cov.get("ok"))
    checks.append(
        _check(
            "M3_reference_and_champion",
            m3,
            f"ref={ref_path.is_file()} champion={cov.get('mapped_count')}/{cov.get('symbol_count')}",
        )
    )

    dash_txt = root / "live_pilot" / "confirmed_execution" / "live_trading_dashboard.txt"
    dash_svc = root / "ui" / "live_trading_dashboard" / "service.py"
    m4 = _file_contains(dash_svc, "Sector reference") or _file_contains(dash_txt, "Sector reference")
    checks.append(_check("M4_dashboard_sector_line", m4, f"txt={dash_txt.is_file()}"))

    daily_bat = root / "1_live_daily_sync.bat"
    m5 = _file_contains(daily_bat, "live_trading_operations") and _file_contains(
        daily_bat, "active_alpha_marktanalyse_os.bat"
    )
    checks.append(_check("M5_daily_bat_wiring", m5, str(daily_bat)))

    test_dir = root / "tests"
    sector_tests = sorted(test_dir.glob("test_sector_reference*.py")) if test_dir.is_dir() else []
    m6 = len(sector_tests) >= 6
    checks.append(_check("M6_test_suite_present", m6, f"{len(sector_tests)} sector test modules"))

    spec = root / "build" / "decision_cockpit" / "Marktanalyse.spec"
    dod_exe = _file_contains(spec, "aa_sector_reference")
    checks.append(_check("DoD5_exe_spec_hiddenimport", dod_exe, str(spec)))

    agents = root / "AGENTS.md"
    dod_agents = _file_contains(agents, "sector_reference.csv") and _file_contains(agents, "SECTOR_MAP")
    checks.append(_check("DoD6_agents_lookup_chain", dod_agents, str(agents)))

    constants = root / "aa_constants.py"
    dod_delegate = _file_contains(constants, "lookup_sector") or _file_contains(constants, "aa_sector_reference")
    checks.append(_check("DoD5_ticker_to_sector_delegates", dod_delegate, "aa_constants.ticker_to_sector"))

    snapshot = audit_sp500_snapshot_sector_columns(root)
    status = load_sector_reference_status(root)
    rollout = build_sector_rollout_summary(root)

    pytest_ok = None
    if run_pytest:
        import subprocess

        py = root / ".venv" / "Scripts" / "python.exe"
        if not py.is_file():
            py = Path(sys.executable)
        proc = subprocess.run(
            [
                str(py),
                "-m",
                "pytest",
                "tests/test_sector_reference.py",
                "tests/test_sector_reference_s2.py",
                "tests/test_sector_reference_s3.py",
                "tests/test_sector_reference_s4.py",
                "tests/test_sector_reference_s5.py",
                "tests/test_sector_reference_s6.py",
                "tests/test_sector_reference_s7.py",
                "-q",
                "--tb=no",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        pytest_ok = proc.returncode == 0
        checks.append(
            _check(
                "DoD_tests_pytest",
                pytest_ok,
                (proc.stdout or proc.stderr or "")[-400:],
            )
        )

    all_pass = all(c["pass"] for c in checks)
    return {
        "schema_version": 1,
        "phase": "S8",
        "generated_at_utc": _utc_now(),
        "status": "PASS" if all_pass else "FAIL",
        "checks": checks,
        "champion_coverage": cov,
        "rollout_summary": rollout,
        "sector_reference_status": status,
        "sp500_snapshot_audit": snapshot,
        "reference_path": str(ref_path),
        "manual_plan_mapping": {
            "M1": "M1_os_env",
            "M2": "M2_live_daily_sector_hook",
            "M3": "M3_reference_and_champion",
            "M4": "M4_dashboard_sector_line",
            "M5": "M5_daily_bat_wiring",
            "M6": "M6_test_suite_present",
        },
    }


def _render_md(report: Dict[str, Any]) -> str:
    lines = [
        "# Sector Reference — Phase S8 Acceptance",
        "",
        f"- generated_at_utc: {report.get('generated_at_utc')}",
        f"- status: **{report.get('status')}**",
        "",
        "## Checks",
        "",
    ]
    for c in report.get("checks") or []:
        mark = "PASS" if c.get("pass") else "FAIL"
        lines.append(f"- [{mark}] `{c.get('id')}` — {c.get('detail', '')}")
    cov = report.get("champion_coverage") or {}
    lines.extend(
        [
            "",
            "## Champion coverage",
            "",
            f"- mapped: {cov.get('mapped_count')}/{cov.get('symbol_count')}",
            f"- unknown: {cov.get('unknown_tickers') or []}",
            "",
            "## Rollout",
            "",
            f"- rollout_status: {(report.get('rollout_summary') or {}).get('rollout_status')}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    from aa_safe_io import atomic_write_json

    p = argparse.ArgumentParser(description="Sector reference S8 acceptance (DoD + M1–M6).")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--write-evidence", action="store_true")
    p.add_argument("--pytest", action="store_true", help="Run sector_reference pytest subset.")
    p.add_argument("--sync-refresh-latest", action="store_true", help="Copy status to evidence/sector_reference_refresh_latest.json")
    args = p.parse_args()
    root = args.root.resolve()

    report = run_acceptance(root, run_pytest=args.pytest)
    if args.write_evidence:
        atomic_write_json(root / EVIDENCE_JSON, report)
        (root / EVIDENCE_MD).write_text(_render_md(report), encoding="utf-8")
        print(f"Evidence: {root / EVIDENCE_JSON}")
        print(f"Report:   {root / EVIDENCE_MD}")

    if args.sync_refresh_latest:
        st_path = root / "control" / "sector_reference_status.json"
        if st_path.is_file():
            payload = json.loads(st_path.read_text(encoding="utf-8"))
            payload["synced_from"] = str(st_path)
            payload["synced_at_utc"] = _utc_now()
            atomic_write_json(root / REFRESH_LATEST, payload)
            print(f"Synced: {root / REFRESH_LATEST}")

    failed = [c["id"] for c in report.get("checks", []) if not c.get("pass")]
    if failed:
        print(f"FAIL checks: {', '.join(failed)}")
    else:
        print("S8 acceptance: PASS")
    print(f"status: {report.get('status')}")
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
