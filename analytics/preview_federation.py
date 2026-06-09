"""Federated Preview — Worker melden Leistung an den zentralen Preview-Hub."""
from __future__ import annotations

import fcntl
import json
import os
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/preview_federation.json")
_STATE_REL = Path("evidence/preview_federation.json")


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


_WORKER_JOIN_REL = Path("control/preview_worker_join.json")


def federation_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = _load_json(root / _CONFIG_REL)
    if not cfg:
        cfg = {"enabled": True, "stale_after_s": 900, "hub_port": 17890, "lan_bind": True}
    cfg.setdefault("stale_after_s", 900)
    return cfg


def ensure_join_token(root: Path) -> str:
    """LAN-Join-Token für Worker (ein Token, viele Teilnehmer — König kann rotieren)."""
    root = Path(root)
    path = root / _CONFIG_REL
    cfg = federation_config(root)
    token = str(cfg.get("join_token") or "").strip()
    if token:
        return token
    token = uuid.uuid4().hex
    cfg["join_token"] = token
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, cfg)
    return token


def worker_join_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _WORKER_JOIN_REL)
    if doc:
        return doc
    cfg = federation_config(root)
    if str(cfg.get("role") or "").lower() == "worker" and cfg.get("hub_join_url"):
        return cfg
    return {}


def is_worker_bundle(root: Path) -> bool:
    doc = worker_join_config(root)
    return bool(doc.get("auto_start") and doc.get("hub_join_url"))


def is_federation_king(root: Path) -> bool:
    return not is_worker_bundle(root)


def resolve_worker_hub_url(root: Path) -> Optional[str]:
    doc = worker_join_config(root)
    url = str(doc.get("hub_join_url") or os.environ.get("AA_PREVIEW_HUB_URL") or "").strip().rstrip("/")
    return url or None


def prepare_worker_bundle_config(root: Path, *, request_host: Optional[str] = None) -> Dict[str, Any]:
    root = Path(root)
    base = hub_public_base_url(root, request_host=request_host)
    token = ensure_join_token(root)
    return {
        "schema_version": 1,
        "role": "worker",
        "hub_join_url": base,
        "join_token": token,
        "auto_start": True,
        "auto_start_de": "./ACTIVE_ALPHA_WORKER_START.sh",
        "king_hostname": socket.gethostname(),
        "worker_interval_s": 120,
        "worker_preview_on_heartbeat": False,
        "exported_at_utc": _utc_now(),
        "note_de": "Worker-Bundle — cd <ordner> && ./ACTIVE_ALPHA_WORKER_START.sh",
    }


def load_federation_state(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _STATE_REL)
    if not doc:
        doc = {"schema_version": 1, "workers": {}, "updated_at_utc": _utc_now()}
    doc.setdefault("workers", {})
    return doc


@contextmanager
def _federation_state_lock(root: Path):
    root = Path(root)
    lock_path = root / "evidence/preview_federation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def save_federation_state(root: Path, doc: Dict[str, Any]) -> Path:
    root = Path(root)
    path = root / _STATE_REL
    doc = dict(doc)
    doc["schema_version"] = 1
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(path, doc)
    return path


