#!/usr/bin/env python3
"""Remote Preview-Worker — meldet Rechenleistung an den zentralen Hub."""
from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_PID_REL = Path(".local/share/r3-os/preview_worker.pid")


def _post_json(url: str, payload: dict, *, timeout: float = 30.0) -> dict:
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


def _hub_base(url: str) -> str:
    return str(url or "").strip().rstrip("/")


def _pid_path(root: Path) -> Path:
    return Path.home() / _PID_REL


def _release_daemon_lock() -> None:
    path = Path.home() / _PID_REL
    try:
        if path.is_file() and int(path.read_text(encoding="utf-8").strip()) == os.getpid():
            path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def _acquire_daemon_lock(root: Path) -> bool:
    path = _pid_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            old = int(path.read_text(encoding="utf-8").strip())
            os.kill(old, 0)
            return False
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
    path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    atexit.register(_release_daemon_lock)
    return True


def _hub_health_ok(hub: str) -> bool:
    try:
        with urllib.request.urlopen(f"{hub}/api/health", timeout=8) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def contribute_once(root: Path, hub_url: str, *, run_preview: bool = False) -> dict:
    root = Path(root)
    hub = _hub_base(hub_url)
    if not _hub_health_ok(hub):
        raise urllib.error.URLError(f"Hub nicht erreichbar: {hub}/api/health")

    os.environ["AA_PREVIEW_KING"] = "0"
    os.environ.setdefault("AA_LINUX_NATIVE_APP", "1")
    os.environ["AA_PROJECT_ROOT"] = str(root)

    preview_report = None
    if run_preview:
        try:
            from ui.live_trading_dashboard.gui_preview_harness import run_backend_preview

            steps = run_backend_preview(root, allow_snapshot_refresh=False)
            passed = sum(1 for s in steps if s.get("pass"))
            total = len(steps)
            preview_report = {
                "passed": passed,
                "total": total,
                "overall_pass": passed == total and total > 0,
                "backend_steps": steps,
            }
        except Exception as exc:
            preview_report = {
                "passed": 0,
                "total": 0,
                "overall_pass": False,
                "error_de": str(exc)[:200],
            }

    from analytics.preview_federation import collect_local_contribution, ensure_join_token, stable_worker_id

    doc = collect_local_contribution(root, preview_report=preview_report)
    doc["worker_id"] = stable_worker_id()
    doc["role"] = "compute"
    if not str(doc.get("join_token") or "").strip():
        doc["join_token"] = ensure_join_token(root)
    out = _post_json(f"{hub}/api/worker/contribute", doc)
    if not out.get("ok"):
        raise RuntimeError(str(out.get("message_de") or "contribute fehlgeschlagen"))
    return {"contribute": out, "worker_id": doc["worker_id"]}


def run_daemon(root: Path, hub_url: str, *, interval_s: int = 300, run_preview: bool = False) -> int:
    if not _acquire_daemon_lock(root):
        print("[worker] Daemon läuft bereits — Abbruch", flush=True)
        return 1
    from analytics.federation_compute import worker_capabilities
    from analytics.federation_worker_runtime import run_worker_daemon
    from analytics.preview_federation import stable_worker_id

    caps = worker_capabilities(root, bundle_kind="full")
    wid = stable_worker_id()

    def _contrib():
        return contribute_once(root, hub_url, run_preview=run_preview)

    return run_worker_daemon(
        root,
        hub_url,
        contribute_fn=_contrib,
        worker_id=wid,
        capabilities=caps,
        cpus=max(1, int(os.cpu_count() or 1)),
        bundle_kind="full",
        interval_s=interval_s,
    )


def _resolve_hub(root: Path, explicit: str) -> str:
    if explicit:
        return _hub_base(explicit)
    from analytics.preview_federation import resolve_worker_hub_url

    url = resolve_worker_hub_url(root)
    if url:
        return url
    env = os.environ.get("AA_PREVIEW_HUB_URL", "").strip()
    return _hub_base(env)


def _default_run_preview(root: Path, cli_flag: bool) -> bool:
    if cli_flag:
        return True
    from analytics.preview_federation import worker_join_config

    doc = worker_join_config(root)
    return bool(doc.get("worker_preview_on_heartbeat"))


def main() -> int:
    p = argparse.ArgumentParser(description="Active Alpha Preview Federation Worker")
    p.add_argument("--join", metavar="HUB_URL", help="Hub-URL z.B. http://<hub-host>:17890")
    p.add_argument(
        "--join-from-config",
        action="store_true",
        help="Hub aus control/preview_worker_join.json (Worker-Bundle)",
    )
    p.add_argument("--once", action="store_true", help="Einmal melden, kein Daemon")
    p.add_argument("--interval", type=int, default=0, help="Daemon-Intervall (Sekunden, 0=aus Config)")
    p.add_argument("--preview", action="store_true", help="Voller Backend-Preview pro Heartbeat (langsam)")
    p.add_argument("--no-preview", action="store_true", help="Nur Hardware (Standard für Daemon)")
    args = p.parse_args()

    root = Path(os.environ.get("AA_PROJECT_ROOT", "").strip() or ROOT)
    hub = _resolve_hub(root, args.join or "")
    if not hub:
        p.error("--join, --join-from-config oder preview_worker_join.json / AA_PREVIEW_HUB_URL setzen")

    if args.interval <= 0:
        try:
            from analytics.preview_federation import worker_join_config

            args.interval = int(worker_join_config(root).get("worker_interval_s") or 300)
        except (TypeError, ValueError):
            args.interval = 300

    run_preview = _default_run_preview(root, args.preview)
    if args.no_preview:
        run_preview = False

    if args.once:
        from analytics.federation_compute import worker_capabilities
        from analytics.federation_worker_runtime import run_worker_cycle
        from analytics.preview_federation import stable_worker_id

        out = run_worker_cycle(
            root,
            hub,
            contribute_fn=lambda: contribute_once(root, hub, run_preview=run_preview),
            worker_id=stable_worker_id(),
            capabilities=worker_capabilities(root, bundle_kind="full"),
            cpus=max(1, int(os.cpu_count() or 1)),
            bundle_kind="full",
        )
        print(json.dumps(out, indent=2))
        return 0
    return run_daemon(root, hub, interval_s=args.interval, run_preview=run_preview)


if __name__ == "__main__":
    raise SystemExit(main())
