"""Stabiler König-Server — ein Hub, Tunnel, Autostart."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json


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


def list_hub_pids(root: Path) -> List[int]:
    root = Path(root).resolve()
    pids: List[int] = []
    try:
        proc = subprocess.run(
            ["pgrep", "-af", "preview_hub.py"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            if "pgrep" in line:
                continue
            parts = line.strip().split(None, 1)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            cmd = parts[1]
            if "preview_hub.py" not in cmd:
                continue
            proc_root = _process_root(pid)
            if proc_root == root or str(root) in cmd:
                pids.append(pid)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return sorted(set(pids))


def _process_root(pid: int) -> Optional[Path]:
    try:
        cwd = Path(f"/proc/{pid}/cwd").resolve()
        if (cwd / "tools/preview_hub.py").is_file():
            return cwd
    except OSError:
        pass
    return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_duplicate_hubs(root: Path, *, keep_pid: Optional[int] = None) -> List[int]:
    """Alle doppelten Hub-Prozesse dieses Projekts beenden."""
    root = Path(root)
    meta_pid = int(_load_json(root / "evidence/preview_hub.json").get("pid") or 0)
    keeper = keep_pid or (meta_pid if _pid_alive(meta_pid) else None)
    killed: List[int] = []
    for pid in list_hub_pids(root):
        if keeper and pid == keeper and _pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except PermissionError:
            try:
                subprocess.run(["kill", "-9", str(pid)], check=False, timeout=3)
                killed.append(pid)
            except (OSError, subprocess.TimeoutExpired):
                pass
        except OSError:
            pass
    if killed:
        time.sleep(0.5)
        for pid in killed:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    return killed


def check_hub_health(url: str, *, timeout: float = 10.0) -> Dict[str, Any]:
    target = f"{url.rstrip('/')}/api/health"
    try:
        with urllib.request.urlopen(target, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
            return {"ok": resp.status == 200 and body.get("ok"), "status": resp.status, "body": body}
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def ensure_stable_server(root: Path, *, port: int = 17890) -> Dict[str, Any]:
    """Ein Hub + Tunnel + gesperrte URL — Server-bootstrap."""
    from analytics.remote_hub_access import (
        ensure_remote_hub_url,
        install_remote_systemd_services,
        load_tunnel_token,
        remote_access_status,
    )
    from analytics.worker_export_sync import ensure_lite_export
    from tools.preview_hub import ensure_hub_running

    root = Path(root)
    log: Dict[str, Any] = {"steps": [], "ok": False}

    killed = kill_duplicate_hubs(root)
    if killed:
        log["steps"].append(f"duplicate_hubs_killed={killed}")

    local = check_hub_health(f"http://127.0.0.1:{port}")
    ensure_hub_running(root, port=port, restart=not local.get("ok"))
    log["steps"].append("hub_running")

    has_token = bool(load_tunnel_token(root))
    remote = ensure_remote_hub_url(root, mode="cloudflared-token" if has_token else "auto")
    log["remote"] = remote
    if not remote.get("ok"):
        log["message_de"] = remote.get("message_de") or "Remote-Hub fehlgeschlagen"
        return log

    try:
        services = install_remote_systemd_services(root)
        log["systemd"] = services
    except Exception as exc:
        log["systemd"] = [str(exc)]

    export_doc = ensure_lite_export(root, force=not remote.get("stable", False))
    log["export"] = export_doc

    status = remote_access_status(root)
    local_ok = check_hub_health(f"http://127.0.0.1:{port}")
    remote_ok = check_hub_health(str(status.get("public_base_url") or ""))
    log["health"] = {"local": local_ok, "remote": remote_ok, "status": status}

    stable = bool(status.get("tunnel_token_set")) or bool(status.get("tailscale_online"))
    log["stable"] = stable
    log["ok"] = bool(local_ok.get("ok")) and bool(remote_ok.get("ok"))
    log["message_de"] = (
        "Server stabil — URL bleibt nach Neustart"
        if stable
        else "Server läuft — für Neustart-Stabilität: bash tools/setup_cloudflare_tunnel_token.sh"
    )

    try:
        from analytics.federation_compute import sync_compute_demand

        log["compute_demand"] = sync_compute_demand(root)
    except Exception as exc:
        log["compute_demand"] = [str(exc)]

    evidence = {
        "ok": log["ok"],
        "stable": stable,
        "updated_at_utc": _utc_now(),
        "public_base_url": status.get("public_base_url"),
        "tunnel_token_set": status.get("tunnel_token_set"),
        "health": log["health"],
        "compute_demand": log.get("compute_demand"),
    }
    path = root / "evidence/stable_server_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, evidence)
    return log


def watchdog_tick(root: Path) -> Dict[str, Any]:
    """Kurzer Stabilitäts- und Compute-Check (Timer/systemd)."""
    from analytics.remote_hub_access import remote_access_status

    root = Path(root)
    status = remote_access_status(root)
    local = check_hub_health("http://127.0.0.1:17890")
    remote_url = str(status.get("public_base_url") or "")
    remote = check_hub_health(remote_url) if remote_url else {"ok": False}
    out = {
        "ok": bool(local.get("ok")) and bool(remote.get("ok")),
        "local": local,
        "remote": remote,
        "tunnel_alive": status.get("tunnel_pid_alive"),
        "updated_at_utc": _utc_now(),
    }
    if not local.get("ok") or not remote.get("ok"):
        return {**out, "action": "run server-bootstrap"}
    try:
        from analytics.federation_compute import sync_compute_demand

        out["compute_demand"] = sync_compute_demand(root)
    except Exception as exc:
        out["compute_demand"] = [str(exc)]
    atomic_write_json(root / "evidence/stable_server_watchdog.json", out)
    return out


def install_boot_integration(root: Path) -> List[str]:
    """systemd user: Server nach Login/ Boot."""
    import os

    root = Path(root)
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(os.environ.get("PYTHON", "python3"))
    unit_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)

    (unit_dir / "active-alpha-stable-server.service").write_text(
        f"""[Unit]
Description=Active Alpha — Stable Server (Hub + Tunnel)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={root}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT={root}
ExecStart={py} {root}/tools/ai_kernel.py server-bootstrap
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "active-alpha-stable-server.service"], check=False)
    return ["active-alpha-stable-server.service"]
