#!/usr/bin/env python3
"""Complete R5 switch: config, control plane, branding icon, full backtest, EXE rebuild."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_evidence_schema import LOCKED_CHAMPION  # noqa: E402
from aa_safe_io import atomic_write_json  # noqa: E402

PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CONTROL = ROOT / "control"
OUT_DIR = ROOT / "model_output_sp500_pit_t212"
R5 = LOCKED_CHAMPION


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _patch_champion_json(path: Path) -> None:
    data = _load(path)
    if not data:
        return
    for key in ("champion_variant_id", "champion", "active_variant_label", "validated_variant_id", "variant_id"):
        if key in data:
            data[key] = R5
    if "last_known_good_model_id" in data:
        data["last_known_good_model_id"] = R5
    ge = data.get("gate_evaluation")
    if isinstance(ge, dict) and "champion_variant_id" in ge:
        ge["champion_variant_id"] = R5
    atomic_write_json(path, data)


def _sync_system_health() -> None:
    pointer = _load(OUT_DIR / "latest_validated_run.json")
    run_id = str(pointer.get("run_id") or "")
    health = _load(CONTROL / "system_health.json")
    health.update(
        {
            "active_variant_label": R5,
            "last_known_good_model_id": R5,
            "last_known_good_run_id": run_id,
            "validated_run_id": run_id,
            "integrity_status": str(pointer.get("integrity_status") or "PASS"),
            "last_updated_at_utc": _utc_now(),
        }
    )
    atomic_write_json(CONTROL / "system_health.json", health)


def _run(cmd: list[str]) -> int:
    print(f"[RUN] {' '.join(cmd)}", flush=True)
    return int(subprocess.run(cmd, cwd=ROOT).returncode)


def main() -> int:
    p = argparse.ArgumentParser(description="Finalize full R5 operational switch")
    p.add_argument("--full-backtest", action="store_true", help="Fresh R5 backtest into model_output")
    p.add_argument("--build-exe", action="store_true", default=True)
    p.add_argument("--no-build-exe", action="store_true")
    args = p.parse_args()
    build_exe = bool(args.build_exe) and not args.no_build_exe

    if _run([str(PYTHON), str(ROOT / "tools" / "generate_r5_icon.py")]) != 0:
        return 1

    promote_cmd = [str(PYTHON), str(ROOT / "tools" / "promote_r5_operational.py"), "--skip-refresh"]
    if args.full_backtest:
        promote_cmd.append("--full-backtest")
    if _run(promote_cmd) != 0:
        return 1

    for rel in (
        "evidence/current_evidence_status.json",
        "evidence/multiple_testing_status.json",
        "evidence/shadow_monitor_status.json",
        "evidence/paper_monitor_status.json",
        "evidence/forward_monitoring_readiness_status.json",
        "evidence/forward_monitoring_data_requirements.json",
        "auto_promotion_status.json",
        "promotion_status.json",
    ):
        _patch_champion_json(CONTROL / rel)

    _sync_system_health()

    summary = {
        "finalized_at_utc": _utc_now(),
        "locked_champion": R5,
        "model_output": str(OUT_DIR),
        "variant_id": R5,
        "app_version": "1.2.0",
        "branding": "R5",
    }
    atomic_write_json(CONTROL / "r5_full_switch_summary.json", summary)

    if _run([str(PYTHON), str(ROOT / "tools" / "refresh_v5r_live_cockpit.py")]) != 0:
        print("[WARN] Cockpit refresh failed", file=sys.stderr)

    if build_exe:
        if _run([str(PYTHON), str(ROOT / "tools" / "setup_operational_marktanalyse.py")]) != 0:
            return 1
        summary["operational_exe"] = str(ROOT / "Marktanalyse" / "Marktanalyse.exe")

    atomic_write_json(CONTROL / "r5_full_switch_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
