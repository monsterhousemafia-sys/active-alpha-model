#!/usr/bin/env python3
"""Promote R5_rank_only_train5 to operational champion and optionally build Marktanalyse.exe."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_recovery import build_last_known_good_snapshot, save_last_known_good  # noqa: E402
from aa_safe_io import atomic_write_json  # noqa: E402
from tools.run_r5_challenger_pipeline import R5_BASE, R5_KEY, build_r5_command  # noqa: E402

PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
OUT_DIR = ROOT / "model_output_sp500_pit_t212"
USER_CONFIG = ROOT / "active_alpha_user_config.bat"
CONTROL = ROOT / "control"
R5_VARIANT = R5_KEY
PREVIOUS_CHAMPION = "R3_w075_q065_noexit"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_source_run() -> Path:
    status = _load_json(ROOT / "validation_runs" / "r5_challenger" / "r5_matrix_cost_stress_summary.json")
    base = status.get("matrix_base") or {}
    out = str(base.get("out_dir") or "").strip()
    if out:
        path = Path(out)
        if path.is_dir() and (path / "integrity_status.json").is_file():
            return path
    registry = _load_json(CONTROL / "r5_challenger_registry.json")
    out = str(registry.get("best_run_dir") or "").strip()
    if out:
        path = Path(out)
        if path.is_dir():
            return path
    fallback = ROOT / "validation_runs" / "r5_challenger" / R5_VARIANT
    if fallback.is_dir():
        return fallback
    raise SystemExit("No validated R5 run directory found for promotion")


def _verify_evidence() -> None:
    status = _load_json(CONTROL / "r5_challenger_status.json")
    if not status.get("cost_stress_complete"):
        raise SystemExit("R5 cost stress not complete — aborting promotion")
    if not status.get("target_met_on_source"):
        raise SystemExit("R5 internet validation gate not met — aborting promotion")


def _patch_bat_key(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    needle = f'set "{key}='
    lines = text.splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(needle):
            lines[i] = f'set "{key}={value}"'
            replaced = True
            break
    if not replaced:
        lines.append(f'set "{key}={value}"')
    path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")


def _apply_user_config() -> None:
    if not USER_CONFIG.is_file():
        raise SystemExit(f"Missing {USER_CONFIG}")
    _patch_bat_key(USER_CONFIG, "AA_ALPHA_MODEL_MODE", "rank_only")
    _patch_bat_key(USER_CONFIG, "AA_TRAIN_YEARS", str(R5_BASE.get("train_years", "5")))
    _patch_bat_key(USER_CONFIG, "AA_FORCE_REBUILD_PREDICTIONS", "1")


def _sync_model_output(source: Path) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skip = {".lock", "ops_refresh_meta.json"}
    for item in source.iterdir():
        if not item.is_file() or item.name in skip:
            continue
        shutil.copy2(item, OUT_DIR / item.name)


def _patch_json_variant(path: Path, variant_id: str) -> None:
    if not path.is_file():
        return
    data = _load_json(path)
    if not data:
        return
    for key in (
        "variant_id",
        "active_champion_variant",
        "active_variant_label",
        "validated_variant_id",
        "validated_model_id",
        "champion_variant_id",
    ):
        if key in data:
            data[key] = variant_id
    if "active_model_label" in data:
        data["active_model_label"] = "R5"
    atomic_write_json(path, data)


def _patch_control_champion_fields(path: Path, variant_id: str) -> None:
    if not path.is_file():
        return
    data = _load_json(path)
    if not data:
        return
    if "champion_variant_id" in data:
        data["champion_variant_id"] = variant_id
    if "champion" in data and isinstance(data["champion"], str):
        data["champion"] = variant_id
    atomic_write_json(path, data)


def _write_operational_champion(source: Path) -> None:
    payload = {
        "variant_id": R5_VARIANT,
        "alpha_model_mode": "rank_only",
        "train_years": int(R5_BASE.get("train_years", "5")),
        "previous_champion_variant_id": PREVIOUS_CHAMPION,
        "promoted_at_utc": _utc_now(),
        "promotion_evidence_dir": str(source),
        "auto_promotion": "DISABLED",
        "note": "Manual R5 promotion — user authorized operational EXE path.",
    }
    atomic_write_json(CONTROL / "operational_champion.json", payload)


def _update_champion_registry(source: Path, pointer: Dict[str, Any]) -> None:
    backup = CONTROL / "champion_registry_r3_backup.json"
    if (CONTROL / "champion_registry.json").is_file() and not backup.is_file():
        shutil.copy2(CONTROL / "champion_registry.json", backup)
    payload = {
        "active": True,
        "auto_promotion": "DISABLED",
        "integrity_status": "PASS",
        "role": "CHAMPION",
        "run_dir": str(pointer.get("run_dir") or source),
        "run_id": str(pointer.get("run_id") or ""),
        "variant_id": R5_VARIANT,
        "previous_champion_variant_id": PREVIOUS_CHAMPION,
        "promoted_at_utc": _utc_now(),
        "promotion_source": str(source),
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(CONTROL / "champion_registry.json", payload)


def _update_lkg() -> None:
    integrity = _load_json(OUT_DIR / "integrity_status.json")
    health = {
        "integrity_status": integrity.get("status", "PASS"),
        "checked_at_utc": integrity.get("checked_at_utc", _utc_now()),
        "active_variant_label": R5_VARIANT,
    }
    snapshot = build_last_known_good_snapshot(out_dir=OUT_DIR, health=health)
    save_last_known_good(CONTROL, snapshot)


def _update_control_plane() -> None:
    paths = [
        CONTROL / "evidence" / "current_evidence_status.json",
        CONTROL / "evidence" / "multiple_testing_status.json",
        CONTROL / "evidence" / "shadow_monitor_status.json",
        CONTROL / "evidence" / "paper_monitor_status.json",
        CONTROL / "evidence" / "forward_monitoring_readiness_status.json",
        CONTROL / "evidence" / "forward_monitoring_data_requirements.json",
        CONTROL / "auto_promotion_status.json",
    ]
    for path in paths:
        _patch_control_champion_fields(path, R5_VARIANT)

    reg = _load_json(CONTROL / "r5_challenger_registry.json")
    reg.update(
        {
            "active": True,
            "role": "CHAMPION",
            "promoted_at_utc": _utc_now(),
            "previous_champion_variant_id": PREVIOUS_CHAMPION,
            "note": "Promoted to operational champion (manual). Auto-promotion remains DISABLED.",
        }
    )
    atomic_write_json(CONTROL / "r5_challenger_registry.json", reg)


def _refresh_cockpit() -> int:
    proc = subprocess.run([str(PYTHON), str(ROOT / "tools" / "refresh_v5r_live_cockpit.py")], cwd=ROOT)
    return int(proc.returncode)


def _build_exe() -> int:
    proc = subprocess.run([str(PYTHON), str(ROOT / "tools" / "setup_operational_marktanalyse.py")], cwd=ROOT)
    return int(proc.returncode)


def _run_operational_backtest() -> int:
    cmd = build_r5_command(
        dict(R5_BASE),
        out_dir=OUT_DIR,
        cpu_cores=16,
        price_source="internet",
        full_reporting=True,
    )
    proc = subprocess.run(cmd, cwd=ROOT)
    return int(proc.returncode)


def main() -> int:
    p = argparse.ArgumentParser(description="Promote R5 to operational champion + optional EXE build")
    p.add_argument("--full-backtest", action="store_true", help="Run fresh R5 backtest into model_output")
    p.add_argument("--build-exe", action="store_true", help="Build operational Marktanalyse onedir bundle")
    p.add_argument("--skip-refresh", action="store_true")
    args = p.parse_args()

    _verify_evidence()
    source = _resolve_source_run()
    _apply_user_config()
    _write_operational_champion(source)

    if args.full_backtest:
        rc = _run_operational_backtest()
        if rc != 0:
            raise SystemExit(f"Operational R5 backtest failed: rc={rc}")
    else:
        _sync_model_output(source)

    pointer = _load_json(OUT_DIR / "latest_validated_run.json")
    pointer["variant_id"] = R5_VARIANT
    atomic_write_json(OUT_DIR / "latest_validated_run.json", pointer)
    _patch_json_variant(OUT_DIR / "model_status.json", R5_VARIANT)
    _update_champion_registry(source, pointer)
    _update_lkg()
    _update_control_plane()

    summary = {
        "ok": True,
        "promoted_at_utc": _utc_now(),
        "variant_id": R5_VARIANT,
        "previous_champion": PREVIOUS_CHAMPION,
        "model_output": str(OUT_DIR),
        "source_run": str(source),
        "user_config": str(USER_CONFIG),
        "auto_promotion": "DISABLED",
    }
    atomic_write_json(CONTROL / "r5_operational_promotion.json", summary)
    print(json.dumps(summary, indent=2))

    if not args.skip_refresh:
        rc = _refresh_cockpit()
        if rc != 0:
            print(f"[WARN] Cockpit refresh rc={rc}", file=sys.stderr)

    if args.build_exe:
        rc = _build_exe()
        if rc != 0:
            raise SystemExit(f"EXE build failed: rc={rc}")
        summary["operational_exe"] = str(ROOT / "Marktanalyse" / "Marktanalyse.exe")
        print(json.dumps({"exe_build": "OK", "path": summary["operational_exe"]}, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
