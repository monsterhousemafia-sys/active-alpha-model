"""H1-Backtest CPU-Priorität — tagsüber Operator/Preview/Ollama nicht ausbremsen."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

_BERLIN = ZoneInfo("Europe/Berlin")
# Operator-Stunden CET: Preview, Hub, Desktop, US-Vorbereitung
_YIELD_HOURS = range(8, 22)


def is_h1_yield_to_operator_hours(*, now: datetime | None = None) -> bool:
    ref = (now or datetime.now(_BERLIN)).astimezone(_BERLIN)
    return ref.hour in _YIELD_HOURS


def h1_priority_profile(*, yield_hours: bool | None = None) -> Dict[str, Any]:
    if yield_hours is None:
        yield_hours = is_h1_yield_to_operator_hours()
    if yield_hours:
        return {
            "nice": 12,
            "ionice_class": 3,
            "ionice_level": 7,
            "label_de": "tagsüber niedrig — Operator/Preview zuerst",
        }
    return {
        "nice": 4,
        "ionice_class": 2,
        "ionice_level": 5,
        "label_de": "nachts höher — H1 darf mehr CPU",
    }


def apply_h1_cpu_priority(*, pid: int | None = None, yield_hours: bool | None = None) -> Dict[str, Any]:
    """Linux: nice + ionice für H1-Prozess (Kind oder laufend)."""
    prof = h1_priority_profile(yield_hours=yield_hours)
    target = int(pid or os.getpid())
    out: Dict[str, Any] = {"pid": target, **prof, "ok": True}

    try:
        os.setpriority(os.PRIO_PROCESS, target, int(prof["nice"]))
        out["nice_applied"] = True
    except (OSError, AttributeError, ProcessLookupError) as exc:
        out["nice_applied"] = False
        out["nice_error"] = str(exc)[:120]

    try:
        proc = subprocess.run(
            [
                "ionice",
                "-c",
                str(int(prof["ionice_class"])),
                "-n",
                str(int(prof["ionice_level"])),
                "-p",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        out["ionice_applied"] = proc.returncode == 0
        if proc.returncode != 0:
            out["ionice_error"] = (proc.stderr or proc.stdout or "")[:120]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        out["ionice_applied"] = False
        out["ionice_error"] = str(exc)[:120]

    out["ok"] = bool(out.get("nice_applied") or out.get("ionice_applied"))
    return out


def h1_backtest_child_preexec() -> None:
    """Popen preexec_fn — Kind-Prozess vor Matrix-Start drosseln."""
    apply_h1_cpu_priority(yield_hours=is_h1_yield_to_operator_hours())


def find_h1_backtest_pids(root: Path) -> List[int]:
    root = Path(root)
    marker = ""
    try:
        from analytics.live_profile_governance import h1_backtest_status

        run_dir = str(h1_backtest_status(root).get("run_dir") or "")
        if run_dir:
            marker = run_dir.split("/")[-1] if "/" in run_dir else run_dir
    except Exception:
        pass
    if not marker:
        marker = "DAILY_ALPHA_H1"

    pids: List[int] = []
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid,args"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in (proc.stdout or "").splitlines():
            if marker not in line or "grep" in line:
                continue
            if "active_alpha_model.py" not in line and "run_validation_matrix" not in line:
                continue
            parts = line.strip().split(None, 1)
            if not parts:
                continue
            try:
                pids.append(int(parts[0]))
            except ValueError:
                continue
    except Exception:
        pass
    return sorted(set(pids))


def renice_running_h1_backtest(root: Path) -> Dict[str, Any]:
    pids = find_h1_backtest_pids(root)
    yield_h = is_h1_yield_to_operator_hours()
    results = [apply_h1_cpu_priority(pid=pid, yield_hours=yield_h) for pid in pids]
    return {
        "schema_version": 1,
        "yield_hours": yield_h,
        "pids": pids,
        "profile_de": h1_priority_profile(yield_hours=yield_h)["label_de"],
        "results": results,
        "ok": bool(pids) and any(r.get("ok") for r in results),
    }
