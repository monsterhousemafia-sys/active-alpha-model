"""Weg B — König orchestriert nur, externe Worker rechnen H1-Prep."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/king_weg_b_latest.json")
_ORCHESTRATOR_REL = Path("control/h1_orchestrator_model.json")
_DISPATCH_REL = Path("control/H1_FEDERATION_DISPATCH.json")
_BENCHMARK_EVIDENCE = Path("evidence/h1_benchmark_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_orchestrate_only() -> bool:
    for key in ("AA_KING_ORCHESTRATE_ONLY", "AA_WEG_B"):
        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def _pgrep_pids(pattern: str) -> List[int]:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            return []
        out: List[int] = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                out.append(int(line))
        return out
    except (OSError, subprocess.TimeoutExpired):
        return []


def _terminate_pids(pids: List[int], *, label: str) -> List[int]:
    stopped: List[int] = []
    for pid in pids:
        if pid <= 1:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except OSError:
            continue
    if stopped:
        import time

        time.sleep(1.5)
        for pid in list(stopped):
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    return stopped


def stop_king_local_compute(root: Path) -> Dict[str, Any]:
    """König rechnet nicht — nur Hub, Tunnel, Merge, Seal."""
    root = Path(root)
    patterns = (
        "generate_h1_naive_benchmark.py",
        "preview_federation_worker.py --join",
    )
    stopped: Dict[str, List[int]] = {}
    for pat in patterns:
        pids = _pgrep_pids(pat)
        if pids:
            stopped[pat] = _terminate_pids(pids, label=pat)

    bench_ev = root / _BENCHMARK_EVIDENCE
    if bench_ev.is_file():
        try:
            doc = json.loads(bench_ev.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and str(doc.get("status") or "") in {"started", "generating"}:
                doc["status"] = "deferred_federation"
                doc["message_de"] = "Weg B — Benchmark wartet auf Worker-Prep-Chunks"
                doc["updated_at_utc"] = _utc_now()
                atomic_write_json(bench_ev, doc)
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "ok": True,
        "stopped": stopped,
        "detail_de": "König-Compute gestoppt — nur Orchestrierung aktiv",
    }


def reclaim_offline_active_tasks(root: Path) -> List[str]:
    """Aktive Tasks an offline Worker zurück in pending."""
    root = Path(root)
    from analytics.federation_compute import load_compute_queue, save_compute_queue
    from analytics.preview_federation import load_federation_state, prune_stale_workers

    prune_stale_workers(root)
    state = load_federation_state(root)
    workers_raw = state.get("workers") or {}
    if isinstance(workers_raw, dict):
        worker_items = workers_raw.values()
    else:
        worker_items = workers_raw
    online = set()
    for w in worker_items:
        if not isinstance(w, dict):
            continue
        if str(w.get("role") or "") == "compute":
            online.add(str(w.get("worker_id") or ""))
    doc = load_compute_queue(root)
    active: Dict[str, Any] = dict(doc.get("active") or {})
    pending: List[Dict[str, Any]] = list(doc.get("pending") or [])
    log: List[str] = []
    kept: Dict[str, Any] = {}
    for tid, task in active.items():
        wid = str(task.get("worker_id") or "")
        if wid and wid in online:
            kept[tid] = task
            continue
        task = dict(task)
        task["status"] = "pending"
        for k in ("assigned_at_utc", "worker_id", "assigned_cpus"):
            task.pop(k, None)
        task["reclaimed_at_utc"] = _utc_now()
        task["reclaim_reason_de"] = "Worker offline — Weg B"
        pending.append(task)
        log.append(f"reclaim_offline {task.get('kind')} {tid}")
    if log:
        doc["active"] = kept
        doc["pending"] = pending
        save_compute_queue(root, doc)
    return log


def update_orchestrator_weg_b(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / _ORCHESTRATOR_REL
    doc: Dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            doc = loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass
    doc.update(
        {
            "schema_version": 1,
            "weg_b_active": True,
            "weg_b_at_utc": _utc_now(),
            "cursor_role_de": "Vasall — Code/Evidence; König rechnet H1-Prep nicht lokal",
            "mom_1_benchmark_lane": {
                "artifact": "validation_runs/*/naive_mom_1_daily_returns.csv",
                "scope": "federation",
                "runtime_profile": "worker_h1",
                "path_dependent": True,
                "commands_de": ["/h1-workers", "/h1-benchmark --wait", "/h1-watch"],
                "detail_de": "Prep-Chunks von externen Workern — König merged + Seal",
            },
        }
    )
    atomic_write_json(path, doc)

    dispatch_path = root / _DISPATCH_REL
    dispatch: Dict[str, Any] = {}
    if dispatch_path.is_file():
        try:
            loaded = json.loads(dispatch_path.read_text(encoding="utf-8"))
            dispatch = loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass
    dispatch["min_worker_bundle"] = "full"
    dispatch["detail_de"] = (
        "Weg B: H1-Prep nur auf Full-Workern (lädt features.parquet vom König)"
    )
    atomic_write_json(dispatch_path, dispatch)
    return {"ok": True, "orchestrator": str(path), "min_worker_bundle": "full"}


def build_recruit_package(root: Path, *, world: Dict[str, Any], full_export: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    join_url = str(world.get("join_url") or "")
    public_url = str(world.get("public_base_url") or "")
    lite_zip = str(world.get("lite_zip") or root.parent / "active_alpha_worker_LITE.zip")
    full_dest = str(full_export.get("full_dest") or "")
    full_zip = str(full_export.get("full_zip") or "")

    steps_de = [
        "Weg B — König allein rechnet nicht. Mindestens 1 externer Full-Worker nötig.",
        f"1. Full-Bundle holen: {full_zip or 'König sendet active_alpha_worker_FULL.zip'}",
        "2. Entpacken → im Ordner: .venv/bin/python3 tools/preview_federation_worker.py --join <URL> --no-preview",
        f"3. Join-URL: {join_url}",
        f"4. Health: {public_url}/api/health",
        "5. Worker lädt features.parquet (~183 MB) vom König, liefert naive-prep-*.pkl zurück",
        "Lite-ZIP reicht nur für Pulse — H1-Seal braucht Full-Worker!",
    ]
    whatsapp = (
        "Active Alpha — H1 Rechenleistung (Weg B)\n"
        "König orchestriert, du rechnest mom_1-Prep.\n"
        f"1) Full-ZIP vom König\n"
        f"2) Start: preview_federation_worker --join {join_url}\n"
        f"3) ~183 MB Daten werden automatisch geladen\n"
        "Kein Geld, kein Broker — nur CPU."
    )
    return {
        "join_url": join_url,
        "public_base_url": public_url,
        "lite_zip": lite_zip,
        "full_dest": full_dest,
        "full_zip": full_zip,
        "steps_de": steps_de,
        "whatsapp_de": whatsapp,
        "h1_asset_de": "GET /api/h1/asset?run_dir=...&file=features.parquet",
        "h1_upload_de": "POST /api/h1/artifact/upload",
    }


def ensure_full_worker_export(root: Path) -> Dict[str, Any]:
    """Full-Worker-Bundle für H1-Prep exportieren."""
    root = Path(root)
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    from analytics.worker_export_sync import validate_worker_export_dest

    dest = validate_worker_export_dest(root, root.parent / "active_alpha_worker_FULL")
    zip_path = dest.parent / "active_alpha_worker_FULL.zip"
    env = dict(os.environ)
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_LINUX_NATIVE_APP"] = "1"
    proc = subprocess.run(
        ["bash", str(root / "tools/preview_export_worker_bundle.sh"), str(dest)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    out: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "export_rc": proc.returncode,
        "full_dest": str(dest),
        "full_zip": str(zip_path),
    }
    if dest.is_dir() and not zip_path.is_file():
        try:
            import shutil

            shutil.make_archive(str(zip_path.with_suffix("")), "zip", root=dest.parent, base_dir=dest.name)
        except OSError as exc:
            out["zip_error_de"] = str(exc)[:120]
    if zip_path.is_file():
        out["full_zip_bytes"] = zip_path.stat().st_size
        out["ok"] = True
    if proc.stdout.strip():
        try:
            pkg = json.loads(proc.stdout)
            if isinstance(pkg, dict):
                out["join_url"] = pkg.get("join_url")
        except json.JSONDecodeError:
            out["stdout_tail"] = proc.stdout[-500:]
    if proc.returncode != 0 and proc.stderr:
        out["stderr_tail"] = proc.stderr[-500:]
    return out


def activate_weg_b(root: Path, *, remote_mode: str = "auto", export_full: bool = True) -> Dict[str, Any]:
    """Weg B aktivieren: König solo aus, Welt ein, H1-Queue bereit."""
    root = Path(root)
    os.environ["AA_WEG_B"] = "1"
    os.environ["AA_KING_ORCHESTRATE_ONLY"] = "1"
    log: List[str] = []

    stop = stop_king_local_compute(root)
    log.append(f"stop:{len(stop.get('stopped') or {})}")

    reclaimed = reclaim_offline_active_tasks(root)
    log.extend(reclaimed)

    orch = update_orchestrator_weg_b(root)
    log.append("orchestrator:weg_b")

    try:
        from tools.preview_hub import ensure_hub_running

        ensure_hub_running(root, restart=False)
        log.append("hub_online")
    except Exception as exc:
        log.append(f"hub:{exc}"[:60])

    world: Dict[str, Any] = {}
    try:
        from analytics.world_spread import activate_world_spread

        world = activate_world_spread(root, remote_mode=remote_mode, force_export=True)
        log.append(f"world:{world.get('ok')}")
    except Exception as exc:
        world = {"ok": False, "error_de": str(exc)[:160]}

    full_export: Dict[str, Any] = {"ok": False, "skipped": not export_full}
    if export_full:
        try:
            full_export = ensure_full_worker_export(root)
            log.append(f"full_export:{full_export.get('export_rc')}")
        except Exception as exc:
            full_export = {"ok": False, "error_de": str(exc)[:160]}

    dist: Dict[str, Any] = {}
    try:
        from analytics.h1_distribute import activate_h1_distribution

        dist = activate_h1_distribution(root)
        log.append("h1_distribute")
    except Exception as exc:
        dist = {"error_de": str(exc)[:120]}

    recruit = build_recruit_package(root, world=world, full_export=full_export)

    assignments: Dict[str, Any] = {}
    try:
        from analytics.federation_assignments import build_assignment_status

        assignments = build_assignment_status(root, reclaim_stale=True)
    except Exception as exc:
        assignments = {"error_de": str(exc)[:120]}

    prep = assignments.get("prep_artifacts") or {}
    workers_n = len(assignments.get("workers") or [])

    out: Dict[str, Any] = {
        "ok": bool(world.get("ok")),
        "schema_version": 1,
        "mode": "weg_b",
        "activated_at_utc": _utc_now(),
        "headline_de": (
            f"Weg B aktiv — {workers_n} Worker online · {prep.get('count', 0)} Prep-Chunks"
            if workers_n
            else f"Weg B aktiv — Join teilen: {recruit.get('join_url')}"
        ),
        "stop_local_compute": stop,
        "reclaimed": reclaimed,
        "orchestrator": orch,
        "world": {
            "join_url": world.get("join_url"),
            "public_base_url": world.get("public_base_url"),
            "lite_zip": world.get("lite_zip"),
            "tunnel_stable": world.get("tunnel_stable"),
        },
        "full_export": full_export,
        "recruit": recruit,
        "distribute": {
            "headline_de": dist.get("headline_de"),
            "queue_pending_total": dist.get("queue_pending_total"),
        },
        "assignments": {
            "headline_de": assignments.get("headline_de"),
            "workers_online": workers_n,
            "prep_count": prep.get("count", 0),
        },
        "next_step_de": (
            "Full-ZIP + Join-Link an mindestens 1 externen PC senden · "
            "dann /h1-workers bis artifact_received"
        ),
        "log": log,
    }
    atomic_write_json(root / _EVIDENCE_REL, out)

    recruit_path = root / "evidence/king_weg_b_recruit_de.txt"
    recruit_lines = [
        recruit.get("whatsapp_de") or "",
        "",
        "---",
        "",
        *(recruit.get("steps_de") or []),
    ]
    recruit_path.write_text("\n".join(recruit_lines) + "\n", encoding="utf-8")
    return out


def format_weg_b_de(root: Path) -> str:
    path = Path(root) / _EVIDENCE_REL
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            lines = [f"**{doc.get('headline_de')}**"]
            recruit = doc.get("recruit") or {}
            for step in recruit.get("steps_de") or []:
                lines.append(step)
            lines.append(str(doc.get("next_step_de") or ""))
            return "\n".join(lines)
        except (json.JSONDecodeError, OSError):
            pass
    doc = activate_weg_b(root)
    return format_weg_b_de(root) if (root / _EVIDENCE_REL).is_file() else json.dumps(doc, ensure_ascii=False)
