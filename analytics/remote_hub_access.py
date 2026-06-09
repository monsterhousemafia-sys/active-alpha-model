"""Remote Hub-Zugang — Cloudflare Quick/Token-Tunnel + Tailscale."""
from __future__ import annotations

import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from aa_safe_io import atomic_write_json

_TUNNEL_EVIDENCE_REL = Path("evidence/remote_hub_tunnel.json")
_TUNNEL_CFG_REL = Path("control/cloudflare_tunnel.json")
_TUNNEL_TOKEN_REL = Path("control/cloudflare_tunnel.token")
_TUNNEL_PAUSE_REL = Path("evidence/tunnel_paused.json")
_CLOUDFLARED_REL = Path("tools/bin/cloudflared")
_TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
_PRIVATE_NETS = ("127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.", "localhost")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def cloudflared_path(root: Path) -> Optional[Path]:
    root = Path(root)
    cand = root / _CLOUDFLARED_REL
    if cand.is_file() and os.access(cand, os.X_OK):
        return cand
    for name in ("cloudflared",):
        found = subprocess.run(["which", name], capture_output=True, text=True, check=False)
        if found.returncode == 0 and found.stdout.strip():
            p = Path(found.stdout.strip())
            if p.is_file():
                return p
    return None


def is_private_lan_host(host: str) -> bool:
    h = str(host or "").strip().lower()
    if not h:
        return True
    if h in ("127.0.0.1", "localhost", "::1"):
        return True
    return any(h.startswith(p) for p in _PRIVATE_NETS)


def is_remote_reachable_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    if u.startswith("https://"):
        return True
    try:
        host = urlparse(u).hostname or ""
    except Exception:
        return False
    if host.startswith("100.") or host.startswith("100.64."):
        return True
    return not is_private_lan_host(host)


def load_tunnel_token(root: Path) -> Optional[str]:
    root = Path(root)
    token_path = root / _TUNNEL_TOKEN_REL
    if token_path.is_file():
        tok = token_path.read_text(encoding="utf-8").strip()
        if len(tok) >= 20:
            return tok
    env_path = root / "control/server.env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("AA_CLOUDFLARE_TUNNEL_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                if len(tok) >= 20:
                    return tok
    return os.environ.get("AA_CLOUDFLARE_TUNNEL_TOKEN", "").strip() or None


def load_stable_tunnel_url(root: Path) -> str:
    root = Path(root)
    cfg = _load_json(root / _TUNNEL_CFG_REL)
    url = str(cfg.get("public_hostname") or cfg.get("public_url") or "").strip().rstrip("/")
    if url.startswith("https://"):
        return url
    env_path = root / "control/server.env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("AA_CLOUDFLARE_TUNNEL_URL="):
                u = line.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/")
                if u.startswith("https://"):
                    return u
    return ""


def resolve_public_url(root: Path, user_url: str) -> str:
    user_url = str(user_url or "").strip().rstrip("/")
    if user_url.startswith("https://"):
        return user_url
    stable = load_stable_tunnel_url(root)
    if stable.startswith("https://"):
        return stable
    state = load_tunnel_state(root)
    pub = str(state.get("public_url") or "").strip().rstrip("/")
    if pub.startswith("https://"):
        return pub
    try:
        from analytics.preview_federation import federation_config

        cfg = federation_config(root)
        locked = str(cfg.get("public_base_url") or "").strip().rstrip("/")
        if cfg.get("public_base_url_locked") and locked.startswith("https://"):
            return locked
    except Exception:
        pass
    return user_url


def _tunnel_evidence_path(root: Path) -> Path:
    return Path(root) / _TUNNEL_EVIDENCE_REL


