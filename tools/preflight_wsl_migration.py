#!/usr/bin/env python3
"""WSL migration preflight — manifest, cache inventory, M1 gate (safe while Windows run active)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE = ROOT / "evidence" / "r0_migration"
MANIFEST_PATH = EVIDENCE / "wsl_migration_manifest.json"
STATE_PATH = EVIDENCE / "wsl_migration_state.json"
CHECKLIST_PATH = ROOT / "control" / "r0_migration" / "wsl_migration_checklist.json"

VARIANTS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)
M1_VARIANT = "M1_MOM_BLEND_MATCHED_CONTROLS"
REQUIRED_ROOT_FILES = (
    "active_alpha_model.py",
    "ticker_membership.csv",
    "requirements_active_alpha.txt",
    "tools/wsl_conductor.sh",
    "tools/setup_wsl_host.sh",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dir_size_mb(path: Path) -> float:
    if not path.is_dir():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 1)


def _decode_wsl_output(raw: bytes) -> str:
    if not raw:
        return ""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:80]:
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def _wsl_probe() -> Dict[str, Any]:
    out: Dict[str, Any] = {"installed": False, "distros": []}
    try:
        proc = subprocess.run(
            ["wsl", "--status"],
            capture_output=True,
            timeout=15,
        )
        text = _decode_wsl_output(proc.stdout or proc.stderr or b"")
        out["installed"] = proc.returncode == 0
        out["status_stdout"] = text.strip()[:500]
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        out["error"] = repr(exc)
        return out
    try:
        proc = subprocess.run(
            ["wsl", "-l", "-v"],
            capture_output=True,
            timeout=15,
        )
        text = _decode_wsl_output(proc.stdout or proc.stderr or b"")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        out["distros"] = lines[1:] if len(lines) > 1 else lines
        out["ubuntu_ready"] = any("ubuntu" in ln.lower() for ln in out["distros"])
    except (subprocess.SubprocessError, OSError):
        out["ubuntu_ready"] = False
    return out


def _run_artifact(run_dir: Path) -> Dict[str, Any]:
    row: Dict[str, Any] = {"dir": run_dir.name}
    for name in (
        "strategy_daily_returns.csv",
        "prediction_cache.pkl",
        "prediction_cache_meta.json",
        "integrity_report.json",
    ):
        p = run_dir / name
        row[name] = p.is_file()
        if p.is_file():
            row[f"{name}_mb"] = round(p.stat().st_size / (1024 * 1024), 2)
    csv = run_dir / "strategy_daily_returns.csv"
    if csv.is_file():
        try:
            row["csv_rows"] = sum(1 for _ in open(csv, encoding="utf-8", errors="replace")) - 1
        except OSError:
            row["csv_rows"] = None
    return row


def _newest_run(variant: str) -> Optional[Path]:
    dirs = sorted(
        [p for p in ROOT.glob(f"validation_runs/*{variant}*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
    )
    return dirs[-1] if dirs else None


def _m1_windows_status() -> Dict[str, Any]:
    from tools.r0_migration_hw import cpu_delta, list_processes, nproc

    m1_procs = [
        p
        for p in list_processes()
        if "M1_MOM_BLEND" in p.get("cmd", "") or "125544Z_M1" in p.get("cmd", "")
    ]
    bt_pids = [p["pid"] for p in m1_procs if "active_alpha_model.py" in p.get("cmd", "")]
    delta = cpu_delta(bt_pids, 2.0) if bt_pids else 0.0
    return {
        "backtest_pids": bt_pids,
        "cpu_delta_2s": delta,
        "productive": delta >= 0.5,
        "matrix_procs": len(m1_procs),
        "cpu_cores": nproc(),
    }


def build_manifest(root: Path | None = None) -> Dict[str, Any]:
    root = root or ROOT
    wsl = _wsl_probe()
    m1_live = _m1_windows_status()

    variant_runs: Dict[str, Any] = {}
    seed_runs: List[str] = []
    for v in VARIANTS:
        newest = _newest_run(v)
        if newest:
            art = _run_artifact(newest)
            variant_runs[v] = art
            if v == M1_VARIANT and art.get("prediction_cache.pkl"):
                seed_runs.append(newest.name)
            if v != M1_VARIANT and art.get("strategy_daily_returns.csv"):
                seed_runs.append(newest.name)

    shared = root / "robustness_results_trading212" / "_shared_cache"
    missing = [rel for rel in REQUIRED_ROOT_FILES if not (root / rel).is_file()]

    from tools._m1_autoseal import _fast_seal, is_sealed

    manifest: Dict[str, Any] = {
        "generated_at_utc": _utc_now(),
        "windows_repo": str(root.resolve()),
        "wsl_target": "~/active_alpha_model",
        "wsl_win_mount": "/mnt/e/active_alpha_model",
        "wsl": wsl,
        "m1_windows": m1_live,
        "m1_sealed": is_sealed(),
        "fast_seal": _fast_seal(),
        "canonical_m1_run": (_newest_run(M1_VARIANT) or Path()).name or None,
        "variant_runs": variant_runs,
        "seed_run_dirs": seed_runs,
        "shared_cache_mb": _dir_size_mb(shared),
        "shared_cache_path": str(shared) if shared.is_dir() else None,
        "missing_required_files": missing,
        "reboot_safe": not bool(m1_live.get("productive")),
        "reboot_block_reason": (
            None
            if not m1_live.get("productive")
            else "M1 backtest CPU active on Windows — wait for CSV or confirmed hang"
        ),
    }
    return manifest


def build_checklist(manifest: Dict[str, Any]) -> Dict[str, Any]:
    wsl = manifest.get("wsl") or {}
    steps = [
        {
            "id": "preflight",
            "label": "Preflight manifest erzeugt",
            "done": True,
            "command": "python tools/preflight_wsl_migration.py",
        },
        {
            "id": "wsl_feature",
            "label": "WSL2 Feature installiert",
            "done": bool(wsl.get("installed")),
            "command": "powershell -File tools/prepare_wsl_migration.ps1 -InstallWsl",
            "needs_admin": True,
            "needs_reboot": True,
        },
        {
            "id": "ubuntu",
            "label": "Ubuntu-Distribution installiert",
            "done": bool(wsl.get("ubuntu_ready")),
            "command": "wsl --install -d Ubuntu",
            "needs_admin": True,
            "after_reboot": True,
        },
        {
            "id": "wsl_setup",
            "label": "WSL Host Setup (rsync, venv, caches)",
            "done": False,
            "command": "bash tools/wsl_conductor.sh setup",
            "in_wsl": True,
        },
        {
            "id": "smoke",
            "label": "WSL Smoke-Test bestanden",
            "done": False,
            "command": "bash tools/wsl_conductor.sh status",
            "in_wsl": True,
        },
        {
            "id": "m1_complete_or_switch",
            "label": "M1 auf Windows fertig ODER WSL-Resume bereit",
            "done": bool(manifest.get("m1_sealed"))
            or bool(
                (manifest.get("variant_runs") or {})
                .get(M1_VARIANT, {})
                .get("strategy_daily_returns.csv")
            ),
            "command": "python tools/r0_migration_status.py",
        },
        {
            "id": "autoseal_m2",
            "label": "Autoseal + M2 auf WSL",
            "done": bool(manifest.get("m1_sealed")),
            "command": "bash tools/wsl_conductor.sh autoseal",
            "in_wsl": True,
        },
    ]
    pending = [s["id"] for s in steps if not s.get("done")]
    return {
        "updated_at_utc": _utc_now(),
        "canonical_entry": "bash tools/wsl_conductor.sh",
        "steps": steps,
        "pending": pending,
        "next_step": pending[0] if pending else "complete",
        "reboot_safe": manifest.get("reboot_safe"),
    }


def write_artifacts(manifest: Dict[str, Any], *, checklist: Optional[Dict[str, Any]] = None) -> Tuple[Path, Path, Path]:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    CHECKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    chk = checklist or build_checklist(manifest)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    STATE_PATH.write_text(
        json.dumps(
            {
                "updated_at_utc": _utc_now(),
                "reboot_safe": manifest.get("reboot_safe"),
                "wsl_installed": (manifest.get("wsl") or {}).get("installed"),
                "ubuntu_ready": (manifest.get("wsl") or {}).get("ubuntu_ready"),
                "m1_productive_windows": (manifest.get("m1_windows") or {}).get("productive"),
                "next_step": chk.get("next_step"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    CHECKLIST_PATH.write_text(json.dumps(chk, indent=2) + "\n", encoding="utf-8")
    return MANIFEST_PATH, STATE_PATH, CHECKLIST_PATH


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="WSL migration preflight")
    p.add_argument("--json", action="store_true", help="Print manifest to stdout")
    args = p.parse_args()
    manifest = build_manifest()
    paths = write_artifacts(manifest)
    if args.json:
        print(json.dumps(manifest, indent=2, default=str))
    else:
        chk = json.loads(CHECKLIST_PATH.read_text(encoding="utf-8"))
        print(f"[preflight] manifest -> {paths[0]}")
        print(f"[preflight] state    -> {paths[1]}")
        print(f"[preflight] checklist-> {paths[2]}")
        print(f"[preflight] WSL installed: {(manifest.get('wsl') or {}).get('installed')}")
        print(f"[preflight] reboot_safe: {manifest.get('reboot_safe')} ({manifest.get('reboot_block_reason') or 'ok'})")
        print(f"[preflight] next_step: {chk.get('next_step')}")
        print(f"[preflight] shared_cache: {manifest.get('shared_cache_mb')} MB")
        print(f"[preflight] seed_runs: {', '.join(manifest.get('seed_run_dirs') or []) or '(none)'}")
    return 0 if not manifest.get("missing_required_files") else 1


if __name__ == "__main__":
    raise SystemExit(main())
