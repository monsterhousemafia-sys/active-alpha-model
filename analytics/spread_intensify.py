"""Spread intensivieren — voller Bash-Pfad wie beim ersten erfolgreichen Lauf."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/spread_intensify_latest.json")
_DISPATCH_REL = Path("control/H1_FEDERATION_DISPATCH.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _py(root: Path) -> Path:
    v = root / ".venv/bin/python3"
    return v if v.is_file() else Path(sys.executable)


def intensify_federation_demand(root: Path) -> List[str]:
    """Mehr Pulse, H1-Chunks, Hub-Checks — Worker sollen sofort Arbeit bekommen."""
    root = Path(root)
    log: List[str] = []
    try:
        from analytics.federation_compute import (
            _online_compute_workers,
            enqueue_task,
            load_compute_queue,
            reclaim_stale_active_tasks,
            sync_compute_demand,
        )

        log.extend(reclaim_stale_active_tasks(root))
        log.extend(sync_compute_demand(root))

        workers = _online_compute_workers(root)
        n_workers = max(1, len(workers))
        doc = load_compute_queue(root)
        pending = list(doc.get("pending") or [])
        active = dict(doc.get("active") or {})

        pulse_pending = sum(1 for t in pending if t.get("kind") == "compute_pulse")
        pulse_active = sum(1 for v in active.values() if v.get("kind") == "compute_pulse")
        target = max(6, n_workers * 4)
        while pulse_pending + pulse_active < target:
            enqueue_task(
                root,
                {
                    "kind": "compute_pulse",
                    "requires": ["pulse"],
                    "priority": 25,
                    "seconds": 60,
                    "timeout_s": 180,
                    "detail_de": "Intensiv-Puls — Spread",
                },
            )
            pulse_pending += 1
            log.append("enqueue compute_pulse+")

        for _ in range(max(0, 3 - sum(1 for t in pending if t.get("kind") == "hub_verify"))):
            enqueue_task(
                root,
                {
                    "kind": "hub_verify",
                    "requires": ["pulse"],
                    "priority": 10,
                    "timeout_s": 30,
                    "detail_de": "Hub-Check (Spread intensiv)",
                },
            )
            log.append("enqueue hub_verify+")
    except Exception as exc:
        log.append(f"demand: {exc}"[:80])

    try:
        from analytics.h1_federation_dispatch import sync_h1_federation_tasks, sync_h1_naive_prep_tasks

        for _ in range(2):
            log.extend(sync_h1_naive_prep_tasks(root))
            log.extend(sync_h1_federation_tasks(root))
    except Exception as exc:
        log.append(f"h1_sync: {exc}"[:80])

    return log


def _boost_h1_prefetch(root: Path, *, prefetch: int = 32) -> None:
    path = root / _DISPATCH_REL
    if not path.is_file():
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    doc["prefetch_chunks"] = max(int(doc.get("prefetch_chunks") or 16), prefetch)
    doc["enqueue_tasks"] = True
    doc["mode"] = "execute"
    atomic_write_json(path, doc)


def _ensure_local_worker_daemon(root: Path) -> Dict[str, Any]:
    """Lokaler Full-Worker — kürzeres Intervall wie beim ersten Bash-Lauf."""
    try:
        from analytics.king_weg_b import is_orchestrate_only

        if is_orchestrate_only():
            return {
                "ok": True,
                "skipped": True,
                "detail_de": "Weg B — kein lokaler Worker auf König",
            }
    except Exception:
        pass
    root = Path(root)
    py = _py(root)
    script = root / "tools/preview_federation_worker.py"
    if not script.is_file():
        return {"ok": False, "message_de": "preview_federation_worker fehlt"}
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "preview_federation_worker.py --join"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return {"ok": True, "reused": True, "detail_de": "Worker-Daemon läuft bereits"}
    except OSError:
        pass
    log_path = root / "evidence/federation_local_worker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        f"cd {root} && nohup {py} tools/preview_federation_worker.py "
        f"--join http://127.0.0.1:17890 --no-preview --interval 30 "
        f">> {log_path} 2>&1 &"
    )
    subprocess.Popen(cmd, shell=True, cwd=str(root))
    return {"ok": True, "started": True, "interval_s": 30, "detail_de": "Worker-Daemon gestartet (30s)"}


def intensify_spread(
    root: Path,
    *,
    remote_mode: str = "auto",
) -> Dict[str, Any]:
    """Voller Spread wie spread-remote + world + timers + Demand-Boost."""
    root = Path(root)
    log: List[str] = []

    try:
        from analytics.world_spread import activate_world_spread

        world = activate_world_spread(root, remote_mode=remote_mode, force_export=True)
        log.append(f"world_spread:{world.get('ok')}")
    except Exception as exc:
        world = {"ok": False, "error_de": str(exc)[:160]}

    try:
        from analytics.community_spread_plan import (
            ensure_federation_spread_security,
            run_spread_tick,
            sync_spread_timers,
            _write_forum_draft,
        )

        sec = ensure_federation_spread_security(root)
        log.append(f"security:{sec.get('ok')}")
        _boost_h1_prefetch(root, prefetch=32)
        log.append("h1_prefetch=32")
        demand_log = intensify_federation_demand(root)
        log.extend(demand_log)
        try:
            timers = sync_spread_timers(root)
            log.append(f"timers:{len(timers)}")
        except Exception as exc:
            log.append(f"timers:{exc}"[:50])
        tick = run_spread_tick(root, execute=True)
        log.append(f"tick:{tick.get('next_phase_id')}")
        forum = _write_forum_draft(root)
        log.append(f"forum:{forum.name}")
    except Exception as exc:
        tick = {"error_de": str(exc)[:160]}

    try:
        from analytics.h1_distribute import activate_h1_distribution

        dist = activate_h1_distribution(root)
        log.append("h1_distribute_refresh")
    except Exception as exc:
        dist = {"error_de": str(exc)[:120]}

    worker = _ensure_local_worker_daemon(root)
    log.append(str(worker.get("detail_de") or "worker"))

    try:
        from analytics.federation_assignments import build_assignment_status
        from analytics.preview_federation import build_share_package
        from analytics.remote_hub_access import remote_access_status

        assignments = build_assignment_status(root)
        pkg = build_share_package(root)
        remote = remote_access_status(root)
    except Exception as exc:
        assignments = {}
        pkg = {}
        remote = {"error_de": str(exc)[:120]}

    share_url = str(pkg.get("share_url") or world.get("public_base_url") or "")
    whatsapp = (
        f"Active Alpha — Rechenleistung (Spread intensiv):\n"
        f"1) ZIP: active_alpha_worker_LITE.zip\n"
        f"2) Doppelklick: Windows_START.bat / Linux_START.sh\n"
        f"3) Python 3 — kein Geld, kein Broker\n"
        f"Join: {pkg.get('join_url') or world.get('join_url')}\n"
        f"Cockpit: {share_url}"
    )

    out: Dict[str, Any] = {
        "ok": bool(world.get("ok")),
        "schema_version": 1,
        "intensified_at_utc": _utc_now(),
        "headline_de": (
            f"Spread intensiv — {assignments.get('headline_de') or world.get('headline_de')}"
        ),
        "world": world,
        "assignments": assignments,
        "worker_daemon": worker,
        "spread_tick": tick,
        "remote": remote,
        "share": pkg,
        "whatsapp_de": whatsapp,
        "bash_de": "bash tools/spread_intensify.sh",
        "log": log,
        "next_step_de": "ZIP + Join-Link teilen · /h1-workers · Forum-Entwurf in evidence/community_spread_forum_de.txt",
    }
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out
