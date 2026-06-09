"""H1-Aufgabenverteilung aktivieren — König enqueued, Worker rechnen."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/H1_FEDERATION_DISPATCH.json")
_EVIDENCE_REL = Path("evidence/h1_distribute_latest.json")
_ORCHESTRATOR_REL = Path("control/h1_orchestrator_model.json")


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


def activate_distribution_config(root: Path, *, prefetch_chunks: int = 16) -> Dict[str, Any]:
    """Schaltet Federation von plan_only auf execute + enqueue."""
    root = Path(root)
    path = root / _CONFIG_REL
    cfg = _load_json(path)
    cfg.update(
        {
            "schema_version": 1,
            "enabled": True,
            "mode": "execute",
            "enqueue_tasks": True,
            "prefetch_chunks": max(4, int(prefetch_chunks)),
            "detail_de": (
                "Verteilung aktiv: Path-Sim-Chunks + mom_1-Prep an Worker. "
                "König orchestriert, merge + Seal lokal."
            ),
        }
    )
    atomic_write_json(path, cfg)

    orch = _load_json(root / _ORCHESTRATOR_REL)
    fed = dict(orch.get("federation_legion_lane") or {})
    fed.update(
        {
            "scope": "active",
            "active_for_mom_1_seal": True,
            "mode": "execute",
            "purpose_de": "Path-Sim + mom_1-Prep-Chunks an Worker — König merged Ergebnisse",
        }
    )
    orch["federation_legion_lane"] = fed
    orch["distributed_at_utc"] = _utc_now()
    atomic_write_json(root / _ORCHESTRATOR_REL, orch)
    return cfg


def activate_h1_distribution(root: Path, *, prefetch_chunks: int = 16) -> Dict[str, Any]:
    """Aufgaben jetzt verteilen: Config, Queue, Path-Chunks, mom_1-Prep."""
    root = Path(root)
    cfg = activate_distribution_config(root, prefetch_chunks=prefetch_chunks)
    log: List[str] = []

    try:
        from analytics.federation_compute import reclaim_stale_active_tasks, sync_compute_demand

        log.extend(reclaim_stale_active_tasks(root))
    except Exception as exc:
        log.append(f"reclaim: {exc}"[:80])

    path_log: List[str] = []
    naive_log: List[str] = []
    plan: Dict[str, Any] = {}
    try:
        from analytics.h1_federation_dispatch import prepare_h1_dispatch

        plan = prepare_h1_dispatch(root, sync_tasks=True)
        path_log = list(plan.get("sync_log") or [])
        naive_log = list(plan.get("naive_prep_sync_log") or [])
    except Exception as exc:
        plan = {"error_de": str(exc)[:200]}
    try:
        from analytics.h1_federation_dispatch import sync_h1_naive_prep_tasks

        extra = sync_h1_naive_prep_tasks(root)
        if extra:
            naive_log = list(naive_log) + extra
    except Exception as exc:
        naive_log.append(f"sync_naive_prep: {exc}"[:80])
    try:
        from analytics.h1_federation_dispatch import sync_h1_federation_tasks

        extra_path = sync_h1_federation_tasks(root)
        if extra_path:
            path_log = list(path_log) + extra_path
    except Exception as exc:
        path_log.append(f"sync_path: {exc}"[:80])

    try:
        from analytics.federation_compute import sync_compute_demand

        log.extend(sync_compute_demand(root))
    except Exception as exc:
        log.append(f"sync_demand: {exc}"[:80])

    try:
        from analytics.federation_compute import build_utilization_summary, load_compute_queue

        util = build_utilization_summary(root)
        queue = load_compute_queue(root)
    except Exception as exc:
        util = {"error_de": str(exc)[:120]}
        queue = {}

    pending_kinds: Dict[str, int] = {}
    for t in list(queue.get("pending") or []):
        k = str(t.get("kind") or "unknown")
        pending_kinds[k] = pending_kinds.get(k, 0) + 1

    out = {
        "ok": True,
        "schema_version": 1,
        "activated_at_utc": _utc_now(),
        "config": cfg,
        "path_sync_log": path_log,
        "naive_prep_sync_log": naive_log,
        "dispatch": {
            "headline_de": plan.get("headline_de"),
            "chunks_pending_worker": plan.get("chunks_pending_worker"),
            "chunks_total": plan.get("chunks_total"),
            "workers_online": plan.get("workers_online"),
        },
        "queue_pending_by_kind": pending_kinds,
        "queue_pending_total": len(queue.get("pending") or []),
        "queue_active_total": len(queue.get("active") or {}),
        "utilization": util,
        "headline_de": (
            f"Verteilung aktiv — {len(queue.get('pending') or [])} Jobs in Queue "
            f"({sum(pending_kinds.values())} Tasks, Worker online: {plan.get('workers_online', 0)})"
        ),
        "next_step_de": (
            "Worker starten (preview-export-lite / universal_preview_worker) · "
            "König: /h1-benchmark --wait nach Prep-Merge"
        ),
        "log": log,
    }
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out


def format_distribute_de(root: Path) -> str:
    doc = activate_h1_distribution(root)
    lines = [
        f"**{doc.get('headline_de')}**",
        f"Queue: {doc.get('queue_pending_total')} pending · {doc.get('queue_active_total')} aktiv",
    ]
    for kind, n in sorted((doc.get("queue_pending_by_kind") or {}).items()):
        lines.append(f"• {kind}: {n}")
    disp = doc.get("dispatch") or {}
    if disp.get("chunks_pending_worker"):
        lines.append(f"Path-Chunks: {disp.get('chunks_pending_worker')} für Worker")
    for line in doc.get("naive_prep_sync_log") or []:
        lines.append(f"Prep: {line}")
    lines.append(str(doc.get("next_step_de") or ""))
    return "\n".join(lines)
