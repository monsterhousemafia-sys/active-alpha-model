#!/usr/bin/env python3
"""
Universal Lite Worker OS — Worker
Win / macOS / Linux · nur Python 3.8+ · keine Installation nötig.

Doppelklick: Windows_START.bat · Mac_START.command · Linux_START.sh
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import os
import platform
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOIN_NAME = "preview_worker_join.json"
_WORKER_STATE_DIR = Path(".local/share/ulwo-worker/state")
_WORKER_ID_FILE = "worker_id"


def bundle_dir() -> Path:
    return Path(__file__).resolve().parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_join_config() -> dict:
    path = bundle_dir() / JOIN_NAME
    if not path.is_file():
        raise FileNotFoundError(
            f"{JOIN_NAME} fehlt — Bundle vom König neu laden (preview-export-lite)"
        )
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not str(doc.get("hub_join_url") or "").strip():
        raise ValueError("hub_join_url fehlt in preview_worker_join.json")
    return doc


def stable_worker_id() -> str:
    host = socket.gethostname().strip().lower()
    host = "".join(c if c.isalnum() or c in "-_" else "-" for c in host) or "host"
    root = Path.home() / _WORKER_STATE_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / _WORKER_ID_FILE
    if path.is_file():
        wid = path.read_text(encoding="utf-8").strip()
        if wid:
            return wid
    wid = f"{host}-{uuid.uuid4().hex[:8]}"
    path.write_text(wid + "\n", encoding="utf-8")
    return wid


def collect_contribution(join_doc: dict) -> dict:
    mem_free_gb = None
    if platform.system() == "Linux":
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                lines = {k: v for k, v in (ln.split(":", 1) for ln in fh if ":" in ln)}
            avail = int(str(lines.get("MemAvailable", "0")).split()[0])
            mem_free_gb = round(avail / (1024 * 1024), 2)
        except OSError:
            pass
    hub = str(join_doc.get("hub_join_url") or "").strip()
    try:
        from analytics.remote_hub_access import is_remote_reachable_url

        remote_join = is_remote_reachable_url(hub)
    except Exception:
        remote_join = hub.startswith("https://")
    caps = ["heartbeat", "pulse"]
    payload = {
        "worker_id": stable_worker_id(),
        "hostname": socket.gethostname(),
        "role": "compute",
        "bundle_kind": "lite",
        "capabilities": caps,
        "remote_join": remote_join,
        "cpus": max(1, int(os.cpu_count() or 1)),
        "mem_free_gb": mem_free_gb,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python": platform.python_version(),
        "headline_de": f"{platform.system()} · {os.cpu_count() or 1} CPU-Kerne bereitgestellt",
        "preview_ok": True,
        "preview_passed": 0,
        "preview_total": 0,
        "h1_running": False,
        "updated_at_utc": _utc_now(),
    }
    token = str(join_doc.get("join_token") or "").strip()
    if token:
        payload["join_token"] = token
    return payload


def hub_health(hub: str) -> bool:
    try:
        with urllib.request.urlopen(f"{hub.rstrip('/')}/api/health", timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _post_json(url: str, payload: dict, *, timeout: float = 60.0) -> dict:
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


def _pulse_unit(n: int) -> float:
    t0 = time.perf_counter()
    x = float(n % 1000) + 1.0
    for i in range(800_000):
        x = math.sin(x) * math.cos(x) + (i % 7) * 0.0001
    return time.perf_counter() - t0


def _run_lite_task(task: dict, hub: str) -> dict:
    kind = str(task.get("kind") or "")
    cpus = max(1, min(int(task.get("assigned_cpus") or os.cpu_count() or 1), os.cpu_count() or 1))
    if kind == "compute_pulse":
        seconds = max(10, int(task.get("seconds") or 45))
        deadline = time.monotonic() + seconds
        total = 0.0
        rounds = 0
        while time.monotonic() < deadline:
            with multiprocessing.Pool(processes=cpus) as pool:
                total += sum(pool.map(_pulse_unit, range(cpus)))
            rounds += 1
        return {"ok": True, "cpu_seconds": round(total, 2), "rounds": rounds, "cpus": cpus}
    if kind == "hub_verify":
        t0 = time.perf_counter()
        with urllib.request.urlopen(f"{hub.rstrip('/')}/api/health", timeout=15) as resp:
            body = resp.read()
        return {
            "ok": resp.status == 200,
            "health_sha": hashlib.sha256(body).hexdigest()[:16],
            "cpu_seconds": round(time.perf_counter() - t0, 2),
        }
    return {"ok": False, "message_de": f"Lite-Worker kann {kind} nicht"}


def _pull_and_run(hub: str, worker_id: str, cpus: int) -> list:
    hub = hub.rstrip("/")
    results = []
    for _ in range(2):
        pull = _post_json(
            f"{hub}/api/worker/pull",
            {
                "worker_id": worker_id,
                "capabilities": ["heartbeat", "pulse"],
                "cpus": cpus,
                "bundle_kind": "lite",
            },
        )
        task = pull.get("task")
        if not task:
            break
        tid = str(task.get("id") or "")
        out = _run_lite_task(task, hub)
        _post_json(
            f"{hub}/api/worker/complete",
            {"worker_id": worker_id, "task_id": tid, "ok": bool(out.get("ok")), "result": out},
        )
        results.append({"task_id": tid, "kind": task.get("kind"), "result": out})
    return results


def contribute(hub: str, join_doc: dict) -> dict:
    hub = hub.rstrip("/")
    if not hub_health(hub):
        raise urllib.error.URLError(
            f"König-Hub nicht erreichbar: {hub}/api/health\n"
            "Prüfe: gleiches WLAN/LAN, Firewall auf König (Port 17890)."
        )
    payload = collect_contribution(join_doc)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{hub}/api/worker/contribute",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        out = json.loads(raw) if raw.strip() else {}
    if not out.get("ok"):
        raise RuntimeError(str(out.get("message_de") or "Beitritt abgelehnt"))
    return {"contribute": out, "worker_id": payload["worker_id"], "hub": hub}


def run_daemon(hub: str, join_doc: dict, interval_s: int) -> int:
    wid = stable_worker_id()
    cpus = max(1, int(os.cpu_count() or 1))
    print(f"[Active Alpha] Hub={hub} · CPUs={cpus} · Compute aktiv · {interval_s}s", flush=True)
    backoff = 0
    while True:
        try:
            out = contribute(hub, join_doc)
            legion = (out.get("contribute") or {}).get("legion") or {}
            welcome = legion.get("welcome_de")
            if welcome:
                print(f"[Legion] {welcome}", flush=True)
            tasks = _pull_and_run(hub, wid, cpus)
            print(json.dumps({"contribute": out, "tasks": tasks, "legion": legion}, ensure_ascii=False), flush=True)
            backoff = 0
        except Exception as exc:
            backoff = min(300, max(30, (backoff or 15) * 2))
            print(f"[Active Alpha] Fehler: {exc} · retry {backoff}s", flush=True)
            time.sleep(backoff)
            continue
        time.sleep(max(45, interval_s))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Active Alpha — Universal Preview Worker")
    p.add_argument("--once", action="store_true", help="Einmal melden und beenden")
    p.add_argument("--daemon", action="store_true", help="Dauerhaft im Hintergrund melden")
    args = p.parse_args(argv)

    try:
        join_doc = load_join_config()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FEHLER] {exc}", file=sys.stderr)
        return 2

    hub = str(join_doc.get("hub_join_url") or "").strip().rstrip("/")
    interval = int(join_doc.get("worker_interval_s") or 300)

    print("=== Active Alpha — Rechenleistung beitreten ===")
    print(f"System:  {platform.system()} {platform.release()}")
    print(f"CPUs:    {os.cpu_count() or 1}")
    print(f"Hub:     {hub}")
    print("Kein Broker, kein Geld — nur CPU fürs Research-Cockpit.")
    print()

    try:
        wid = stable_worker_id()
        cpus = max(1, int(os.cpu_count() or 1))
        out = contribute(hub, join_doc)
        tasks = _pull_and_run(hub, wid, cpus)
        print("[OK] Beigetreten:", out["worker_id"])
        if tasks:
            print("[OK] Compute-Jobs:", len(tasks))
        print(f"[OK] Command Center: {hub}/")
    except Exception as exc:
        print(f"[FEHLER] {exc}", file=sys.stderr)
        return 1

    if args.once:
        return 0
    if args.daemon or not args.once:
        return run_daemon(hub, join_doc, interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
