"""Worker-Zuweisungen prüfen — Task übernommen, aktiv, fertig, Artifact da."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/federation_assignments_latest.json")
_PREP_GLOB = "naive-prep-*.pkl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_utc(ts: str) -> Optional[datetime]:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_seconds(ts: str) -> Optional[float]:
    dt = _parse_utc(ts)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _prep_artifact_path(root: Path, chunk_id: str) -> Optional[Path]:
    cid = str(chunk_id or "").strip()
    if not cid:
        return None
    path = root / "evidence/h1_naive_prep_chunks" / f"{cid}.pkl"
    return path if path.is_file() else None


def build_assignment_status(root: Path, *, reclaim_stale: bool = True) -> Dict[str, Any]:
    """König: Haben Worker Aufgaben übernommen und liefern sie?"""
    root = Path(root)
    if reclaim_stale:
        try:
            from analytics.federation_compute import reclaim_stale_active_tasks

            reclaim_stale_active_tasks(root)
        except Exception:
            pass

    from analytics.federation_compute import build_utilization_summary, load_compute_queue
    from analytics.h1_artifact_transport import list_prep_artifacts
    from analytics.preview_federation import federation_config, load_federation_state, prune_stale_workers

    try:
        prune_stale_workers(root)
    except Exception:
        pass

    cfg = federation_config(root)
    stale_worker_s = int(cfg.get("stale_after_s") or 900)
    state = load_federation_state(root)
    workers_raw = dict(state.get("workers") or {})
    queue = load_compute_queue(root)
    util = build_utilization_summary(root)
    prep_listing = list_prep_artifacts(root)

    workers: List[Dict[str, Any]] = []
    worker_index: Dict[str, Dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    for wid, w in workers_raw.items():
        if str(w.get("role") or "").lower() != "compute":
            continue
        last_seen = str(w.get("last_seen_utc") or "")
        seen_age = _age_seconds(last_seen)
        online = seen_age is not None and seen_age <= stale_worker_s
        row = {
            "worker_id": wid,
            "hostname": w.get("hostname"),
            "cpus": int(w.get("cpus") or 0),
            "online": online,
            "last_seen_utc": last_seen,
            "last_seen_age_s": round(seen_age, 1) if seen_age is not None else None,
            "active_tasks": 0,
            "completed_ok": 0,
        }
        workers.append(row)
        worker_index[wid] = row

    active_rows: List[Dict[str, Any]] = []
    for tid, task in dict(queue.get("active") or {}).items():
        wid = str(task.get("worker_id") or "")
        assigned = str(task.get("assigned_at_utc") or "")
        age = _age_seconds(assigned)
        timeout_s = max(120, int(task.get("timeout_s") or 600))
        kind = str(task.get("kind") or "")
        chunk_id = str(task.get("chunk_id") or "")
        artifact_path = _prep_artifact_path(root, chunk_id) if kind == "h1_naive_prep_chunk" else None
        worker_row = worker_index.get(wid)
        if worker_row:
            worker_row["active_tasks"] = int(worker_row.get("active_tasks") or 0) + 1
        stale_task = age is not None and age > timeout_s
        active_rows.append(
            {
                "task_id": tid,
                "kind": kind,
                "worker_id": wid or None,
                "chunk_id": chunk_id or None,
                "detail_de": task.get("detail_de"),
                "assigned_at_utc": assigned or None,
                "age_s": round(age, 1) if age is not None else None,
                "timeout_s": timeout_s,
                "accepted": bool(wid and assigned),
                "worker_online": bool(worker_row and worker_row.get("online")),
                "stale_risk": stale_task,
                "artifact_received": bool(artifact_path),
                "artifact_path": str(artifact_path.relative_to(root)).replace("\\", "/") if artifact_path else None,
            }
        )

    completed_rows: List[Dict[str, Any]] = []
    for task in reversed(list(queue.get("completed") or [])[-20:]):
        wid = str(task.get("worker_id") or "")
        ok = task.get("status") == "ok"
        if wid in worker_index and ok:
            worker_index[wid]["completed_ok"] = int(worker_index[wid].get("completed_ok") or 0) + 1
        res = dict(task.get("result") or {})
        chunk_id = str(task.get("chunk_id") or res.get("chunk_id") or "")
        completed_rows.append(
            {
                "task_id": task.get("id"),
                "kind": task.get("kind"),
                "worker_id": wid or None,
                "chunk_id": chunk_id or None,
                "ok": ok,
                "completed_at_utc": task.get("completed_at_utc"),
                "artifact_upload_ok": bool((res.get("artifact_upload") or {}).get("ok")),
                "artifact_received": bool(_prep_artifact_path(root, chunk_id)) if chunk_id else False,
            }
        )

    pending = list(queue.get("pending") or [])
    pending_by_kind: Dict[str, int] = {}
    for t in pending:
        k = str(t.get("kind") or "unknown")
        pending_by_kind[k] = pending_by_kind.get(k, 0) + 1

    checks: List[Dict[str, Any]] = []
    online_workers = [w for w in workers if w.get("online")]
    checks.append(
        {
            "id": "workers_online",
            "ok": len(online_workers) >= 1,
            "detail_de": f"{len(online_workers)} Compute-Worker online (Heartbeat < {stale_worker_s}s)",
        }
    )
    accepted = [r for r in active_rows if r.get("accepted")]
    checks.append(
        {
            "id": "tasks_accepted",
            "ok": len(accepted) >= 1 or len(completed_rows) >= 1,
            "detail_de": f"{len(accepted)} aktiv übernommen · {len(completed_rows)} kürzlich fertig",
        }
    )
    orphan_active = [r for r in active_rows if r.get("accepted") and not r.get("worker_online")]
    checks.append(
        {
            "id": "assignee_online",
            "ok": len(orphan_active) == 0,
            "detail_de": "Alle aktiven Tasks haben online Worker"
            if not orphan_active
            else f"{len(orphan_active)} Task(s) an offline Worker",
        }
    )
    stale_active = [r for r in active_rows if r.get("stale_risk")]
    checks.append(
        {
            "id": "not_stale",
            "ok": len(stale_active) == 0,
            "detail_de": "Keine überfälligen aktiven Tasks"
            if not stale_active
            else f"{len(stale_active)} Task(s) über timeout_s",
        }
    )
    h1_active = [r for r in active_rows if r.get("kind") == "h1_naive_prep_chunk"]
    h1_done_artifact = [r for r in completed_rows if r.get("kind") == "h1_naive_prep_chunk" and r.get("artifact_received")]
    checks.append(
        {
            "id": "h1_prep_delivery",
            "ok": int(prep_listing.get("count") or 0) > 0 or not h1_active,
            "detail_de": f"{prep_listing.get('count', 0)} Prep-Chunks auf König · {len(h1_active)} aktiv",
        }
    )

    all_ok = all(c.get("ok") for c in checks)
    headline = (
        f"{len(accepted)} Tasks übernommen · {len(online_workers)} Worker online · "
        f"{prep_listing.get('count', 0)} Prep-Chunks"
        if accepted or completed_rows
        else f"Keine Übernahme — {len(pending)} pending · {len(online_workers)} Worker online"
    )

    doc = {
        "ok": all_ok,
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": headline,
        "utilization": util,
        "workers": workers,
        "active_assignments": active_rows,
        "completed_recent": completed_rows[:12],
        "pending_by_kind": pending_by_kind,
        "pending_total": len(pending),
        "prep_artifacts": prep_listing,
        "assurance_checks": checks,
        "next_step_de": (
            "Worker starten oder /h1-distribute"
            if not online_workers
            else "Auf complete/artifact warten — /h1-workers erneut"
            if accepted and not prep_listing.get("count")
            else "Benchmark-Merge: /h1-benchmark --wait"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def format_assignments_de(root: Path) -> str:
    doc = build_assignment_status(root)
    lines = [f"**{doc.get('headline_de')}**"]
    for w in doc.get("workers") or []:
        flag = "online" if w.get("online") else "offline"
        lines.append(
            f"• {w.get('worker_id')}: {flag} · {w.get('active_tasks', 0)} aktiv · "
            f"{w.get('completed_ok', 0)} fertig"
        )
    for row in doc.get("active_assignments") or []:
        lines.append(
            f"→ {row.get('kind')} {row.get('chunk_id') or ''} @ {row.get('worker_id')} "
            f"({row.get('age_s')}s)"
        )
    for chk in doc.get("assurance_checks") or []:
        mark = "OK" if chk.get("ok") else "!"
        lines.append(f"[{mark}] {chk.get('detail_de')}")
    lines.append(str(doc.get("next_step_de") or ""))
    return "\n".join(lines)
