"""H1-Migration — ein Monitor, Auto-Recovery, keine Doppel-Starter."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_PIPELINE_EVIDENCE = Path("evidence/daily_alpha_h1_pipeline_latest.json")
_MONITOR_MARK = "run_daily_alpha_h1_pipeline.py --monitor-only"
_START_MARK = "run_daily_alpha_h1_pipeline.py"
_BACKTEST_MARKERS = (
    "run_validation_matrix.py",
    "active_alpha_model.py --mode backtest",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _python_bin(root: Path) -> str:
    venv_py = Path(root) / ".venv/bin/python3"
    return str(venv_py) if venv_py.is_file() else sys.executable


def _pgrep_lines(pattern: str) -> List[str]:
    try:
        proc = subprocess.run(
            ["pgrep", "-af", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return []
        return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    except OSError:
        return []


def _pid_from_pgrep_line(line: str) -> Optional[int]:
    parts = line.split(None, 1)
    if not parts:
        return None
    try:
        return int(parts[0])
    except ValueError:
        return None


def h1_process_inventory(root: Path) -> Dict[str, Any]:
    """Welche H1-Prozesse laufen — für Dedup und Health."""
    root = Path(root)
    monitors: List[Dict[str, Any]] = []
    starters: List[Dict[str, Any]] = []
    backtests: List[Dict[str, Any]] = []

    for line in _pgrep_lines(_MONITOR_MARK):
        if "pgrep" in line or "python3 -c" in line:
            continue
        pid = _pid_from_pgrep_line(line)
        if pid:
            monitors.append({"pid": pid, "cmd": line})

    for line in _pgrep_lines(_START_MARK):
        if _MONITOR_MARK in line or "pgrep" in line or "python3 -c" in line:
            continue
        pid = _pid_from_pgrep_line(line)
        if pid:
            starters.append({"pid": pid, "cmd": line})

    for marker in _BACKTEST_MARKERS:
        for line in _pgrep_lines(marker):
            if "pgrep" in line or "python3 -c" in line:
                continue
            if "DAILY_ALPHA_H1" not in line and "validation_runs" not in line:
                continue
            pid = _pid_from_pgrep_line(line)
            if pid and not any(x["pid"] == pid for x in backtests):
                backtests.append({"pid": pid, "cmd": line, "marker": marker})

    return {
        "monitor_count": len(monitors),
        "starter_count": len(starters),
        "backtest_count": len(backtests),
        "monitors": monitors,
        "starters": starters,
        "backtests": backtests,
        "duplicate_risk": len(monitors) > 1 or (len(starters) > 0 and len(backtests) > 0),
    }


def _sync_pipeline_evidence(root: Path, *, phase: str, ok: bool, detail_de: str, status_doc: Dict[str, Any]) -> None:
    path = root / _PIPELINE_EVIDENCE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": ok,
        "phase": phase,
        "h1_backtest_status": status_doc,
        "detail_de": detail_de,
        "updated_at_utc": _utc_now(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _terminate_pid(pid: int, *, grace_s: float = 0.25) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    import time

    if grace_s > 0:
        time.sleep(grace_s)
    try:
        os.kill(pid, 0)
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return True


def prune_duplicate_h1_processes(root: Path) -> Dict[str, Any]:
    """Entfernt überzählige Monitor/Starter — Backtest bleibt unangetastet."""
    inv = h1_process_inventory(root)
    killed: List[int] = []

    monitors = list(inv.get("monitors") or [])
    if len(monitors) > 1:
        keep_pid = int(monitors[-1]["pid"])
        for entry in monitors[:-1]:
            pid = int(entry["pid"])
            try:
                os.kill(pid, signal.SIGKILL)
                killed.append(pid)
            except OSError:
                pass

    backtest_active = int(inv.get("backtest_count") or 0) > 0
    starters = list(inv.get("starters") or [])
    if backtest_active and starters:
        for entry in starters:
            pid = int(entry["pid"])
            if _terminate_pid(pid):
                killed.append(pid)

    return {"killed_pids": killed, "inventory_before": inv}


def _start_monitor(root: Path, *, poll_seconds: int = 60) -> Dict[str, Any]:
    inv = h1_process_inventory(root)
    if int(inv.get("monitor_count") or 0) > 0:
        return {
            "ok": True,
            "action": "monitor_exists",
            "pid": inv["monitors"][0]["pid"],
            "reply_de": "H1-Monitor läuft bereits",
        }
    cmd = [
        _python_bin(root),
        str(root / "tools/run_daily_alpha_h1_pipeline.py"),
        "--monitor-only",
        "--poll-seconds",
        str(poll_seconds),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "ok": True,
            "action": "monitor_started",
            "pid": proc.pid,
            "reply_de": f"H1-Monitor gestartet (PID {proc.pid})",
        }
    except OSError as exc:
        return {"ok": False, "action": "monitor_failed", "error_de": str(exc)[:200]}


def _resume_backtest(root: Path, run_dir: Optional[str]) -> Dict[str, Any]:
    from tools.run_daily_alpha_h1_pipeline import _resume_stamp_from_run

    stamp = _resume_stamp_from_run(run_dir)
    inv = h1_process_inventory(root)
    if int(inv.get("backtest_count") or 0) > 0:
        return {
            "ok": True,
            "action": "resume_skipped",
            "resume_stamp": stamp,
            "detail_de": "Backtest läuft bereits — kein Neustart",
        }
    cmd = [_python_bin(root), str(root / "tools/run_daily_alpha_h1_pipeline.py"), "--native", "--start-only"]
    env = os.environ.copy()
    env["AA_PROJECT_ROOT"] = str(root)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "ok": True,
            "action": "resume_backtest",
            "resume_stamp": stamp,
            "pid": proc.pid,
            "detail_de": f"Fortsetzung gestartet (PID {proc.pid}) — {run_dir or 'neu'}",
        }
    except OSError as exc:
        return {"ok": False, "action": "resume_failed", "error_de": str(exc)[:200]}


def ensure_h1_migration_healthy(
    root: Path,
    *,
    auto_fix: bool = True,
    poll_seconds: int = 60,
) -> Dict[str, Any]:
    """
    Stellt sicher: ein Monitor, Backtest läuft oder wird fortgesetzt, Evidence aktuell.
    """
    root = Path(root)
    from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

    if is_h1_backtest_sealed(root):
        bt = h1_backtest_status(root)
        _sync_pipeline_evidence(root, phase="sealed", ok=True, detail_de="H1 sealed", status_doc=bt)
        try:
            from analytics.h1_governance_status import sync_h1_governance_status

            gov = sync_h1_governance_status(root)
        except Exception:
            gov = {}
        return {
            "ok": True,
            "action": "sealed",
            "h1_status": "SEALED",
            "governance": gov,
            "reply_de": "H1 sealed — Migration abgeschlossen",
        }

    actions: List[str] = []
    bt = h1_backtest_status(root)
    inv_before = h1_process_inventory(root)
    if auto_fix and inv_before.get("duplicate_risk"):
        pruned = prune_duplicate_h1_processes(root)
        if pruned.get("killed_pids"):
            actions.append(f"dedup:{len(pruned['killed_pids'])}")

    bt = h1_backtest_status(root)
    st = str(bt.get("status") or "MISSING")
    inv = h1_process_inventory(root)
    backtest_live = int(inv.get("backtest_count") or 0) > 0

    if st == "RUNNING" and backtest_live:
        _sync_pipeline_evidence(
            root,
            phase="running",
            ok=True,
            detail_de=str(bt.get("detail_de") or "Backtest aktiv"),
            status_doc=bt,
        )
        mon = _start_monitor(root, poll_seconds=poll_seconds) if auto_fix else {"ok": True}
        if mon.get("action") == "monitor_started":
            actions.append("monitor")
        try:
            from analytics.h1_governance_status import sync_h1_governance_status

            gov = sync_h1_governance_status(root)
        except Exception:
            gov = {}
        return {
            "ok": True,
            "action": "running",
            "h1_status": st,
            "run_dir": bt.get("run_dir"),
            "inventory": inv,
            "actions": actions,
            "monitor": mon,
            "governance": gov,
            "reply_de": f"H1 läuft stabil — {bt.get('detail_de') or st}",
        }

    if st in ("ZOMBIE", "FAILED") or (st == "RUNNING" and not backtest_live):
        if auto_fix:
            resumed = _resume_backtest(root, str(bt.get("run_dir") or ""))
            actions.append(resumed.get("action") or "resume")
            mon = _start_monitor(root, poll_seconds=poll_seconds)
            if mon.get("action") == "monitor_started":
                actions.append("monitor")
            bt = h1_backtest_status(root)
            st = str(bt.get("status") or st)
            _sync_pipeline_evidence(
                root,
                phase="recovered",
                ok=resumed.get("ok", False),
                detail_de=str(resumed.get("detail_de") or bt.get("detail_de") or "Recovery"),
                status_doc=bt,
            )
            try:
                from analytics.h1_governance_status import sync_h1_governance_status

                gov = sync_h1_governance_status(root)
            except Exception:
                gov = {}
            return {
                "ok": bool(resumed.get("ok")),
                "action": "recovered",
                "h1_status": st,
                "resume": resumed,
                "monitor": mon,
                "actions": actions,
                "governance": gov,
                "reply_de": f"H1 wiederhergestellt — {bt.get('detail_de') or st}",
            }
        _sync_pipeline_evidence(
            root,
            phase="zombie",
            ok=False,
            detail_de=str(bt.get("detail_de") or "Zombie — ai_kernel h1"),
            status_doc=bt,
        )
        return {
            "ok": False,
            "action": "needs_recovery",
            "h1_status": st,
            "inventory": inv,
            "reply_de": f"H1 {st} — Recovery nötig (ai_kernel h1)",
        }

    if st == "COMPLETE":
        _sync_pipeline_evidence(
            root,
            phase="complete",
            ok=True,
            detail_de="Evaluate/Seal via Monitor",
            status_doc=bt,
        )
        mon = _start_monitor(root, poll_seconds=poll_seconds) if auto_fix else {"ok": True}
        try:
            from analytics.h1_governance_status import sync_h1_governance_status

            gov = sync_h1_governance_status(root)
        except Exception:
            gov = {}
        return {
            "ok": True,
            "action": "complete",
            "h1_status": st,
            "monitor": mon,
            "governance": gov,
            "reply_de": "H1 COMPLETE — Evaluate läuft",
        }

    if auto_fix:
        started = _resume_backtest(root, None)
        mon = _start_monitor(root, poll_seconds=poll_seconds)
        bt = h1_backtest_status(root)
        _sync_pipeline_evidence(
            root,
            phase="started",
            ok=started.get("ok", False),
            detail_de=str(started.get("detail_de") or "Neustart"),
            status_doc=bt,
        )
        try:
            from analytics.h1_governance_status import sync_h1_governance_status

            gov = sync_h1_governance_status(root)
        except Exception:
            gov = {}
        return {
            "ok": bool(started.get("ok")),
            "action": "started",
            "h1_status": str(bt.get("status") or "MISSING"),
            "start": started,
            "monitor": mon,
            "governance": gov,
            "reply_de": "H1 gestartet",
        }

    return {"ok": False, "action": "missing", "h1_status": st, "reply_de": "H1 fehlt — ai_kernel h1"}


def should_skip_h1_start(root: Path) -> tuple[bool, str]:
    """Für ai_kernel h1 — kein Doppel-Start."""
    from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

    bt = h1_backtest_status(root)
    st = str(bt.get("status") or "MISSING")
    inv = h1_process_inventory(root)
    if st == "RUNNING" and int(inv.get("backtest_count") or 0) > 0:
        return True, f"H1 läuft bereits ({bt.get('run_dir')})"
    if st == "COMPLETE":
        return True, "H1 COMPLETE — Monitor/Evaluate"
    if is_h1_backtest_sealed(root):
        return True, "H1 sealed"
    return False, ""
