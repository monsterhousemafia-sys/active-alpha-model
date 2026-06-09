"""Lean Linux — nur was der Cognitive Kernel braucht, Rest pausiert."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/aa_lean_mode_latest.json")
_STATE_REL = Path("control/aa_lean_mode_state.json")

# Kern: H1, Hub, Tunnel, API, Scheduler, Observer
_KEEP_TIMERS = frozenset(
    {
        "active-alpha-h1-resume.timer",
        "active-alpha-h1-watch.timer",
        "active-alpha-evidence-watch.timer",
        "active-alpha-cognitive-scheduler.timer",
        "active-alpha-cognitive-observe.timer",
    }
)

_KEEP_SERVICES = frozenset(
    {
        "active-alpha-preview-hub.service",
        "active-alpha-remote-tunnel.service",
        "active-alpha-runtime-api.service",
    }
)

# Pausiert während Lean — CPU/RAM für H1
_PAUSE_TIMERS = frozenset(
    {
        "active-alpha-learn.timer",
        "active-alpha-gui-preview.timer",
        "active-alpha-refresh.timer",
        "active-alpha-refresh-preus.timer",
        "active-alpha-refresh-usopen.timer",
        "active-alpha-trading-day.timer",
        "active-alpha-warnings.timer",
        "active-alpha-spread-tick.timer",
        "active-alpha-spread-tick-1.timer",
        "active-alpha-spread-tick-2.timer",
        "active-alpha-spread-tick-3.timer",
        "active-alpha-spread-tick-4.timer",
        "active-alpha-boot.timer",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _list_aa_timers() -> List[str]:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "list-unit-files", "active-alpha-*.timer", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        units: List[str] = []
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if parts and parts[0].startswith("active-alpha-") and parts[0].endswith(".timer"):
                units.append(parts[0])
        return sorted(set(units))
    except (OSError, subprocess.TimeoutExpired):
        return []


def _timer_active(unit: str) -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-enabled", unit],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return (proc.stdout or "").strip() == "enabled"
    except (OSError, subprocess.TimeoutExpired):
        return False


_TURBO_STOP_SERVICES = frozenset(
    {
        "active-alpha-preview-hub.service",
        "active-alpha-remote-tunnel.service",
        "active-alpha-runtime-api.service",
    }
)

_TURBO_STOP_TIMERS = frozenset(
    {
        "active-alpha-evidence-watch.timer",
        "active-alpha-h1-watch.timer",
    }
)

_MAX_STOP_SERVICES = frozenset(
    {
        "active-alpha-preview-hub.service",
        "active-alpha-remote-tunnel.service",
        "active-alpha-runtime-api.service",
        "active-alpha-stable-server.service",
        "active-alpha-preview-worker.service",
    }
)

_PROTECTED_USER_SERVICES = frozenset({"ollama.service"})


def _ensure_protected_services() -> Dict[str, Any]:
    """Ollama und andere geschützte Dienste nicht stoppen — bei Bedarf starten."""
    ensured: List[str] = []
    errors: List[str] = []
    for unit in sorted(_PROTECTED_USER_SERVICES):
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if (proc.stdout or "").strip() in ("active", "activating"):
                ensured.append(unit)
                continue
            subprocess.run(
                ["systemctl", "--user", "enable", "--now", unit],
                check=False,
                timeout=15,
            )
            proc2 = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if (proc2.stdout or "").strip() in ("active", "activating"):
                ensured.append(unit)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{unit}: {exc}")
    return {"ensured": ensured, "errors": errors}


def _boost_h1_processes(root: Path) -> Dict[str, Any]:
    """Max CPU/IO für laufenden H1 — Operator-Yield aus."""
    root = Path(root)
    try:
        from execution.h1_cpu_priority import find_h1_backtest_pids

        pids = find_h1_backtest_pids(root)
    except Exception:
        pids = []
    results: List[Dict[str, Any]] = []
    for pid in pids:
        row: Dict[str, Any] = {"pid": pid}
        try:
            os.setpriority(os.PRIO_PROCESS, pid, -2)
            row["nice"] = -2
        except (OSError, AttributeError, ProcessLookupError) as exc:
            row["nice_error"] = str(exc)[:80]
        try:
            proc = subprocess.run(
                ["ionice", "-c", "2", "-n", "0", "-p", str(pid)],
                capture_output=True,
                timeout=3,
                check=False,
            )
            row["ionice_ok"] = proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            row["ionice_ok"] = False
        results.append(row)
    try:
        from execution.h1_linux_boost import warm_run_artifacts
        from analytics.live_profile_governance import h1_backtest_status

        warm = warm_run_artifacts(root, h1_backtest_status(root).get("run_dir"))
    except Exception:
        warm = {}
    return {"pids": pids, "results": results, "warm": warm}


def _stop_service(scope: List[str], unit: str) -> bool:
    try:
        proc = subprocess.run(
            [*scope, "is-active", unit],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if (proc.stdout or "").strip() not in ("active", "activating"):
            subprocess.run([*scope, "stop", unit], check=False, timeout=10)
            return False
        subprocess.run([*scope, "stop", unit], check=False, timeout=10)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _pause_timer(unit: str) -> bool:
    if not _timer_active(unit):
        return False
    subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=5)
    subprocess.run(["systemctl", "--user", "disable", unit], check=False, timeout=5)
    return True


def _clear_stale_locks(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cleared: List[str] = []
    try:
        from aa_runtime_profile import cleanup_stale_batch_lock

        lock = cleanup_stale_batch_lock(root)
        if lock.get("removed"):
            cleared.append(str(lock.get("path") or ".active_alpha_batch.lock"))
    except Exception:
        pass
    hub_active = False
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", "active-alpha-preview-hub.service"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        hub_active = (proc.stdout or "").strip() in ("active", "activating")
    except (OSError, subprocess.TimeoutExpired):
        hub_active = False
    if not hub_active:
        for rel in ("evidence/preview_hub_daemon.lock", "evidence/preview_federation.lock"):
            path = root / rel
            if not path.is_file():
                continue
            try:
                path.unlink(missing_ok=True)
                cleared.append(rel)
            except OSError:
                pass
    return {"cleared": cleared}


def enable_lean_mode(root: Path, *, turbo: bool = False, maximum: bool = False) -> Dict[str, Any]:
    """Alles auf Cognitive Kernel zusammenführen — Neben-Timer aus."""
    root = Path(root)
    state_path = root / _STATE_REL
    if state_path.is_file():
        try:
            json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    paused: List[str] = []
    stopped_services: List[str] = []
    errors: List[str] = []

    if maximum:
        for unit in _list_aa_timers():
            try:
                if _pause_timer(unit):
                    paused.append(unit)
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(f"{unit}: {exc}")
        for svc in sorted(_MAX_STOP_SERVICES):
            try:
                if _stop_service(["systemctl", "--user"], svc):
                    stopped_services.append(svc)
            except OSError as exc:
                errors.append(f"{svc}: {exc}")
        keep_timers: set[str] = set()
    else:
        pause_set = set(_PAUSE_TIMERS)
        if turbo:
            pause_set |= _TURBO_STOP_TIMERS
        for unit in pause_set:
            try:
                if _pause_timer(unit):
                    paused.append(unit)
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(f"{unit}: {exc}")
        if turbo:
            for svc in _TURBO_STOP_SERVICES:
                try:
                    if _stop_service(["systemctl", "--user"], svc):
                        stopped_services.append(svc)
                except OSError as exc:
                    errors.append(f"{svc}: {exc}")
            keep_timers = {"active-alpha-h1-resume.timer"}
        else:
            try:
                from analytics.linux_runtime_unified import effective_keep_services, effective_keep_timers

                eff_svc = effective_keep_services(root)
                eff_tim = effective_keep_timers(root)
            except Exception:
                eff_svc = set(_KEEP_SERVICES)
                eff_tim = set(_KEEP_TIMERS)
            for svc in eff_svc:
                subprocess.run(["systemctl", "--user", "restart", svc], check=False, timeout=15)
            keep_timers = set(eff_tim) if eff_tim else set(_KEEP_TIMERS)

    for unit in keep_timers:
        subprocess.run(["systemctl", "--user", "unmask", unit], check=False, timeout=5)
        subprocess.run(["systemctl", "--user", "enable", "--now", unit], check=False, timeout=8)

    lock_cleanup = _clear_stale_locks(root) if (turbo or maximum) else {}
    boost = _boost_h1_processes(root) if (turbo or maximum) else {}
    protected = _ensure_protected_services() if (turbo or maximum) else {}

    try:
        from analytics.cognitive_kernel import cognitive_kernel_status

        ck = cognitive_kernel_status(root)
    except Exception:
        ck = {}

    if maximum:
        mode = "maximum"
    elif turbo:
        mode = "turbo"
    else:
        mode = "lean"
    if turbo or maximum:
        keep_services_list = sorted(_PROTECTED_USER_SERVICES)
    else:
        try:
            from analytics.linux_runtime_unified import effective_keep_services as _eff_svc

            keep_services_list = sorted(_eff_svc(root))
        except Exception:
            keep_services_list = sorted(_KEEP_SERVICES)
    doc = {
        "schema_version": 1,
        "mode": mode,
        "enabled_at_utc": _utc_now(),
        "paused_timers": paused,
        "stopped_services": stopped_services,
        "keep_timers": sorted(keep_timers),
        "keep_services": keep_services_list,
        "protected_services": protected,
        "lock_cleanup": lock_cleanup,
        "h1_boost": boost,
        "cognitive_kernel": ck,
        "errors": errors,
        "headline_de": (
            f"Maximum-Lean — alle AA-Timer/Services aus, {len(paused)} Timer, "
            f"{len(stopped_services)} Services gestoppt, nur H1-Prozess"
            if maximum
            else (
                f"Turbo-Lean — Hub/Tunnel/API aus, {len(paused)} Timer pausiert, H1 priorisiert"
                if turbo
                else f"Lean-Modus aktiv — {len(paused)} Timer pausiert, Kern läuft"
            )
        ),
        "restore_de": "ai_kernel lean-off",
        "ok": True,
    }
    atomic_write_json(
        state_path,
        {
            "paused_timers": paused,
            "stopped_services": stopped_services,
            "mode": mode,
            "enabled_at_utc": doc["enabled_at_utc"],
        },
    )
    atomic_write_json(root / _EVIDENCE_REL, doc)
    try:
        from analytics.runtime_structured_log import emit_runtime_log

        emit_runtime_log("aa-lean", mode, root=root, paused=len(paused))
    except Exception:
        pass
    return doc


def disable_lean_mode(root: Path) -> Dict[str, Any]:
    """Lean beenden — zuvor pausierte Timer wieder aktivieren."""
    root = Path(root)
    state_path = root / _STATE_REL
    paused: List[str] = []
    stopped_services: List[str] = []
    if state_path.is_file():
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            paused = list(st.get("paused_timers") or [])
            stopped_services = list(st.get("stopped_services") or [])
        except (json.JSONDecodeError, OSError):
            paused = []

    restored: List[str] = []
    for unit in paused:
        subprocess.run(["systemctl", "--user", "enable", unit], check=False, timeout=5)
        restored.append(unit)

    restarted: List[str] = []
    for svc in stopped_services:
        subprocess.run(["systemctl", "--user", "start", svc], check=False, timeout=15)
        restarted.append(svc)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    if state_path.is_file():
        try:
            state_path.unlink()
        except OSError:
            pass

    doc = {
        "schema_version": 1,
        "mode": "normal",
        "disabled_at_utc": _utc_now(),
        "restored_timers": restored,
        "restarted_services": restarted,
        "headline_de": f"Lean aus — {len(restored)} Timer, {len(restarted)} Services wieder aktiv",
        "ok": True,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def lean_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    active_paused = [u for u in _PAUSE_TIMERS if not _timer_active(u)]
    lean_on = len(active_paused) >= 5
    return {
        "schema_version": 1,
        "lean_active": lean_on,
        "paused_count": len(active_paused),
        "keep_timers": sorted(_KEEP_TIMERS),
        "all_aa_timers": _list_aa_timers(),
        "headline_de": "Lean aktiv" if lean_on else "Normal — alle Timer enabled",
    }
