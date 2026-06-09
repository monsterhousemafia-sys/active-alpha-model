"""AA Scheduler v2 — Userspace-Prioritäten für H1, Hub, Operator."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json


def _h1_process_alive(root: Path, run_dir: str) -> bool:
    if not run_dir:
        return False
    needle = Path(run_dir).name
    try:
        for pattern in ("run_validation_matrix", "active_alpha_model.py", "run_daily_alpha_h1"):
            proc = subprocess.run(
                ["pgrep", "-af", pattern],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if needle in (proc.stdout or ""):
                return True
        return False
    except (OSError, subprocess.TimeoutExpired):
        return False

_EVIDENCE_REL = Path("evidence/aa_scheduler_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_aa_scheduler(root: Path) -> Dict[str, Any]:
    root = Path(root)
    actions: List[Dict[str, Any]] = []

    try:
        from analytics.live_profile_governance import h1_backtest_status

        h1 = h1_backtest_status(root)
        st = str(h1.get("status") or "")
        if st in ("ZOMBIE", "FAILED") or (
            st == "RUNNING" and not _h1_process_alive(root, str(h1.get("run_dir") or ""))
        ):
            from aa_runtime_profile import cleanup_stale_batch_lock
            from analytics.aa_linux_runtime import runtime_h1_prep

            lock = cleanup_stale_batch_lock(root)
            prep = runtime_h1_prep(root)
            actions.append({"action": "h1_prep", "lock": lock, "detail": prep})
            try:
                import subprocess
                import sys

                py = root / ".venv/bin/python3"
                if not py.is_file():
                    py = Path(sys.executable)
                env = os.environ.copy()
                env["AA_RUNTIME_PROFILE"] = "validation"
                env["AA_PROJECT_ROOT"] = str(root)
                env["AA_LINUX_NATIVE_APP"] = "1"
                proc = subprocess.Popen(
                    [str(py), str(root / "tools/ai_kernel.py"), "h1"],
                    cwd=str(root),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                actions.append({"action": "h1_resume_forced", "pid": proc.pid, "profile": "validation"})
            except OSError as exc:
                actions.append({"action": "h1_resume_forced", "error": str(exc)[:120]})
        elif st == "RUNNING":
            from execution.h1_cpu_priority import renice_running_h1_backtest

            actions.append({"action": "h1_renice", "detail": renice_running_h1_backtest(root)})
    except Exception as exc:
        actions.append({"action": "h1", "error": str(exc)[:120]})

    try:
        from tools.preview_hub import ensure_hub_running

        port = ensure_hub_running(root, restart=False)
        actions.append({"action": "hub_ensure", "port": port})
    except Exception as exc:
        actions.append({"action": "hub_ensure", "error": str(exc)[:120]})

    try:
        from analytics.orchestrator_dispatch import run_orchestrator_dispatch

        dispatch = run_orchestrator_dispatch(root)
        actions.append({"action": "orchestrator_dispatch", "detail": dispatch})
    except Exception as exc:
        actions.append({"action": "orchestrator_dispatch", "error": str(exc)[:120]})

    try:
        from analytics.r3_desktop_view import run_r3_background_refresh

        refresh = run_r3_background_refresh(root)
        actions.append(
            {
                "action": "r3_background_refresh",
                "ok": bool(refresh.get("ok")),
                "steps": refresh.get("steps") or [],
            }
        )
    except Exception as exc:
        actions.append({"action": "r3_background_refresh", "error": str(exc)[:120]})

    doc = {
        "schema_version": 1,
        "ran_at_utc": _utc_now(),
        "actions": actions,
        "headline_de": f"Scheduler: {len(actions)} Aktion(en)",
        "ok": True,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