def load_tunnel_state(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(_tunnel_evidence_path(root))
    pid = int(doc.get("pid") or 0)
    alive = False
    if pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    url = str(doc.get("public_url") or "").strip()
    ok = alive and url.startswith("https://")
    return {
        "public_url": url or None,
        "pid": pid or None,
        "running": alive,
        "ok": ok,
        "stable": bool(doc.get("stable")),
        "mode": str(doc.get("mode") or ""),
        "updated_at_utc": doc.get("updated_at_utc"),
    }


def _save_tunnel_state(root: Path, state: Dict[str, Any]) -> None:
    atomic_write_json(_tunnel_evidence_path(root), {**state, "updated_at_utc": _utc_now()})


def _http_ok(url: str, *, timeout: float = 8.0) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/health", headers={"User-Agent": "aa-tunnel-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _wait_dns(host: str, *, timeout_s: float = 30.0) -> bool:
    import socket

    host = str(host or "").strip()
    if not host:
        return False
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            return True
        except socket.gaierror:
            time.sleep(2.0)
    return False


def _verify_remote_health(public_url: str, *, local_port: int = 17890) -> bool:
    public_url = str(public_url or "").strip().rstrip("/")
    if not public_url.startswith("https://"):
        return False
    host = urlparse(public_url).hostname or ""
    if host and _wait_dns(host, timeout_s=20.0):
        return _http_ok(public_url)
    return _http_ok(f"http://127.0.0.1:{local_port}")


def _stop_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
    except OSError:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def stop_cloudflared_tunnel(root: Path) -> Dict[str, Any]:
    root = Path(root)
    state = load_tunnel_state(root)
    pid = int(state.get("pid") or 0)
    stopped = 0
    if pid > 0:
        _stop_pid(pid)
        stopped = 1
    _save_tunnel_state(root, {"public_url": None, "pid": None, "running": False, "stable": False, "mode": ""})
    return {"ok": True, "stopped": stopped, "message_de": "Tunnel gestoppt"}


def tailscale_online(root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def build_tailscale_hub_url(root: Path) -> Optional[str]:
    if not tailscale_online(root):
        return None
    try:
        from analytics.preview_federation import federation_config

        port = int(federation_config(root).get("hub_port") or 17890)
        proc = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        ip = (proc.stdout or "").strip().splitlines()[0].strip() if proc.returncode == 0 else ""
        if ip:
            return f"http://{ip}:{port}"
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass
    return None


def _sync_public_urls(root: Path, public_url: str, *, mode: str, stable: bool) -> List[str]:
    root = Path(root)
    changed: List[str] = []
    public_url = str(public_url or "").strip().rstrip("/")
    if not public_url:
        return changed

    fed_path = root / "control/preview_federation.json"
    fed = _load_json(fed_path) or {"schema_version": 1, "enabled": True}
    updates = {
        "public_base_url": public_url,
        "public_base_url_locked": True,
        "remote_access_mode": mode,
        "remote_workers_expected": True,
        "note_de": f"Haus+Welt — Tunnel {public_url}, LAN parallel",
    }
    for k, v in updates.items():
        if fed.get(k) != v:
            fed[k] = v
            changed.append(f"preview_federation:{k}")
    if changed:
        atomic_write_json(fed_path, fed)

    mirror_path = root / "control/r3_https_mirror.json"
    mirror = _load_json(mirror_path)
    mirror_updates = {
        "enabled": public_url.startswith("https://"),
        "public_base_url": public_url if public_url.startswith("https://") else None,
        "local_hub": "http://127.0.0.1:17890",
        "mode": mode,
        "stable": stable,
        "locked": stable,
        "note_de": f"HTTPS-Spiegel: {public_url}" if public_url.startswith("https://") else "Lokal",
        "schema_version": 1,
    }
    if any(mirror.get(k) != v for k, v in mirror_updates.items()):
        atomic_write_json(mirror_path, {**mirror, **mirror_updates})
        changed.append("r3_https_mirror")

    return changed


def start_cloudflared_token_tunnel(root: Path, token: str, *, port: int = 17890) -> Dict[str, Any]:
    root = Path(root)
    cf = cloudflared_path(root)
    if not cf:
        return {"ok": False, "message_de": "cloudflared nicht installiert"}
    stop_cloudflared_tunnel(root)
    proc = subprocess.Popen(
        [str(cf), "tunnel", "--no-autoupdate", "run", "--token", token],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(root),
    )
    stable_url = load_stable_tunnel_url(root)
    deadline = time.time() + 25.0
    while time.time() < deadline:
        if stable_url and _http_ok(stable_url):
            break
        time.sleep(1.0)
    public_url = stable_url or ""
    if not public_url:
        fed = _load_json(root / "control/preview_federation.json")
        cand = str(fed.get("public_base_url") or "").strip().rstrip("/")
        if cand.startswith("https://"):
            public_url = cand
    if not public_url:
        proc.terminate()
        return {"ok": False, "message_de": "Token-Tunnel — stabile URL fehlt (control/server.env)"}
    _save_tunnel_state(
        root,
        {
            "public_url": public_url,
            "pid": proc.pid,
            "running": True,
            "stable": True,
            "mode": "cloudflared-token",
        },
    )
    changed = _sync_public_urls(root, public_url, mode="cloudflared-token", stable=True)
    return {
        "ok": True,
        "mode": "cloudflared-token",
        "public_url": public_url,
        "public_base_url": public_url,
        "pid": proc.pid,
        "stable": True,
        "changed": changed,
    }


def start_cloudflared_quick_tunnel(root: Path, *, port: int = 17890) -> Dict[str, Any]:
    root = Path(root)
    cf = cloudflared_path(root)
    if not cf:
        return {"ok": False, "message_de": "cloudflared nicht installiert"}
    stop_cloudflared_tunnel(root)
    proc = subprocess.Popen(
        [str(cf), "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(root),
    )
    public_url = ""
    deadline = time.time() + 45.0
    while time.time() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line and proc.poll() is not None:
            break
        m = _TUNNEL_URL_RE.search(line or "")
        if m:
            public_url = m.group(0).rstrip("/")
            break
        time.sleep(0.2)
    if not public_url:
        _stop_pid(proc.pid)
        return {"ok": False, "message_de": "Quick-Tunnel URL nicht gefunden — cloudflared Log prüfen"}
    remote_health = _verify_remote_health(public_url, local_port=port)
    if not remote_health:
        _stop_pid(proc.pid)
        return {"ok": False, "message_de": f"Remote-Health FAIL: {public_url}/api/health"}
    _save_tunnel_state(
        root,
        {
            "public_url": public_url,
            "pid": proc.pid,
            "running": True,
            "stable": False,
            "mode": "cloudflared",
            "remote_health_verified": _http_ok(public_url),
        },
    )
    changed = _sync_public_urls(root, public_url, mode="cloudflared", stable=False)
    return {
        "ok": True,
        "mode": "cloudflared",
        "public_url": public_url,
        "public_base_url": public_url,
        "pid": proc.pid,
        "stable": False,
        "changed": changed,
    }


def ensure_remote_hub_url(root: Path, *, mode: str = "auto") -> Dict[str, Any]:
    root = Path(root)
    if is_tunnel_paused(root):
        return {"ok": False, "public_base_url": None, "message_de": "Tunnel pausiert — king_ops tunnel-stable resume"}

    from analytics.preview_federation import federation_config

    cfg = federation_config(root)
    port = int(cfg.get("hub_port") or 17890)
    mode = str(mode or "auto").strip().lower()
    token = load_tunnel_token(root)

    if mode in ("cloudflared-token", "token") and token:
        out = start_cloudflared_token_tunnel(root, token, port=port)
        if out.get("ok"):
            return out
        mode = "auto"

    if mode in ("auto", "tailscale"):
        ts_url = build_tailscale_hub_url(root)
        if ts_url:
            changed = _sync_public_urls(root, ts_url, mode="tailscale", stable=True)
            _save_tunnel_state(
                root,
                {"public_url": ts_url, "pid": None, "running": True, "stable": True, "mode": "tailscale"},
            )
            return {
                "ok": True,
                "mode": "tailscale",
                "public_base_url": ts_url,
                "stable": True,
                "changed": changed,
            }
        if mode == "tailscale":
            return {"ok": False, "message_de": "Tailscale offline"}

    state = load_tunnel_state(root)
    if state.get("ok") and state.get("public_url"):
        url = str(state["public_url"])
        if _http_ok(url):
            return {
                "ok": True,
                "mode": state.get("mode") or "cloudflared",
                "public_base_url": url,
                "stable": bool(state.get("stable")),
                "changed": [],
            }

    if token:
        out = start_cloudflared_token_tunnel(root, token, port=port)
        if out.get("ok"):
            return out

    out = start_cloudflared_quick_tunnel(root, port=port)
    if out.get("ok") and out.get("public_url") and not out.get("public_base_url"):
        out["public_base_url"] = out["public_url"]
    return out


def is_tunnel_paused(root: Path) -> bool:
    doc = _load_json(Path(root) / _TUNNEL_PAUSE_REL)
    return bool(doc.get("paused"))


def remote_access_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.preview_federation import federation_config

    fed = federation_config(root)
    state = load_tunnel_state(root)
    token = load_tunnel_token(root)
    public = str(fed.get("public_base_url") or state.get("public_url") or "").strip().rstrip("/")
    pid_alive = bool(state.get("running"))
    https = public.startswith("https://")
    health = _http_ok(public) if https else False
    local_health = _http_ok(f"http://127.0.0.1:{int(fed.get('hub_port') or 17890)}")
    remote_ready = https and pid_alive and (health or local_health)
    return {
        "ok": True,
        "remote_ready": remote_ready,
        "remote_workers_expected": bool(fed.get("remote_workers_expected")),
        "public_base_url": public or None,
        "tunnel_pid_alive": pid_alive,
        "tunnel_stable": bool(state.get("stable")) or bool(token),
        "tunnel_token_set": bool(token),
        "tailscale_online": tailscale_online(root),
        "local_hub": "http://127.0.0.1:17890",
        "mode": state.get("mode") or fed.get("remote_access_mode"),
        "message_de": (
            f"Remote OK — {public}"
            if remote_ready
            else (
                "Tunnel läuft — Health prüfen"
                if pid_alive and https
                else "Tunnel/Hub nicht bereit — ai_kernel spread-remote"
            )
        ),
    }


def install_remote_systemd_services(root: Path) -> List[str]:
    root = Path(root)
    script = root / "tools/setup_aa_runtime.sh"
    if not script.is_file():
        return ["setup_aa_runtime.sh fehlt"]
    try:
        proc = subprocess.run(
            ["bash", str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return [f"setup_aa_runtime rc={proc.returncode}"]
    except subprocess.TimeoutExpired:
        return ["setup_aa_runtime timeout"]
