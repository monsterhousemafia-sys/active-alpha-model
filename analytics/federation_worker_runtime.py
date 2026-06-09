"""Gemeinsame Worker-Runtime — Heartbeat + Compute-Pull."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


def post_json(url: str, payload: dict, *, timeout: float = 60.0) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}


def hub_health(hub: str) -> bool:
    try:
        with urllib.request.urlopen(f"{hub.rstrip('/')}/api/health", timeout=12) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def pull_and_run_tasks(
    root: Path,
    hub: str,
    *,
    worker_id: str,
    capabilities: List[str],
    cpus: int,
    bundle_kind: str = "lite",
) -> List[Dict[str, Any]]:
    from analytics.federation_compute import execute_task

    hub = hub.rstrip("/")
    results: List[Dict[str, Any]] = []
    for _ in range(3):
        try:
            pull = post_json(
                f"{hub}/api/worker/pull",
                {
                    "worker_id": worker_id,
                    "capabilities": capabilities,
                    "cpus": cpus,
                    "bundle_kind": bundle_kind,
                },
                timeout=30,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            break
        task = pull.get("task")
        if not task:
            break
        tid = str(task.get("id") or "")
        out = execute_task(root, task, hub_url=hub)
        try:
            post_json(
                f"{hub}/api/worker/complete",
                {"worker_id": worker_id, "task_id": tid, "ok": bool(out.get("ok")), "result": out},
                timeout=120,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
        results.append({"task_id": tid, "kind": task.get("kind"), "result": out})
        if not out.get("ok"):
            break
    return results


def run_worker_cycle(
    root: Path,
    hub: str,
    *,
    contribute_fn,
    worker_id: str,
    capabilities: List[str],
    cpus: int,
    bundle_kind: str = "lite",
) -> Dict[str, Any]:
    hub = hub.rstrip("/")
    if not hub_health(hub):
        raise urllib.error.URLError(f"Hub nicht erreichbar: {hub}/api/health")
    contrib = contribute_fn()
    tasks = pull_and_run_tasks(
        root,
        hub,
        worker_id=worker_id,
        capabilities=capabilities,
        cpus=cpus,
        bundle_kind=bundle_kind,
    )
    return {"contribute": contrib, "tasks": tasks, "worker_id": worker_id}


def run_worker_daemon(
    root: Path,
    hub: str,
    *,
    contribute_fn,
    worker_id: str,
    capabilities: List[str],
    cpus: int,
    bundle_kind: str = "lite",
    interval_s: int = 120,
) -> int:
    print(
        f"[worker] Hub={hub} · CPUs={cpus} · caps={','.join(capabilities)} · {interval_s}s",
        flush=True,
    )
    backoff = 0
    while True:
        try:
            out = run_worker_cycle(
                root,
                hub,
                contribute_fn=contribute_fn,
                worker_id=worker_id,
                capabilities=capabilities,
                cpus=cpus,
                bundle_kind=bundle_kind,
            )
            print(json.dumps(out, ensure_ascii=False), flush=True)
            backoff = 0
        except urllib.error.URLError as exc:
            backoff = min(300, max(30, (backoff or 15) * 2))
            print(f"[worker] Hub-Fehler: {exc} · retry {backoff}s", flush=True)
            time.sleep(backoff)
            continue
        except Exception as exc:
            backoff = min(180, max(20, (backoff or 10) * 2))
            print(f"[worker] Fehler: {exc} · retry {backoff}s", flush=True)
            time.sleep(backoff)
            continue
        time.sleep(max(45, interval_s))
