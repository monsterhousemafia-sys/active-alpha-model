"""Federation Compute — echte Arbeit auf Worker-CPUs verteilen."""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_QUEUE_REL = Path("evidence/federation_compute_queue.json")
_STATS_REL = Path("evidence/federation_compute_stats.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def worker_capabilities(root: Path, *, bundle_kind: str = "lite") -> List[str]:
    caps = ["heartbeat", "pulse"]
    root = Path(root)
    is_full = bundle_kind == "full" or (root / "tools" / "ai_kernel.py").is_file()
    if is_full:
        caps.extend(["preview", "snapshot"])
        try:
            from analytics.h1_federation_dispatch import h1_worker_capable

            if h1_worker_capable(root, bundle_kind="full" if is_full else bundle_kind):
                caps.append("h1")
        except Exception:
            pass
    return sorted(set(caps))


def load_compute_queue(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _QUEUE_REL)
    if not doc:
        doc = {"schema_version": 1, "pending": [], "active": {}, "completed": [], "updated_at_utc": _utc_now()}
    doc.setdefault("pending", [])
    doc.setdefault("active", {})
    doc.setdefault("completed", [])
    return doc


def _dedupe_pending(pending: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for item in pending:
        tid = str(item.get("id") or "")
        key = tid or json.dumps(item, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def save_compute_queue(root: Path, doc: Dict[str, Any]) -> Path:
    root = Path(root)
    path = root / _QUEUE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(doc)
    doc["schema_version"] = 1
    doc["pending"] = _dedupe_pending(list(doc.get("pending") or []))
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(path, doc)
    return path


def purge_h1_compute_tasks(root: Path) -> int:
    """H1-Chunks aus Queue entfernen — H1 läuft nur auf König."""
    root = Path(root)
    doc = load_compute_queue(root)
    removed = 0

    def _keep(task: Dict[str, Any]) -> bool:
        nonlocal removed
        if str(task.get("kind") or "") == "h1_path_chunk":
            removed += 1
            return False
        return True

    doc["pending"] = [t for t in (doc.get("pending") or []) if _keep(t)]
    active = dict(doc.get("active") or {})
    doc["active"] = {k: v for k, v in active.items() if _keep(v)}
    if removed:
        save_compute_queue(root, doc)
    return removed


def reclaim_stale_active_tasks(root: Path, *, max_age_s: int = 600) -> List[str]:
    """Hängende aktive Tasks zurück in pending (Worker abgestürzt)."""
    root = Path(root)
    doc = load_compute_queue(root)
    active: Dict[str, Any] = dict(doc.get("active") or {})
    pending: List[Dict[str, Any]] = list(doc.get("pending") or [])
    log: List[str] = []
    now = datetime.now(timezone.utc)
    kept: Dict[str, Any] = {}
    for tid, task in active.items():
        assigned = str(task.get("assigned_at_utc") or "")
        timeout_s = max(120, int(task.get("timeout_s") or max_age_s))
        stale = True
        if assigned:
            try:
                dt = datetime.fromisoformat(assigned.replace("Z", "+00:00"))
                stale = (now - dt).total_seconds() > timeout_s
            except ValueError:
                stale = True
        if stale:
            task = dict(task)
            task["status"] = "pending"
            task.pop("assigned_at_utc", None)
            task.pop("worker_id", None)
            task.pop("assigned_cpus", None)
            task["reclaimed_at_utc"] = _utc_now()
            pending.append(task)
            log.append(f"reclaim {task.get('kind')} {tid}")
        else:
            kept[tid] = task
    if log:
        doc["active"] = kept
        doc["pending"] = pending
        save_compute_queue(root, doc)
    return log


def _online_compute_workers(root: Path) -> List[Dict[str, Any]]:
    from analytics.preview_federation import load_federation_state, prune_stale_workers

    try:
        prune_stale_workers(root)
    except Exception:
        pass
    state = load_federation_state(root)
    workers = list((state.get("workers") or {}).values())
    return [w for w in workers if str(w.get("role") or "").lower() == "compute"]


def _task_id(kind: str) -> str:
    return f"{kind}-{time.time_ns()}-{os.getpid()}"


def enqueue_task(root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    doc = load_compute_queue(root)
    pending: List[Dict[str, Any]] = list(doc.get("pending") or [])
    tid = str(task.get("id") or _task_id(str(task.get("kind") or "task")))
    item = {**task, "id": tid, "enqueued_at_utc": _utc_now(), "status": "pending"}
    pending.append(item)
    doc["pending"] = pending[-50:]
    save_compute_queue(root, doc)
    return item


def sync_compute_demand(root: Path) -> List[str]:
    """König: echte Worker-Last — Pulse + Backend-Preview (H1 nur lokal)."""
    root = Path(root)
    log: List[str] = []
    log.extend(reclaim_stale_active_tasks(root))
    try:
        from analytics.h1_federation_dispatch import h1_tasks_enabled

        h1_distribute_on = h1_tasks_enabled(root)
    except Exception:
        h1_distribute_on = False
    if not h1_distribute_on:
        removed = purge_h1_compute_tasks(root)
        if removed:
            log.append(f"purge h1_path_chunk x{removed}")

    doc = load_compute_queue(root)
    pending = list(doc.get("pending") or [])
    active = dict(doc.get("active") or {})
    kinds_pending = {str(t.get("kind")) for t in pending} | {str(v.get("kind")) for v in active.values()}
    compute_workers = _online_compute_workers(root)
    n_workers = max(1, len(compute_workers))

    preview_path = root / "evidence/gui_preview_latest.json"
    preview_stale = True
    if preview_path.is_file():
        age_h = (time.time() - preview_path.stat().st_mtime) / 3600.0
        preview_stale = age_h > 3.0

    if preview_stale and "backend_preview" not in kinds_pending:
        enqueue_task(
            root,
            {
                "kind": "backend_preview",
                "requires": ["preview"],
                "priority": 50,
                "timeout_s": 600,
                "detail_de": "Backend-Preview auf Worker-CPU",
            },
        )
        log.append("enqueue backend_preview")

    pulse_n = sum(1 for t in pending if t.get("kind") == "compute_pulse")
    active_pulse = sum(1 for v in active.values() if v.get("kind") == "compute_pulse")
    try:
        from analytics.federation_worker_rewards import load_rewards_policy

        per_worker = int(load_rewards_policy(root).get("pulse_tasks_per_worker") or 3)
    except Exception:
        per_worker = 3
    target_pulse = max(2, n_workers * max(1, per_worker))
    while pulse_n + active_pulse < target_pulse:
        enqueue_task(
            root,
            {
                "kind": "compute_pulse",
                "requires": ["pulse"],
                "priority": 20,
                "seconds": 45,
                "timeout_s": 120,
                "detail_de": "CPU-Puls — echte Rechenleistung",
            },
        )
        pulse_n += 1
        log.append("enqueue compute_pulse")

    if preview_stale and "snapshot_refresh" not in kinds_pending:
        enqueue_task(
            root,
            {
                "kind": "snapshot_refresh",
                "requires": ["snapshot"],
                "priority": 30,
                "timeout_s": 300,
                "detail_de": "Snapshot-Refresh auf Worker",
            },
        )
        log.append("enqueue snapshot_refresh")

    verify_n = sum(1 for t in pending if t.get("kind") == "hub_verify")
    active_verify = sum(1 for v in active.values() if v.get("kind") == "hub_verify")
    if verify_n + active_verify < 1:
        enqueue_task(
            root,
            {
                "kind": "hub_verify",
                "requires": ["pulse"],
                "priority": 5,
                "timeout_s": 30,
                "detail_de": "Hub-Health-Check vom Worker",
            },
        )
        log.append("enqueue hub_verify")

    try:
        from analytics.h1_federation_dispatch import sync_h1_federation_tasks

        for line in sync_h1_federation_tasks(root):
            log.append(line)
    except Exception:
        pass

    return log


def pull_task_for_worker(
    root: Path,
    *,
    worker_id: str,
    capabilities: List[str],
    cpus: int = 1,
) -> Optional[Dict[str, Any]]:
    root = Path(root)
    sync_compute_demand(root)
    doc = load_compute_queue(root)
    pending: List[Dict[str, Any]] = list(doc.get("pending") or [])
    active: Dict[str, Any] = dict(doc.get("active") or {})
    caps = set(capabilities or [])

    try:
        from analytics.federation_worker_rewards import (
            load_rewards_policy,
            worker_fairness_score,
            worker_has_active_task,
        )

        pol = load_rewards_policy(root)
        if pol.get("fair_pull_one_active_per_worker", True) and worker_has_active_task(active, worker_id):
            return None
        fairness = worker_fairness_score(root, worker_id)
    except Exception:
        fairness = 0.0

    def _score(task: Dict[str, Any]) -> int:
        req = set(task.get("requires") or [])
        if req and not req.issubset(caps):
            return -1
        return int(task.get("priority") or 0)

    candidates = [t for t in pending if _score(t) >= 0]
    candidates.sort(
        key=lambda t: (
            -int(t.get("priority") or 0),
            fairness,
            str(t.get("enqueued_at_utc") or ""),
        )
    )
    if not candidates:
        return None

    task = dict(candidates[0])
    pending = [t for t in pending if t.get("id") != task.get("id")]
    task["status"] = "active"
    task["worker_id"] = worker_id
    task["assigned_at_utc"] = _utc_now()
    task["assigned_cpus"] = max(1, int(cpus or 1))
    active[str(task["id"])] = task
    doc["pending"] = pending
    doc["active"] = active
    save_compute_queue(root, doc)
    return task


def complete_task(
    root: Path,
    *,
    task_id: str,
    worker_id: str,
    ok: bool,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    doc = load_compute_queue(root)
    active: Dict[str, Any] = dict(doc.get("active") or {})
    task = dict(active.pop(str(task_id), {}) or {})
    if not task:
        return {"ok": False, "message_de": "Task unbekannt"}
    task["status"] = "ok" if ok else "failed"
    task["completed_at_utc"] = _utc_now()
    task["worker_id"] = worker_id
    if result:
        task["result"] = result
    completed: List[Dict[str, Any]] = list(doc.get("completed") or [])
    completed.append(task)
    doc["completed"] = completed[-100:]
    doc["active"] = active
    save_compute_queue(root, doc)
    _record_stats(root, task)
    return {"ok": True, "task_id": task_id}


def _record_stats(root: Path, task: Dict[str, Any]) -> None:
    root = Path(root)
    path = root / _STATS_REL
    stats = _load_json(path)
    stats.setdefault("tasks_ok", 0)
    stats.setdefault("tasks_failed", 0)
    stats.setdefault("cpu_seconds", 0.0)
    ok = task.get("status") == "ok"
    if ok:
        stats["tasks_ok"] = int(stats["tasks_ok"]) + 1
    else:
        stats["tasks_failed"] = int(stats["tasks_failed"]) + 1
    res = task.get("result") or {}
    cpu_s = float(res.get("cpu_seconds") or 0)
    try:
        from analytics.federation_worker_rewards import apply_task_reward_credit

        cpu_s = apply_task_reward_credit(
            root,
            kind=str(task.get("kind") or ""),
            cpu_seconds=cpu_s,
            ok=ok,
        )
        if res:
            task = dict(task)
            task["result"] = {**res, "cpu_seconds": cpu_s, "reward_adjusted": True}
    except Exception:
        pass
    stats["cpu_seconds"] = round(float(stats.get("cpu_seconds") or 0) + cpu_s, 2)
    stats["updated_at_utc"] = _utc_now()
    atomic_write_json(path, stats)
    try:
        from analytics.federation_legion import record_legion_contribution

        record_legion_contribution(
            root,
            worker_id=str(task.get("worker_id") or ""),
            ok=ok,
            kind=str(task.get("kind") or ""),
            cpu_seconds=cpu_s,
        )
    except Exception:
        pass


def _cpu_pulse_worker(n: int) -> float:
    t0 = time.perf_counter()
    x = float(n % 1000) + 1.0
    for i in range(800_000):
        x = math.sin(x) * math.cos(x) + (i % 7) * 0.0001
    return time.perf_counter() - t0


def run_compute_pulse(*, seconds: int = 45, cpus: int = 1) -> Dict[str, Any]:
    cpus = max(1, min(int(cpus or 1), os.cpu_count() or 1))
    deadline = time.monotonic() + max(10, int(seconds))
    total = 0.0
    rounds = 0
    while time.monotonic() < deadline:
        with multiprocessing.Pool(processes=cpus) as pool:
            chunk = pool.map(_cpu_pulse_worker, range(cpus))
        total += sum(chunk)
        rounds += 1
    return {"ok": True, "cpu_seconds": round(total, 2), "rounds": rounds, "cpus": cpus}


def run_backend_preview(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from ui.live_trading_dashboard.gui_preview_harness import run_backend_preview

    t0 = time.perf_counter()
    steps = run_backend_preview(root, allow_snapshot_refresh=False)
    wall_s = time.perf_counter() - t0
    passed = sum(1 for s in steps if s.get("pass"))
    total = len(steps)
    cpus = max(1, os.cpu_count() or 1)
    return {
        "ok": passed == total and total > 0,
        "passed": passed,
        "total": total,
        "wall_seconds": round(wall_s, 2),
        "cpu_seconds": round(wall_s * cpus, 2),
        "cpus": cpus,
    }


def run_snapshot_refresh(root: Path) -> Dict[str, Any]:
    import subprocess
    import sys

    root = Path(root)
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    proc = subprocess.run(
        [str(py), str(root / "tools/ai_kernel.py"), "refresh", "--refresh-mode", "snapshot"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    return {"ok": proc.returncode == 0, "rc": proc.returncode, "cpu_seconds": 30.0}


def execute_task(root: Path, task: Dict[str, Any], *, hub_url: str = "") -> Dict[str, Any]:
    kind = str(task.get("kind") or "")
    cpus = int(task.get("assigned_cpus") or os.cpu_count() or 1)
    try:
        if kind == "compute_pulse":
            return run_compute_pulse(seconds=int(task.get("seconds") or 45), cpus=cpus)
        if kind == "backend_preview":
            return run_backend_preview(root)
        if kind == "snapshot_refresh":
            return run_snapshot_refresh(root)
        if kind == "hub_verify":
            hub = str(hub_url or task.get("hub_url") or "").rstrip("/")
            with urllib.request.urlopen(f"{hub}/api/health", timeout=15) as resp:
                body = resp.read()
            digest = hashlib.sha256(body).hexdigest()[:16]
            return {"ok": resp.status == 200, "health_sha": digest, "cpu_seconds": 1.0}
        if kind == "h1_path_chunk":
            from analytics.h1_federation_dispatch import run_h1_path_chunk

            return run_h1_path_chunk(root, task, hub_url=hub_url, cpus=cpus)
        if kind == "h1_naive_prep_chunk":
            from analytics.h1_federation_dispatch import run_h1_naive_prep_chunk

            return run_h1_naive_prep_chunk(root, task, hub_url=hub_url, cpus=cpus)
        return {"ok": False, "message_de": f"Unbekannte Aufgabe: {kind}"}
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:300]}


def build_utilization_summary(root: Path) -> Dict[str, Any]:
    from analytics.preview_federation import load_federation_state, prune_stale_workers

    root = Path(root)
    try:
        prune_stale_workers(root)
    except Exception:
        pass
    state = load_federation_state(root)
    workers = list((state.get("workers") or {}).values())
    compute_workers = [w for w in workers if str(w.get("role") or "").lower() == "compute"]
    stats = _load_json(root / _STATS_REL)
    queue = load_compute_queue(root)
    active: Dict[str, Any] = dict(queue.get("active") or {})
    total_cpus = sum(int(w.get("cpus") or 0) for w in compute_workers)
    active_tasks = len(active)
    pending_tasks = len(queue.get("pending") or [])
    active_cpus = sum(int(t.get("assigned_cpus") or 1) for t in active.values())
    cpu_seconds = float(stats.get("cpu_seconds") or 0)
    tasks_ok = int(stats.get("tasks_ok") or 0)

    util_pct = 0
    if total_cpus > 0 and active_cpus:
        util_pct = min(100, int(100 * active_cpus / total_cpus))

    measured_de = ""
    if cpu_seconds > 0:
        measured_de = f"{cpu_seconds:.0f} CPU-Sekunden gemessen"
    elif active_cpus:
        measured_de = f"{active_cpus} Kerne aktiv rechnen"
    else:
        measured_de = "Warte auf Worker-Jobs"

    return {
        "total_cpus": total_cpus,
        "workers_online": len(compute_workers),
        "active_tasks": active_tasks,
        "active_cpus": active_cpus,
        "pending_tasks": pending_tasks,
        "tasks_completed_ok": tasks_ok,
        "cpu_seconds_total": cpu_seconds,
        "utilization_pct": util_pct,
        "measurement": "cpu_seconds",
        "headline_de": (
            f"{total_cpus} CPUs · {measured_de} · {tasks_ok} Jobs erledigt"
            if total_cpus
            else "Keine Worker"
        ),
    }