def _mutate_federation_state(root: Path, mutate: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    root = Path(root)
    with _federation_state_lock(root):
        state = load_federation_state(root)
        state = mutate(state)
        save_federation_state(root, state)
        return state


def stable_worker_id(*, hostname: Optional[str] = None, suffix: Optional[str] = None) -> str:
    host = str(hostname or socket.gethostname() or "host").strip().lower()
    host = "".join(c if c.isalnum() or c in "-_" else "-" for c in host)
    if suffix:
        return f"{host}-{suffix}"
    from analytics.r3_paths import r3_share_dir

    path = r3_share_dir() / "worker_id"
    if path.is_file():
        wid = path.read_text(encoding="utf-8").strip()
        if wid:
            return wid
    wid = f"{host}-{uuid.uuid4().hex[:8]}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(wid + "\n", encoding="utf-8")
    return wid


def detect_lan_ip() -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        for line in os.popen("hostname -I 2>/dev/null").read().split():
            if line and not line.startswith("127."):
                return line
    except OSError:
        pass
    return None


def hub_bind_host(root: Path) -> str:
    cfg = federation_config(root)
    if cfg.get("enabled", True) and cfg.get("lan_bind"):
        return str(cfg.get("bind_host") or "0.0.0.0")
    try:
        from analytics.alpha_model_local_runtime import is_local_only, load_local_runtime

        if is_local_only(root):
            return str(load_local_runtime(root).get("hub_bind") or "127.0.0.1")
    except Exception:
        pass
    if cfg.get("enabled", True) and cfg.get("lan_bind", True):
        return str(cfg.get("bind_host") or "0.0.0.0")
    return str(cfg.get("bind_host") or "127.0.0.1")


def hub_public_base_url(root: Path, *, port: Optional[int] = None, request_host: Optional[str] = None) -> str:
    cfg = federation_config(root)
    port = int(port or cfg.get("hub_port") or 17890)
    explicit = str(cfg.get("public_base_url") or "").strip().rstrip("/")
    try:
        from analytics.alpha_model_local_runtime import is_local_only

        if (
            explicit.startswith("https://")
            and cfg.get("public_base_url_locked")
            and cfg.get("remote_workers_expected")
            and not is_local_only(root)
        ):
            return explicit
    except Exception:
        pass
    if cfg.get("lan_bind") and str(cfg.get("remote_access_mode") or "") == "lan":
        if explicit.startswith("http://") and not explicit.startswith("http://127."):
            return explicit
        lan = detect_lan_ip()
        if lan:
            return f"http://{lan}:{port}"
    try:
        from analytics.r3_local_first import is_r3_local_first, local_hub_authoritative_url

        if is_r3_local_first(root):
            return local_hub_authoritative_url(root, port=port)
    except Exception:
        pass
    try:
        from analytics.r3_local_surface import is_king_cockpit_local

        if is_king_cockpit_local(root):
            return f"http://127.0.0.1:{port}"
    except Exception:
        pass
    try:
        from analytics.alpha_model_local_runtime import is_local_only, load_local_runtime

        world_mode = bool(cfg.get("remote_workers_expected")) or not is_local_only(root)
        if explicit.startswith("https://") and (
            world_mode or cfg.get("public_base_url_locked")
        ):
            return explicit
        if is_local_only(root):
            local = str(load_local_runtime(root).get("hub_url") or "").strip().rstrip("/")
            if local:
                return local
            return f"http://127.0.0.1:{port}"
    except Exception:
        if explicit.startswith("https://"):
            return explicit
    if explicit and not explicit.startswith("https://"):
        return explicit
    if explicit and cfg.get("remote_access_mode") == "local_only":
        return f"http://127.0.0.1:{port}"
    if explicit:
        return explicit
    if request_host and request_host.split(":")[0] not in ("127.0.0.1", "localhost"):
        return f"http://{request_host.split(':')[0]}:{port}"
    lan = detect_lan_ip()
    if lan:
        return f"http://{lan}:{port}"
    return f"http://127.0.0.1:{port}"


def collect_local_contribution(root: Path, *, preview_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root)
    from analytics.preview_hardware_status import build_preview_hardware_status

    hw = build_preview_hardware_status(root)
    cpus = int(hw.get("cpus") or os.cpu_count() or 1)
    load = hw.get("load_per_cpu")
    h1 = hw.get("h1") or {}
    report = dict(preview_report or _load_json(root / "evidence/gui_preview_latest.json"))
    join_doc = worker_join_config(root)
    payload: Dict[str, Any] = {
        "worker_id": stable_worker_id(),
        "hostname": socket.gethostname(),
        "role": "compute" if is_worker_bundle(root) else "king",
        "cpus": cpus,
        "mem_free_gb": hw.get("mem_free_gb"),
        "load_per_cpu": load,
        "hardware_score": hw.get("score"),
        "h1_running": bool(h1.get("running")),
        "preview_passed": int(report.get("passed") or 0),
        "preview_total": int(report.get("total") or 0),
        "preview_ok": bool(report.get("overall_pass")),
        "headline_de": str(hw.get("headline_de") or "")[:200],
        "nvme_mounted": bool((hw.get("nvme") or {}).get("mount")),
        "updated_at_utc": _utc_now(),
    }
    token = str(join_doc.get("join_token") or "").strip()
    if token:
        payload["join_token"] = token
    return payload


def _validate_worker_contribution(root: Path, contribution: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[str]:
    role = str(contribution.get("role") or "compute").lower()
    king_id = str(cfg.get("king_worker_id") or "king")
    wid = str(contribution.get("worker_id") or "").strip()
    if not wid:
        return "worker_id fehlt"
    if role == "king":
        if wid != king_id:
            return "king worker_id ungültig"
        return None
    if wid == king_id:
        return "compute darf nicht king-ID nutzen"
    expected = str(cfg.get("join_token") or "").strip()
    if expected:
        got = str(contribution.get("join_token") or "").strip()
        if got != expected:
            return "join_token ungültig — Bundle vom König neu exportieren"
    cpus = int(contribution.get("cpus") or 0)
    if cpus < 1:
        return "cpus fehlt"
    return None


def upsert_worker(root: Path, contribution: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    cfg = federation_config(root)
    if not cfg.get("enabled", True):
        return {"ok": False, "message_de": "Federation deaktiviert"}

    err = _validate_worker_contribution(root, contribution, cfg)
    if err:
        return {"ok": False, "message_de": err}

    wid = str(contribution.get("worker_id") or "").strip()

    def _merge(state: Dict[str, Any]) -> Dict[str, Any]:
        workers: Dict[str, Any] = dict(state.get("workers") or {})
        prior = dict(workers.get(wid) or {})
        merged = {**prior, **contribution, "worker_id": wid, "last_seen_utc": _utc_now()}
        if not prior.get("first_seen_utc"):
            merged["first_seen_utc"] = merged["last_seen_utc"]
        workers[wid] = merged
        state["workers"] = workers
        return state

    prior_state = load_federation_state(root)
    prior_worker = dict((prior_state.get("workers") or {}).get(wid) or {})
    is_new = not prior_worker.get("first_seen_utc")

    state = _mutate_federation_state(root, _merge)
    workers = state.get("workers") or {}
    out: Dict[str, Any] = {"ok": True, "worker_id": wid, "workers_online": len(workers)}
    try:
        from analytics.federation_worker_rewards import (
            entlohnung_for_worker,
            grant_heartbeat_stipend,
            grant_join_stipend,
        )

        if is_new:
            out["join_stipend"] = grant_join_stipend(root, worker_id=wid, is_new=True)
        out["heartbeat_stipend"] = grant_heartbeat_stipend(root, worker_id=wid)
    except Exception:
        pass
    try:
        from analytics.federation_legion import legion_welcome_for_worker

        legion = legion_welcome_for_worker(root, wid)
        legion["entlohnung_de"] = entlohnung_for_worker(root, wid)
        out["legion"] = legion
    except Exception:
        pass
    return out


def prune_stale_workers(root: Path) -> int:
    root = Path(root)
    cfg = federation_config(root)
    stale_s = int(cfg.get("stale_after_s") or 900)
    now = datetime.now(timezone.utc)
    removed_box = {"n": 0}

    def _prune(state: Dict[str, Any]) -> Dict[str, Any]:
        workers: Dict[str, Any] = dict(state.get("workers") or {})
        for wid, doc in list(workers.items()):
            raw = str(doc.get("last_seen_utc") or doc.get("updated_at_utc") or "")
            try:
                ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age = (now - ts).total_seconds()
            except (TypeError, ValueError):
                age = stale_s + 1
            if age > stale_s:
                workers.pop(wid, None)
                removed_box["n"] += 1
        state["workers"] = workers
        return state

    _mutate_federation_state(root, _prune)
    return int(removed_box["n"])


def count_federation_participants(workers: List[Dict[str, Any]]) -> Dict[str, int]:
    king = sum(1 for w in workers if str(w.get("role") or "").lower() == "king")
    compute = sum(1 for w in workers if str(w.get("role") or "").lower() == "compute")
    hosts = {str(w.get("hostname") or "") for w in workers if w.get("hostname")}
    hosts.discard("")
    return {"king": king, "compute": compute, "hosts": len(hosts), "total": len(workers)}


def build_federation_summary(root: Path, *, request_host: Optional[str] = None) -> Dict[str, Any]:
    root = Path(root)
    cfg = federation_config(root)
    if is_federation_king(root):
        try:
            sync_king_contribution(root)
        except Exception:
            pass
    prune_stale_workers(root)
    state = load_federation_state(root)
    workers: List[Dict[str, Any]] = list((state.get("workers") or {}).values())
    workers.sort(key=lambda w: (0 if w.get("role") == "king" else 1, str(w.get("hostname") or "")))

    total_cpus = sum(int(w.get("cpus") or 0) for w in workers)
    preview_ok = sum(1 for w in workers if w.get("preview_ok"))
    h1_nodes = sum(1 for w in workers if w.get("h1_running"))
    from analytics.r3_local_surface import is_king_cockpit_local, local_hub_base_url

    port = int(cfg.get("hub_port") or 17890)
    if is_king_cockpit_local(root) and (
        not request_host or request_host.split(":")[0] in ("127.0.0.1", "localhost")
    ):
        base = local_hub_base_url(port=port)
    else:
        base = hub_public_base_url(root, request_host=request_host)
    try:
        from analytics.federation_compute import build_utilization_summary

        util = build_utilization_summary(root)
    except Exception:
        util = {}
    try:
        from analytics.federation_legion import build_legion_summary

        legion = build_legion_summary(root)
    except Exception:
        legion = {}

    return {
        "schema_version": 1,
        "enabled": bool(cfg.get("enabled", True)),
        "workers_online": len(workers),
        "total_cpus": total_cpus,
        "preview_ok_nodes": preview_ok,
        "h1_nodes": h1_nodes,
        "compute": util,
        "legion": legion,
        "headline_de": (
            legion.get("headline_de")
            if legion.get("headline_de") and legion.get("legionnaires")
            else util.get("headline_de")
            if util.get("headline_de")
            else (
                f"{len(workers)} Knoten · {total_cpus} CPU-Kerne zentral"
                if workers
                else "Nur König — Link teilen für mehr Rechenleistung"
            )
        ),
        "share_url": f"{base}/",
        "join_url": f"{base}/join",
        "workers": workers,
        "updated_at_utc": _utc_now(),
    }


def merge_federation_into_report(root: Path, report: Dict[str, Any], *, request_host: Optional[str] = None) -> Dict[str, Any]:
    report = dict(report)
    summary = build_federation_summary(root, request_host=request_host)
    report["federation"] = summary
    return report


def sync_king_contribution(root: Path, *, preview_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if is_worker_bundle(root):
        return {"ok": False, "skipped": True, "message_de": "Worker-Bundle — kein König"}
    os.environ.setdefault("AA_PREVIEW_KING", "1")
    cfg = federation_config(root)
    king_id = str(cfg.get("king_worker_id") or "king")
    doc = collect_local_contribution(root, preview_report=preview_report)
    doc["worker_id"] = king_id
    doc["role"] = "king"
    doc["hostname"] = socket.gethostname()
    return upsert_worker(root, doc)


def build_share_package(root: Path, *, port: int = 17890, request_host: Optional[str] = None) -> Dict[str, Any]:
    root = Path(root)
    base = hub_public_base_url(root, port=port, request_host=request_host)
    summary = build_federation_summary(root, request_host=request_host)
    bundle_cmd = "cd <empfangener-worker-ordner> && ./ACTIVE_ALPHA_WORKER_START.sh"
    dev_cmd = (
        f"cd ~/active_alpha_model && export AA_LINUX_NATIVE_APP=1 && "
        f".venv/bin/python3 tools/preview_federation_worker.py --join {base} --no-preview"
    )
    return {
        "ok": True,
        "share_url": f"{base}/",
        "join_url": f"{base}/join",
        "join_command_de": bundle_cmd,
        "join_command_lite_de": "ZIP entpacken → Windows_START.bat / Mac_START.command / Linux_START.sh",
        "join_command_dev_de": dev_cmd,
        "export_command_de": "ai_kernel spread-remote",
        "export_command_lite_de": "ai_kernel preview-export-lite",
        "export_command_full_de": "ai_kernel preview-export",
        "health_check_de": f"curl -fsS {base}/api/health",
        "federation": summary,
    }


def render_join_html(root: Path, *, hub_base: str) -> str:
    pkg = build_share_package(root, request_host=hub_base.replace("http://", "").split("/")[0])
    bundle = pkg.get("join_command_de") or ""
    dev = pkg.get("join_command_dev_de") or ""
    health = pkg.get("health_check_de") or ""
    export_cmd = pkg.get("export_command_de") or "ai_kernel preview-export"
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>R3 — Mitmachen</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;color:#1d1d1f}}
code,pre{{background:#f5f5f7;padding:12px;border-radius:12px;display:block;overflow:auto;font-size:13px}}
h1{{font-size:28px}} p{{line-height:1.5;color:#6e6e73}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border:1px solid #e5e5ea;padding:10px;text-align:left}}
.btn{{display:inline-block;margin-top:16px;padding:12px 18px;background:#0071e3;color:#fff;text-decoration:none;border-radius:12px;font-weight:600}}
</style></head><body>
<h1>Rechenleistung beitreten</h1>
<p>CPU spenden fürs Research-Cockpit — <strong>kein Broker, kein Geld</strong>. Win · Mac · Linux.</p>
<p>Du wirst <strong>Legionär</strong> mit sichtbarem Rang (Tiro → Centurio) — <a href="{hub_base}/legion">Rangliste</a>.</p>
<p><strong>Entlohnung:</strong> Willkommens-Gutschrift beim Join · CPU-Sekunden pro Job · sichtbarer Rang — fair, ohne Echtgeld.</p>
<h2>1. Kinderleicht (empfohlen)</h2>
<p>König exportiert: <code>ai_kernel spread-remote</code> → ZIP verschicken → Doppelklick:</p>
<table>
<tr><th>System</th><th>Datei</th></tr>
<tr><td>Windows</td><td><code>Windows_START.bat</code></td></tr>
<tr><td>macOS</td><td><code>Mac_START.command</code></td></tr>
<tr><td>Linux</td><td><code>Linux_START.sh</code></td></tr>
</table>
<p>Nur <strong>Python 3</strong> nötig — sonst nichts installieren.</p>
<h2>2. Linux Voll-Bundle</h2>
<pre>{bundle}</pre>
<h2>3. Erreichbarkeit</h2>
<pre>{health}</pre>
<p><a class="btn" href="{pkg.get('share_url','/')}">Zum R3 Cockpit</a>
<a class="btn" href="{hub_base}/legion" style="background:#8b4513;margin-left:8px">Legion-Rangliste</a></p>
</body></html>"""


_EVIDENCE_LAN_SPREAD_REL = Path("evidence/lan_spread_latest.json")
_SHARE_TEXT_REL = Path("evidence/lan_spread_share_de.txt")


def _try_ufw_allow(port: int) -> Dict[str, Any]:
    import subprocess

    try:
        st = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=8)
        if st.returncode != 0 or "inactive" in (st.stdout or "").lower():
            return {"ok": True, "skipped": True, "detail_de": "ufw inaktiv oder nicht installiert"}
        allow = subprocess.run(
            ["sudo", "-n", "ufw", "allow", f"{port}/tcp"],
            capture_output=True,
            text=True,
            timeout=12,
        )
        if allow.returncode == 0:
            return {"ok": True, "detail_de": f"ufw allow {port}/tcp"}
        return {
            "ok": False,
            "detail_de": "ufw aktiv — manuell: sudo ufw allow {0}/tcp".format(port),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "detail_de": str(exc)[:120]}


def apply_lan_spread(
    root: Path,
    *,
    export_lite: bool = True,
    restart_hub: bool = True,
    home_zip_copy: bool = True,
) -> Dict[str, Any]:
    """Festnetz/LAN über Router (Telefonkabel/DSL) — Worker im gleichen Hausnetz."""
    import shutil
    import subprocess

    root = Path(root)
    lan = detect_lan_ip()
    if not lan:
        doc = {
            "ok": False,
            "headline_de": "Keine LAN-IP — Router/WLAN-Kabel prüfen",
            "updated_at_utc": _utc_now(),
        }
        atomic_write_json(root / _EVIDENCE_LAN_SPREAD_REL, doc)
        return doc

    cfg = dict(federation_config(root))
    port = int(cfg.get("hub_port") or 17890)
    lan_url = f"http://{lan}:{port}"
    fed_path = root / _CONFIG_REL
    changed: List[str] = []
    updates = {
        "lan_bind": True,
        "bind_host": "0.0.0.0",
        "public_base_url": lan_url,
        "public_base_url_locked": True,
        "remote_access_mode": "lan",
        "remote_workers_expected": True,
        "note_de": f"LAN-Verbreitung — Festnetz/Router ({lan}), kein Tunnel nötig im Haus",
    }
    for key, value in updates.items():
        if cfg.get(key) != value:
            cfg[key] = value
            changed.append(key)
    atomic_write_json(fed_path, cfg)

    rt_path = root / Path("control/alpha_model_local_runtime.json")
    rt = _load_json(rt_path)
    if rt and rt.get("hub_bind") != "0.0.0.0":
        rt["hub_bind"] = "0.0.0.0"
        atomic_write_json(rt_path, rt)
        changed.append("local_runtime:hub_bind")

    ensure_join_token(root)

    if restart_hub:
        from tools.preview_hub import ensure_hub_running

        ensure_hub_running(root, restart=True)

    export_doc: Dict[str, Any] = {}
    lite_zip = ""
    if export_lite:
        py = shutil.which("python3") or "python3"
        dest = str(Path.home() / "active_alpha_worker_LITE")
        env = os.environ.copy()
        env["AA_PROJECT_ROOT"] = str(root)
        env["AA_WORKER_LITE_EXPORT_DEST"] = dest
        proc = subprocess.run(
            [py, str(root / "tools/ai_kernel.py"), "preview-export-lite"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        export_doc = {"export_rc": proc.returncode, "stderr_tail": (proc.stderr or "")[-400:]}
        marker = _load_json(root / Path("evidence/community_spread_export.json"))
        lite_zip = str(marker.get("lite_zip") or f"{dest}.zip")
        if home_zip_copy and lite_zip and Path(lite_zip).is_file():
            home_copy = Path.home() / "glasfaser_NOTFALL_worker_LITE.zip"
            shutil.copy2(lite_zip, home_copy)
            export_doc["home_zip"] = str(home_copy)
        backup_dir = root / Path("evidence/glasfaser_offline")
        backup_dir.mkdir(parents=True, exist_ok=True)
        if lite_zip and Path(lite_zip).is_file():
            shutil.copy2(lite_zip, backup_dir / "worker_LITE_backup.zip")
            export_doc["backup_zip"] = str(backup_dir / "worker_LITE_backup.zip")

    firewall = _try_ufw_allow(port)
    pkg = build_share_package(root)
    share_lines = [
        "Active Alpha — LAN (Festnetz/Router)",
        "",
        f"ZIP: {lite_zip or '(nach Export)'}",
        f"Join: {pkg.get('join_url')}",
        f"Health: curl -fsS {lan_url}/api/health",
        "",
        "1. ZIP auf USB oder per LAN kopieren",
        "2. Entpacken → Windows_START.bat / Linux_START.sh",
        "3. Gleiches WLAN/LAN wie König-PC",
    ]
    share_path = root / _SHARE_TEXT_REL
    share_path.parent.mkdir(parents=True, exist_ok=True)
    share_path.write_text("\n".join(share_lines) + "\n", encoding="utf-8")

    doc = {
        "schema_version": 1,
        "ok": True,
        "headline_de": f"LAN aktiv — {lan_url} (Festnetz/Telefonkabel-Router)",
        "lan_ip": lan,
        "lan_url": lan_url,
        "join_url": pkg.get("join_url"),
        "bind_host": hub_bind_host(root),
        "lite_zip": lite_zip,
        "share_text_ref": _SHARE_TEXT_REL.as_posix(),
        "changed": changed,
        "export": export_doc,
        "firewall": firewall,
        "operator_de": [
            f"Worker testen: curl -fsS {lan_url}/api/health",
            f"ZIP teilen: {lite_zip}",
            "Zurück auf nur-local: ai_kernel r3-local",
        ],
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_LAN_SPREAD_REL, doc)
    try:
        from analytics.community_spread_plan import broadcast_spread

        doc["broadcast"] = broadcast_spread(root)
    except Exception as exc:
        doc["broadcast"] = {"ok": False, "detail_de": str(exc)[:120]}
    return doc


def verify_lan_spread(root: Path) -> Dict[str, Any]:
    import urllib.error
    import urllib.request

    root = Path(root)
    cfg = federation_config(root)
    bind = hub_bind_host(root)
    lan_url = hub_public_base_url(root)
    checks: List[Dict[str, Any]] = []

    def add(cid: str, label: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "label_de": label, "ok": ok, "detail_de": detail})

    add("lan_bind", "LAN-Bind aktiv", bool(cfg.get("lan_bind")), str(cfg.get("bind_host") or ""))
    add("bind_open", "Hub bindet 0.0.0.0", bind == "0.0.0.0", bind)
    add("lan_url", "LAN-URL gesetzt", lan_url.startswith("http://") and "127.0.0.1" not in lan_url, lan_url)
    health_ok = False
    try:
        with urllib.request.urlopen(f"{lan_url.rstrip('/')}/api/health", timeout=4) as resp:
            health_ok = int(getattr(resp, "status", 0) or 0) == 200
    except (urllib.error.URLError, OSError, ValueError):
        health_ok = False
    add("health", "Hub Health LAN", health_ok, f"{lan_url}/api/health")
    marker = _load_json(root / Path("evidence/community_spread_export.json"))
    zip_path = str(marker.get("lite_zip") or "")
    add("lite_zip", "Lite-ZIP vorhanden", bool(zip_path) and Path(zip_path).is_file(), zip_path)
    passed = sum(1 for c in checks if c.get("ok"))
    return {
        "ok": passed == len(checks),
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "lan_url": lan_url,
        "updated_at_utc": _utc_now(),
    }
