#!/usr/bin/env python3
"""Phase M1 — R0 migration evidence baseline (audits; optional matrix launch)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion  # noqa: E402
from aa_safe_io import atomic_write_json, atomic_write_text  # noqa: E402

EVIDENCE_DIR = ROOT / "evidence" / "r0_migration"
CONTROL_DIR = ROOT / "control" / "r0_migration"
VALIDATION_ROOT = ROOT / "validation_runs"
M1_VARIANTS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)

ENV_SCAN_GLOBS = (
    "active_alpha_user_config.bat",
    "active_alpha_settings.bat",
    "run_active_alpha_model.bat",
    "run_paper_trading.bat",
    "load_active_alpha_config.bat",
)

CHAMPION_R3_RISK_OFF = {
    "AA_RISK_OFF_SELECTION_MODE": "mom_blend_blend",
    "AA_RISK_OFF_GATE_MODE": "momentum_rescue",
    "AA_RISK_OFF_MOMENTUM_WEIGHT": "0.75",
    "AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE": "0.65",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_returns_days(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    try:
        import pandas as pd

        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return int(len(df))
    except Exception:
        return None


def _m1_backtest_waiver_path(root: Path) -> Path:
    return root / "control" / "r0_migration" / "m1_backtest_waiver.json"


def _m1_backtest_waiver_active(root: Path) -> bool:
    p = _m1_backtest_waiver_path(root)
    if not p.is_file():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(data.get("status", "")).upper() == "ACTIVE" and bool(data.get("evidence_only"))


def write_m1_backtest_waiver(root: Path, *, reason: str) -> Dict[str, Any]:
    payload = {
        "schema_version": 1,
        "status": "ACTIVE",
        "evidence_only": True,
        "scope": "R0_LONG_TERM_MIGRATION_M1",
        "allowed_actions": ["validation_matrix_backtest", "validation_runs_population"],
        "forbidden": [
            "champion_change",
            "auto_promotion",
            "real_money_execution",
            "productive_signal_parameter_change",
        ],
        "reason": reason,
        "authorized_at_utc": _utc_now(),
        "authoritative_champion_unchanged": AUTHORITATIVE_CHAMPION,
    }
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_m1_backtest_waiver_path(root), payload)
    return payload


def _authorization_blocks_backtest(root: Path) -> Dict[str, Any]:
    if _m1_backtest_waiver_active(root):
        return {
            "blocks": False,
            "reason": "m1_backtest_waiver_active",
            "waiver_path": str(_m1_backtest_waiver_path(root).relative_to(root)),
        }
    p = root / "control" / "authorization" / "current_authorization_status.json"
    if not p.is_file():
        return {"blocks": False, "reason": "authorization_file_missing"}
    data = json.loads(p.read_text(encoding="utf-8"))
    blocked = set(data.get("blocked_actions") or [])
    blocks = "backtest_execution" in blocked or "matrix_rerun" in blocked
    return {
        "blocks": blocks,
        "operational_status": data.get("operational_status"),
        "blocked_actions": sorted(blocked),
        "g1_execution_authorized": data.get("g1_execution_authorized"),
    }


def build_pointer_audit(root: Path) -> Dict[str, Any]:
    from tools.run_champion_evidence_phase_a import build_champion_pointer_audit

    full = build_champion_pointer_audit(root)
    lvr_path = root / "model_output_sp500_pit_t212" / "latest_validated_run.json"
    lvr: Dict[str, Any] = {}
    if lvr_path.is_file():
        lvr = json.loads(lvr_path.read_text(encoding="utf-8"))
    run_dir = Path(str(lvr.get("run_dir") or ""))
    returns_candidates = [
        run_dir / "strategy_daily_returns.csv",
        root / "model_output_sp500_pit_t212" / "strategy_daily_returns.csv",
    ]
    returns_info = []
    for cand in returns_candidates:
        if not str(cand):
            continue
        returns_info.append(
            {
                "path": str(cand.relative_to(root)) if cand.is_relative_to(root) else str(cand),
                "exists": cand.is_file(),
                "sha256": _sha256(cand) if cand.is_file() else None,
                "n_days": _count_returns_days(cand) if cand.is_file() else None,
            }
        )
    return {
        "schema_version": 1,
        "phase": "M1.1",
        "generated_at_utc": _utc_now(),
        "locked_champion": resolve_locked_champion(root),
        "latest_validated_run": lvr,
        "run_dir_exists": run_dir.is_dir() if run_dir else False,
        "returns_candidates": returns_info,
        "conflicts": full.get("conflicts") or [],
        "critical_artifacts": {
            k: full.get("critical_artifacts", {}).get(k)
            for k in (
                "model_output_sp500_pit_t212/latest_validated_run.json",
                "control/authorization/current_authorization_status.json",
            )
        },
        "full_audit_ref": "evidence/champion_pointer_audit.json",
    }


def _parse_bat_env(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r'^\s*set\s+"([A-Z0-9_]+)=([^"]*)"\s*$', line, re.I)
        if m:
            out[m.group(1).upper()] = m.group(2)
    return out


def build_env_audit(root: Path) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    issues: List[str] = []
    for name in ENV_SCAN_GLOBS:
        p = root / name
        env = _parse_bat_env(p)
        alpha = env.get("AA_ALPHA_MODEL_MODE", "")
        entry: Dict[str, Any] = {"file": name, "present": p.is_file(), "AA_ALPHA_MODEL_MODE": alpha or None}
        if p.is_file() and alpha.lower() == "rank_only":
            issues.append(f"{name}: AA_ALPHA_MODEL_MODE=rank_only (must be ensemble for R0/R3 matrix alignment)")
            entry["issue"] = "rank_only_drift"
        if p.is_file() and name in ("active_alpha_user_config.bat", "active_alpha_settings.bat"):
            for key, expected in CHAMPION_R3_RISK_OFF.items():
                actual = env.get(key, "")
                entry[key] = actual or None
                if actual and actual.lower() != expected.lower():
                    entry.setdefault("champion_risk_off_notes", []).append(
                        f"{key}={actual} (productive R3 expects {expected})"
                    )
        files.append(entry)
    return {
        "schema_version": 1,
        "phase": "M1.5",
        "generated_at_utc": _utc_now(),
        "required_alpha_model_mode": "ensemble",
        "files": files,
        "issues": issues,
        "pass": len(issues) == 0,
    }


def apply_env_ensemble_fix(root: Path) -> Dict[str, Any]:
    changed: List[str] = []
    for name in ("active_alpha_user_config.bat", "active_alpha_settings.bat"):
        p = root / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new_text, n = re.subn(
            r'(set\s+"AA_ALPHA_MODEL_MODE=)rank_only(")',
            r"\1ensemble\2",
            text,
            flags=re.I,
        )
        if n:
            atomic_write_text(p, new_text)
            changed.append(name)
    return {"changed_files": changed, "applied": bool(changed)}


def discover_variant_returns(root: Path, variant_id: str) -> Dict[str, Any]:
    """Find strategy_daily_returns.csv under validation_runs or runs."""
    hits: List[Dict[str, Any]] = []
    patterns = [
        VALIDATION_ROOT.glob(f"*{variant_id}*/strategy_daily_returns.csv"),
        VALIDATION_ROOT.glob(f"**/*{variant_id}*/strategy_daily_returns.csv"),
        (ROOT / "runs").glob(f"*{variant_id}*/strategy_daily_returns.csv"),
        (ROOT / "runs").glob(f"**/*{variant_id}*/strategy_daily_returns.csv"),
    ]
    seen: set[str] = set()
    for gen in patterns:
        for p in gen:
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                {
                    "path": str(p.relative_to(root)),
                    "sha256": _sha256(p),
                    "n_days": _count_returns_days(p),
                    "integrity_hint": "PASS" if (_count_returns_days(p) or 0) >= 1800 else "CHECK",
                }
            )
    best = hits[0] if hits else None
    return {
        "variant_id": variant_id,
        "returns_found": bool(hits),
        "candidates": hits,
        "primary": best,
        "integrity_pass": bool(best and (best.get("n_days") or 0) >= 1800),
    }


def build_returns_manifest(root: Path) -> Dict[str, Any]:
    variants = {vid: discover_variant_returns(root, vid) for vid in M1_VARIANTS}
    mom_path = ROOT / "evidence" / "g1_independent_next_level" / "challenger" / "MOM_63_TOP12" / "daily_returns.csv"
    if mom_path.is_file():
        variants["MOM_63_TOP12_reference"] = {
            "variant_id": "MOM_63_TOP12",
            "returns_found": True,
            "primary": {
                "path": str(mom_path.relative_to(root)),
                "sha256": _sha256(mom_path),
                "n_days": _count_returns_days(mom_path),
            },
            "note": "G1 challenger reference only; not M1 matrix variant",
        }
    all_pass = all(v.get("integrity_pass") for v in variants.values() if v.get("variant_id") in M1_VARIANTS)
    return {
        "schema_version": 1,
        "phase": "M1.3",
        "generated_at_utc": _utc_now(),
        "variants": variants,
        "all_m1_variants_integrity_pass": all_pass,
    }


def build_validation_runs_status(root: Path, *, auth: Dict[str, Any]) -> Dict[str, Any]:
    present = VALIDATION_ROOT.is_dir() and any(VALIDATION_ROOT.iterdir()) if VALIDATION_ROOT.is_dir() else False
    cmd = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(ROOT / "tools" / "run_validation_matrix.py"),
        "--phase",
        "matrix",
        "--run-mode",
        "backtest",
        "--variant",
        "R0_LEGACY_ENSEMBLE",
        "--variant",
        "R3_w075_q065_noexit",
        "--variant",
        "M1_MOM_BLEND_MATCHED_CONTROLS",
        "--parallel-jobs",
        "1",
        "--runtime-profile",
        "turbo",
    ]
    return {
        "schema_version": 1,
        "phase": "M1.2",
        "generated_at_utc": _utc_now(),
        "validation_runs_dir_present": present,
        "validation_runs_path": str(VALIDATION_ROOT.relative_to(root)),
        "authorization_blocks_backtest": auth.get("blocks"),
        "status": "PENDING_BACKTEST" if not present else "PARTIAL",
        "recommended_command": " ".join(cmd),
        "estimated_runtime": "hours_per_variant (3 variants, shared feature cache)",
        "user_action_required": not present,
    }


def update_calendar_mismatch_doc(root: Path, pointer: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    lvr = pointer.get("latest_validated_run") or {}
    run_exists = pointer.get("run_dir_exists")
    mo_ret = root / "model_output_sp500_pit_t212" / "strategy_daily_returns.csv"
    n_mo = _count_returns_days(mo_ret) if mo_ret.is_file() else None
    lines = [
        "# Calendar mismatch root cause (M1.4 update)",
        "",
        f"**Updated:** {_utc_now()}",
        "",
        "## M1 findings",
        "",
        f"- **Locked champion:** `{resolve_locked_champion(root)}`",
        f"- **`latest_validated_run.run_dir` exists on disk:** {run_exists}",
        f"- **`validation_runs/` populated:** {VALIDATION_ROOT.is_dir() and any(VALIDATION_ROOT.iterdir()) if VALIDATION_ROOT.is_dir() else False}",
        f"- **`model_output` returns n_days:** {n_mo if n_mo is not None else 'MISSING'}",
        "",
        "## Rule (M1.4)",
        "",
        "Do **not** use `model_output_sp500_pit_t212/strategy_daily_returns.csv` for champion or R0 comparison metrics",
        "until `n_days` matches matrix (~1860). Use `validation_runs/*/strategy_daily_returns.csv` only.",
        "",
        "## Variant returns (M1.3)",
        "",
    ]
    for vid, info in (manifest.get("variants") or {}).items():
        prim = (info or {}).get("primary") or {}
        lines.append(
            f"- **{vid}:** found={info.get('returns_found')} n_days={prim.get('n_days')} path={prim.get('path')}"
        )
    lines.extend(
        [
            "",
            "## Phase B reference",
            "",
            "See original Phase A3 notes in git history; matrix embedded metrics remain valid for ranking",
            "until fresh CSVs exist under `validation_runs/`.",
            "",
        ]
    )
    atomic_write_text(root / "evidence" / "calendar_mismatch_root_cause.md", "\n".join(lines))


def _sla_blocks_full_matrix_launch(root: Path, variant_list: List[str]) -> Optional[str]:
    """While canonical R0 is incomplete, never launch validation_matrix (any variant)."""
    from tools.r0_migration_sla_enforce import canonical_r0_incomplete, sla_fast_path_active

    if not sla_fast_path_active(root):
        return None
    if canonical_r0_incomplete(root):
        return "sla_fast_path_canonical_r0_incomplete"
    return None


def launch_validation_matrix(
    root: Path,
    *,
    dry_run: bool = False,
    foreground: bool = False,
    no_warm_cache: bool = False,
    cpu_cores: Optional[int] = None,
    variants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    import os

    from tools.r0_migration_crash_guard import append_matrix_log_session, write_matrix_job
    from tools.r0_migration_outage_guard import run_outage_check

    variant_list = list(variants) if variants else list(M1_VARIANTS)
    block = _sla_blocks_full_matrix_launch(root, variant_list)
    if block and not dry_run:
        from tools.r0_migration_sla_enforce import enforce_sla_fast_path

        sla = enforce_sla_fast_path(root)
        return {
            "skipped": True,
            "reason": block,
            "sla_enforce": sla,
            "variants": variant_list,
        }

    guard = CONTROL_DIR / "matrix_launch_guard.lock"
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        from tools.r0_migration_runtime import count_validation_matrix_processes, matrix_work_in_progress

        if guard.is_file() and not matrix_work_in_progress(root):
            try:
                guard.unlink(missing_ok=True)
            except OSError:
                pass
        if guard.is_file() and count_validation_matrix_processes(root) > 0:
            return {"skipped": True, "reason": "matrix_launch_guard_active", "guard": str(guard)}
        try:
            fd = os.open(str(guard), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.close(fd)
        except FileExistsError:
            return {"skipped": True, "reason": "matrix_launch_guard_active", "guard": str(guard)}
    run_outage_check(root, repair=True)
    VALIDATION_ROOT.mkdir(parents=True, exist_ok=True)
    py = root / ".venv" / "Scripts" / "python.exe"
    cmd = [
        str(py),
        str(root / "tools" / "run_validation_matrix.py"),
        "--phase",
        "matrix",
        "--run-mode",
        "backtest",
        "--parallel-jobs",
        "2",
        "--runtime-profile",
        "turbo",
        "--cpu-cores",
        str(max(1, int(cpu_cores or os.cpu_count() or 16))),
    ]
    for vk in variant_list:
        cmd.extend(["--variant", vk])
    if no_warm_cache:
        cmd.append("--no-warm-cache")
    from tools.r0_migration_runtime import count_validation_matrix_processes, matrix_work_in_progress

    if matrix_work_in_progress(root):
        return {
            "skipped": True,
            "reason": "matrix_already_running",
            "cmd": cmd,
            "matrix_processes": count_validation_matrix_processes(root),
        }
    log_path = EVIDENCE_DIR / "validation_matrix_run.log"
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return {"cmd": cmd, "log_path": str(log_path), "dry_run": True}
    import subprocess

    cores = max(1, int(os.environ.get("AA_CPU_CORES", "") or os.cpu_count() or 16))
    from tools.r0_migration_killer_pack import killer_subprocess_env

    env = killer_subprocess_env(
        {
            **os.environ,
            "AA_RUNTIME_PROFILE": "turbo",
            "AA_CPU_CORES": str(cores),
            "AA_RESERVE_CPU_CORES": "0",
        }
    )
    session = _utc_now().replace(":", "")
    append_matrix_log_session(root, cmd, session=session)
    started = _utc_now()
    if foreground:
        print("[R0-M1] Validation matrix (foreground) — Fortschritt erscheint in diesem Fenster.", flush=True)
        print(" ".join(cmd), flush=True)
        with log_path.open("a", encoding="utf-8") as log:
            rc = subprocess.call(cmd, cwd=str(root), env=env, stdout=log, stderr=subprocess.STDOUT)
        job = write_matrix_job(
            root,
            {
                "started_at_utc": started,
                "finished_at_utc": _utc_now(),
                "cmd": cmd,
                "log_path": str(log_path.relative_to(root)),
                "returncode": rc,
                "foreground": True,
                "session": session,
            },
            returncode=rc,
            foreground=True,
        )
        return {"returncode": rc, "log_path": str(log_path), "cmd": cmd, "foreground": True, "matrix_job": job}

    with log_path.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
        )
    job = write_matrix_job(
        root,
        {
            "started_at_utc": started,
            "cmd": cmd,
            "log_path": str(log_path.relative_to(root)),
            "pid": proc.pid,
            "foreground": False,
            "session": session,
        },
        foreground=False,
    )
    return {"pid": proc.pid, "log_path": str(log_path), "cmd": cmd, "foreground": False, "matrix_job": job}


def _tail_text(path: Path, *, lines: int = 5) -> List[str]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [ln.rstrip() for ln in text[-lines:] if ln.strip()]


def _matrix_log_paths(root: Path) -> List[Path]:
    paths = [EVIDENCE_DIR / "validation_matrix_run.log"]
    if VALIDATION_ROOT.is_dir():
        for child in sorted(VALIDATION_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if child.is_dir() and child.name.endswith("_M1_MOM_BLEND_MATCHED_CONTROLS"):
                p = child / "validation_run.log"
                if p.is_file():
                    paths.append(p)
                    break
    return paths


def _count_validation_variant_dirs(root: Path) -> List[str]:
    if not VALIDATION_ROOT.is_dir():
        return []
    names: List[str] = []
    for child in VALIDATION_ROOT.iterdir():
        if not child.is_dir():
            continue
        for key in M1_VARIANTS:
            if child.name.endswith(f"_{key}"):
                names.append(key)
                break
    return sorted(set(names))


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    import subprocess

    return (
        subprocess.call(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
            ],
        )
        == 0
    )


def _lock_holder_pid(root: Path) -> int:
    lock_path = root / ".active_alpha_batch.lock"
    if not lock_path.is_file():
        return 0
    try:
        return int(lock_path.read_text(encoding="utf-8").split()[0])
    except Exception:
        return 0


def _matrix_work_active(root: Path, *, job_pid: int) -> bool:
    from aa_runtime_profile import is_batch_work_active

    if is_batch_work_active(root):
        return True
    if _pid_alive(job_pid):
        return True
    lock_pid = _lock_holder_pid(root)
    return _pid_alive(lock_pid)


def _matrix_log_complete(root: Path) -> bool:
    log_path = EVIDENCE_DIR / "validation_matrix_run.log"
    if not log_path.is_file():
        return False
    return "Summary: PASS=" in log_path.read_text(encoding="utf-8", errors="replace")


def _m1_returns_complete(root: Path) -> bool:
    manifest = build_returns_manifest(root)
    return bool(manifest.get("all_m1_variants_integrity_pass"))


def wait_for_matrix_job(root: Path, *, interval_sec: int = 30, max_polls: int = 720) -> Dict[str, Any]:
    """Poll until matrix truly finished (lock, log Summary, or all returns)."""
    job_path = EVIDENCE_DIR / "matrix_job.json"
    log_path = EVIDENCE_DIR / "validation_matrix_run.log"
    job_pid = 0
    if job_path.is_file():
        try:
            job_pid = int(json.loads(job_path.read_text(encoding="utf-8")).get("pid") or 0)
        except Exception:
            job_pid = 0
    lock_pid = _lock_holder_pid(root)
    watch_pid = lock_pid if _pid_alive(lock_pid) else (job_pid if _pid_alive(job_pid) else lock_pid or job_pid)

    print("[R0-M1] Warte auf Validation Matrix (Fortschritt alle 30s). Ctrl+C = nur Abbruch des Waiters.", flush=True)
    print(f"[R0-M1] Watch-PID: lock={lock_pid} job={job_pid} (job.json kann veraltet sein)", flush=True)

    import time

    for poll in range(1, max_polls + 1):
        active = _matrix_work_active(root, job_pid=job_pid)
        alive_watch = _pid_alive(watch_pid)
        log_tail = _tail_text(log_path, lines=4)
        variants = _count_validation_variant_dirs(root)
        returns_ok = _m1_returns_complete(root)
        elapsed_min = (poll * interval_sec) // 60
        status_parts = [
            f"poll={poll}",
            f"~{elapsed_min} min",
            f"dirs={variants or ['-']}",
            f"batch_active={active}",
            f"returns_ok={returns_ok}",
        ]
        print(f"[R0-M1] {' | '.join(status_parts)}", flush=True)
        for ln in log_tail:
            print(f"  matrix.log: {ln[:200]}", flush=True)
        m1_logs = _matrix_log_paths(root)
        if len(m1_logs) > 1:
            for ln in _tail_text(m1_logs[1], lines=2):
                print(f"  variant.log: {ln[:200]}", flush=True)

        if _matrix_log_complete(root):
            print("[R0-M1] Matrix abgeschlossen (Summary: PASS= im Log).", flush=True)
            return {"status": "FINISHED", "reason": "log_summary", "polls": poll}
        if returns_ok:
            print("[R0-M1] Alle M1-Returns vorhanden (R0/R3/M1).", flush=True)
            return {"status": "FINISHED", "reason": "returns_manifest", "polls": poll}

        if not active and poll >= 2:
            print(
                "[R0-M1] WARNUNG: Kein Batch-Lock/Prozess mehr, aber Matrix nicht fertig "
                "(kein Summary, keine vollständigen Returns).",
                flush=True,
            )
            print("[R0-M1] -> Matrix evtl. abgestuerzt. Neu starten: python tools/r0_migration_commander.py", flush=True)
            return {"status": "INCOMPLETE", "reason": "work_stopped_early", "polls": poll}

        time.sleep(interval_sec)

    print("[R0-M1] Timeout nach max_polls — Refresh trotzdem.", flush=True)
    return {"status": "TIMEOUT", "polls": max_polls}


def print_human_summary(result: Dict[str, Any]) -> None:
    """Kurze Konsolen-Zusammenfassung statt vollem JSON."""
    print("", flush=True)
    print("=" * 60, flush=True)
    print("R0-M1 Zusammenfassung", flush=True)
    print("=" * 60, flush=True)
    m1_status = result.get("m1_status") or "?"
    print(f"  M1-Status:        {m1_status}", flush=True)
    blockers = result.get("blockers") or []
    print(f"  Blocker:          {blockers or '(keine)'}", flush=True)
    env = result.get("env_audit") or {}
    print(f"  Env-Audit:        {'PASS' if env.get('pass') else 'FAIL'}", flush=True)
    manifest = result.get("returns_manifest") or {}
    print(f"  Returns komplett: {manifest.get('all_m1_variants_integrity_pass')}", flush=True)
    for vid in M1_VARIANTS:
        info = (manifest.get("variants") or {}).get(vid) or {}
        prim = info.get("primary") or {}
        print(
            f"    {vid}: found={info.get('returns_found')} n_days={prim.get('n_days')} pass={info.get('integrity_pass')}",
            flush=True,
        )
    vr = result.get("validation_runs_status") or {}
    print(f"  validation_runs:  {vr.get('status')} present={vr.get('validation_runs_dir_present')}", flush=True)
    wi = result.get("wait_info") or {}
    if wi:
        print(f"  Wait:             status={wi.get('status')} reason={wi.get('reason')}", flush=True)
    rec = result.get("recovery") or {}
    snap = rec.get("snapshot") or {}
    if snap:
        print(f"  Recovery:         batch_active={snap.get('batch_active')} lock_removed=", end="", flush=True)
        acts = snap.get("actions") or []
        rm = next((a for a in acts if a.get("action") == "cleanup_stale_batch_lock"), {})
        print(f"{rm.get('removed')}", flush=True)
    if result.get("matrix_launch"):
        ml = result["matrix_launch"]
        print(f"  Matrix-Start:     pid={ml.get('pid')} foreground={ml.get('foreground')} rc={ml.get('returncode')}", flush=True)
    print("=" * 60, flush=True)
    print("Details: evidence\\r0_migration\\returns_manifest.json", flush=True)
    print("", flush=True)


def _finalize_m1_artifacts(
    root: Path,
    *,
    pointer: Dict[str, Any],
    env_audit: Dict[str, Any],
    manifest: Dict[str, Any],
    vr_status: Dict[str, Any],
    blockers: List[str],
    env_fix: Dict[str, Any],
) -> str:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(EVIDENCE_DIR / "pointer_audit.json", pointer)
    atomic_write_json(EVIDENCE_DIR / "env_alpha_model_mode_audit.json", env_audit)
    atomic_write_json(EVIDENCE_DIR / "returns_manifest.json", manifest)
    atomic_write_json(EVIDENCE_DIR / "validation_runs_status.json", vr_status)
    if env_fix.get("applied"):
        atomic_write_json(EVIDENCE_DIR / "env_fix_applied.json", env_fix)
    update_calendar_mismatch_doc(root, pointer, manifest)

    from tools.run_champion_evidence_phase_a import build_champion_pointer_audit

    atomic_write_json(root / "evidence" / "champion_pointer_audit.json", build_champion_pointer_audit(root))

    status = "COMPLETE" if manifest.get("all_m1_variants_integrity_pass") and not blockers else "COMPLETE_WITH_BLOCKER"
    if blockers == ["M1_VARIANT_RETURNS_MISSING"]:
        status = "COMPLETE_WITH_BLOCKER"
    atomic_write_json(
        EVIDENCE_DIR / "m1_completion_summary.json",
        {
            "phase": "M1",
            "status": status,
            "completed_at_utc": _utc_now(),
            "blockers": blockers,
            "validation_runs_present": vr_status.get("validation_runs_dir_present"),
            "env_audit_pass": env_audit.get("pass"),
            "authoritative_champion_unchanged": AUTHORITATIVE_CHAMPION,
        },
    )
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase

    seal_result: Dict[str, Any] = {}
    if status == "COMPLETE" and not blockers:
        seal_result = try_seal_phase(root, "M1")
        if str(seal_result.get("status")) == "SEALED":
            status = "SEALED"
    elif blockers:
        phase_status_path = CONTROL_DIR / "phase_status.json"
        phase_data = json.loads(phase_status_path.read_text(encoding="utf-8")) if phase_status_path.is_file() else {}
        phases = phase_data.get("phases") or {}
        phases["M1"] = {"status": "IN_PROGRESS", "updated_at_utc": _utc_now(), "blockers": blockers}
        phases["M2"] = {"status": "PENDING", "blocked_by": blockers[0] if blockers else "M1"}
        phase_data["phases"] = phases
        phase_data["current_phase"] = "M1"
        phase_data["last_completed_phase"] = "M0" if is_phase_sealed(root, "M0") else "M0"
        phase_data["updated_at_utc"] = _utc_now()
        atomic_write_json(phase_status_path, phase_data)
        atomic_write_json(
            root / "control" / "r0_migration_program.json",
            {
                "schema_version": 1,
                "program": "R0_LONG_TERM_MIGRATION",
                "current_phase": "M1",
                "last_completed_phase": "M0",
                "updated_at_utc": _utc_now(),
                "m1_blockers": blockers,
            },
        )
        auth = _authorization_blocks_backtest(root)
        atomic_write_text(EVIDENCE_DIR / "M1_BACKTEST_INSTRUCTIONS.md", _backtest_instructions(vr_status, auth))
        from tools.r0_migration_status_sync import sync_m1_status_artifacts

        sync_m1_status_artifacts(root, blockers=blockers)
        return status

    phase_status_path = CONTROL_DIR / "phase_status.json"
    phase_data = json.loads(phase_status_path.read_text(encoding="utf-8")) if phase_status_path.is_file() else {}
    phases = phase_data.get("phases") or {}
    phases["M1"] = {"status": status, "completed_at_utc": _utc_now(), "blockers": blockers, "seal": seal_result.get("status")}
    phases["M2"] = {"status": "READY" if status == "SEALED" else "PENDING", "blocked_by": None if status == "SEALED" else "M1"}
    phase_data["phases"] = phases
    phase_data["current_phase"] = "M2" if status == "SEALED" else "M1"
    phase_data["last_completed_phase"] = "M1" if status == "SEALED" else phase_data.get("last_completed_phase", "M0")
    phase_data["updated_at_utc"] = _utc_now()
    atomic_write_json(phase_status_path, phase_data)
    atomic_write_json(
        root / "control" / "r0_migration_program.json",
        {
            "schema_version": 1,
            "program": "R0_LONG_TERM_MIGRATION",
            "current_phase": "M2" if status == "SEALED" else "M1",
            "last_completed_phase": "M1" if status == "SEALED" else "M0",
            "last_sealed_phase": "M1" if status == "SEALED" else None,
            "updated_at_utc": _utc_now(),
            "m1_blockers": blockers,
            "m1_seal": seal_result.get("status"),
        },
    )
    auth = _authorization_blocks_backtest(root)
    atomic_write_text(EVIDENCE_DIR / "M1_BACKTEST_INSTRUCTIONS.md", _backtest_instructions(vr_status, auth))
    from tools.r0_migration_status_sync import sync_m1_status_artifacts

    sync_m1_status_artifacts(root, blockers=blockers)
    return status


def run_m1(
    *,
    apply_env_fix: bool = False,
    launch_matrix: bool = False,
    execute_preparation: bool = False,
    foreground_matrix: bool = False,
    wait_matrix: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    recovery: Dict[str, Any] = {}
    if not dry_run:
        from tools.r0_migration_outage_guard import run_outage_check

        recovery = run_outage_check(ROOT, repair=True)
    auth = _authorization_blocks_backtest(ROOT)
    pointer = build_pointer_audit(ROOT)
    env_audit = build_env_audit(ROOT)
    env_fix: Dict[str, Any] = {"applied": False}
    if apply_env_fix and not dry_run:
        env_fix = apply_env_ensemble_fix(ROOT)
        env_audit = build_env_audit(ROOT)

    manifest = build_returns_manifest(ROOT)
    vr_status = build_validation_runs_status(ROOT, auth=auth)
    blockers: List[str] = []
    if auth.get("blocks"):
        blockers.append("AUTHORIZATION_BLOCKS_BACKTEST")
    if not manifest.get("all_m1_variants_integrity_pass"):
        blockers.append("M1_VARIANT_RETURNS_MISSING")
    if env_audit.get("issues"):
        blockers.append("ENV_ALPHA_MODEL_MODE_DRIFT")

    matrix_exit = 0
    matrix_launch: Dict[str, Any] = {}
    wait_info: Dict[str, Any] = {}
    if execute_preparation and not dry_run:
        write_m1_backtest_waiver(ROOT, reason="User-requested M1 preparation: validation matrix for R0/R3/M1 evidence only.")
        auth = _authorization_blocks_backtest(ROOT)
        blockers = [b for b in blockers if b != "AUTHORIZATION_BLOCKS_BACKTEST"]
        if launch_matrix or execute_preparation:
            matrix_launch = launch_validation_matrix(ROOT, dry_run=False, foreground=foreground_matrix)
            if foreground_matrix:
                blockers = [b for b in blockers if b != "MATRIX_RUNNING"]
                manifest = build_returns_manifest(ROOT)
                vr_status = build_validation_runs_status(ROOT, auth=_authorization_blocks_backtest(ROOT))
                if not manifest.get("all_m1_variants_integrity_pass"):
                    blockers.append("M1_VARIANT_RETURNS_MISSING")
                matrix_exit = int(matrix_launch.get("returncode") or 0)
            blockers = [b for b in blockers if b != "M1_VARIANT_RETURNS_MISSING"]
            blockers.append("MATRIX_RUNNING")
            vr_status["status"] = "RUNNING"

    elif launch_matrix and not dry_run:
        if auth.get("blocks"):
            blockers.append("MATRIX_LAUNCH_SKIPPED_AUTHORIZATION")
        else:
            import subprocess

            cmd = vr_status["recommended_command"].split()
            matrix_exit = subprocess.call(cmd, cwd=str(ROOT))

    if wait_matrix and not dry_run:
        wait_info = wait_for_matrix_job(ROOT)
        from tools.r0_migration_crash_guard import reconcile_matrix_job, write_matrix_job

        job_path = EVIDENCE_DIR / "matrix_job.json"
        data: Dict[str, Any] = {}
        if job_path.is_file():
            data = json.loads(job_path.read_text(encoding="utf-8"))
        data["finished_at_utc"] = _utc_now()
        data["wait"] = wait_info
        if str(wait_info.get("status")) == "INCOMPLETE":
            data["returncode"] = data.get("returncode") or 1
        write_matrix_job(ROOT, data)
        reconcile_matrix_job(ROOT)
        manifest = build_returns_manifest(ROOT)
        vr_status = build_validation_runs_status(ROOT, auth=_authorization_blocks_backtest(ROOT))
        blockers = [b for b in blockers if b not in ("MATRIX_RUNNING", "M1_VARIANT_RETURNS_MISSING")]
        if not manifest.get("all_m1_variants_integrity_pass"):
            blockers.append("M1_VARIANT_RETURNS_MISSING")
        if str(wait_info.get("status")) == "INCOMPLETE":
            blockers.append("MATRIX_INCOMPLETE_OR_CRASHED")

    if not dry_run:
        status = _finalize_m1_artifacts(
            ROOT,
            pointer=pointer,
            env_audit=env_audit,
            manifest=manifest,
            vr_status=vr_status,
            blockers=blockers,
            env_fix=env_fix,
        )
        from tools.r0_migration_outage_guard import run_outage_check

        recovery = run_outage_check(ROOT, repair=True)
    else:
        status = "dry_run"

    return {
        "recovery": recovery,
        "pointer_audit": pointer,
        "env_audit": env_audit,
        "env_fix": env_fix,
        "returns_manifest": manifest,
        "validation_runs_status": vr_status,
        "authorization": auth,
        "blockers": blockers,
        "matrix_exit_code": matrix_exit,
        "matrix_launch": matrix_launch,
        "m1_status": status if not dry_run else "dry_run",
        "wait_info": wait_info,
    }


def _backtest_instructions(vr_status: Dict[str, Any], auth: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# M1 — Backtest / Validation Matrix (Benutzeraktion)",
            "",
            "## Brauchen Sie einen Backtest?",
            "",
            "**Ja**, für vollständiges M1-Exit und für M2:",
            "",
            "- `validation_runs/` ist leer oder ohne R0/R3/M1-Returns.",
            "- Ohne Lauf gibt es keine frischen `strategy_daily_returns.csv` mit `integrity_pass`.",
            "",
            "M1-Audits (Pointer, Env, Kalender-Regeln) sind **ohne** Backtest erledigt.",
            "",
            "## Voraussetzungen",
            "",
            "1. `AA_ALPHA_MODEL_MODE=ensemble` in `active_alpha_*.bat` (M1 hat ggf. bereits korrigiert).",
            "2. Kein paralleler Marktanalyse.exe-Lauf (Batch-Lock).",
            "3. **Authorization:** `control/authorization/current_authorization_status.json` darf",
            "   `backtest_execution` / `matrix_rerun` **nicht** blockieren — sonst manuell nach G0/G1-Freigabe.",
            "",
            "## Empfohlener Befehl (3 Varianten, ~Stunden Laufzeit)",
            "",
            "```bat",
            vr_status.get("recommended_command", "").replace(str(ROOT) + "\\", ""),
            "```",
            "",
            "Vollständige Matrix (alle R0–R4):",
            "",
            "```bat",
            ".venv\\Scripts\\python.exe tools\\run_validation_matrix.py --phase matrix --run-mode backtest",
            "```",
            "",
            "Nach Abschluss:",
            "",
            "```bat",
            ".venv\\Scripts\\python.exe tools\\run_r0_migration_phase_m1.py",
            "```",
            "",
            f"**Authorization blocks backtest now:** {auth.get('blocks')}",
            "",
        ]
    )


def main() -> int:
    p = argparse.ArgumentParser(description="R0 migration phase M1 evidence baseline.")
    p.add_argument("--apply-env-fix", action="store_true", help="Set AA_ALPHA_MODEL_MODE=ensemble in user config bats.")
    p.add_argument("--launch-matrix", action="store_true", help="Run validation matrix if authorization allows.")
    p.add_argument(
        "--execute-preparation",
        action="store_true",
        help="M1 waiver + start validation matrix (R0/R3/M1).",
    )
    p.add_argument(
        "--foreground-matrix",
        action="store_true",
        help="With --execute-preparation: run matrix in this console (visible progress).",
    )
    p.add_argument("--wait-matrix", action="store_true", help="Wait for matrix job (up to ~6h) with progress lines, then refresh.")
    p.add_argument("--json", action="store_true", help="Print full JSON summary (default: short human-readable).")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    result = run_m1(
        apply_env_fix=args.apply_env_fix,
        launch_matrix=args.launch_matrix or args.execute_preparation,
        execute_preparation=args.execute_preparation,
        foreground_matrix=args.foreground_matrix,
        wait_matrix=args.wait_matrix,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "pointer_audit"}, indent=2))
    else:
        print_human_summary(result)
    if str(result.get("m1_status")) == "SEALED":
        return 0
    blockers = set(result.get("blockers") or [])
    hard = {"AUTHORIZATION_BLOCKS_BACKTEST", "ENV_ALPHA_MODEL_MODE_DRIFT", "MATRIX_LAUNCH_SKIPPED_AUTHORIZATION"}
    if blockers & hard:
        return 1
    if blockers <= {"MATRIX_RUNNING"} and result.get("matrix_launch"):
        return 0
    if not blockers:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
