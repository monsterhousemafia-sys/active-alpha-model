"""Lokale Kontrolle — Ubuntu-Runtime unter king_ops (Hub, Tunnel, Worker, Spread)."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/local_control_latest.json")
_POLICY_REL = Path("control/local_control_policy.json")

_CORE_SERVICES = (
    "active-alpha-preview-hub.service",
    "active-alpha-remote-tunnel.service",
    "active-alpha-preview-worker.service",
    "active-alpha-runtime-api.service",
)
_CORE_TIMERS = (
    "active-alpha-tunnel-stable.timer",
    "active-alpha-spread-tick.timer",
    "active-alpha-evidence-watch.timer",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _unit_state(name: str) -> Dict[str, Any]:
    proc = _systemctl("is-active", name)
    active = proc.stdout.strip()
    return {
        "unit": name,
        "active": active,
        "ok": active in ("active", "waiting", "elapsed"),
    }


def _ensure_units(root: Path) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    _systemctl("daemon-reload")
    for unit in _CORE_SERVICES:
        st = _unit_state(unit)
        if not st["ok"]:
            _systemctl("restart", unit)
            st = _unit_state(unit)
            actions.append({"action": "restart", **st})
        else:
            actions.append({"action": "ok", **st})
    for timer in _CORE_TIMERS:
        _systemctl("enable", timer)
        _systemctl("start", timer)
        actions.append({"action": "enable", **_unit_state(timer)})
    return actions


def assume_local_control(root: Path, *, repair: bool = True) -> Dict[str, Any]:
    """Operative Kontrolle lokal übernehmen — Dienste, Tunnel, Worker, Spread."""
    root = Path(root)
    unit_actions: List[Dict[str, Any]] = []
    if repair:
        unit_actions = _ensure_units(root)

    from analytics.remote_hub_access import ensure_remote_hub_url, load_tunnel_token, remote_access_status
    from analytics.spread_secure_ops import verify_spread_security
    from analytics.tunnel_control import tunnel_control_status, tunnel_control_try_apply
    from analytics.worker_export_sync import build_worker_stability_status, ensure_lite_export

    if not load_tunnel_token(root):
        tunnel_control_try_apply(root, silent=True)

    tunnel = ensure_remote_hub_url(
        root,
        mode="cloudflared-token" if load_tunnel_token(root) else "auto",
    )
    worker = build_worker_stability_status(root)
    try:
        ensure_lite_export(root, force=False)
    except Exception:
        pass
    spread = verify_spread_security(root)
    tunnel_status = tunnel_control_status(root)
    remote = remote_access_status(root)

    linger = ""
    try:
        proc = subprocess.run(
            ["loginctl", "show-user", Path.home().name, "-p", "Linger"],
            capture_output=True,
            text=True,
            check=False,
        )
        linger = (proc.stdout or "").strip().split("=", 1)[-1]
    except OSError:
        pass

    ok = bool(
        spread.get("ok")
        and remote.get("tunnel_pid_alive")
        and remote.get("remote_ready")
        and worker.get("ok")
    )
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok,
        "controller": "cursor_local",
        "layer_de": "Schicht 4 — lokale Runtime-Kontrolle (Hub/Tunnel/Worker)",
        "linger": linger,
        "headline_de": (
            "Lokale Kontrolle aktiv — Hub, Tunnel, Worker unter king_ops"
            if ok
            else "Lokale Kontrolle — Teile prüfen (siehe checks)"
        ),
        "join_url": worker.get("join_url"),
        "tunnel_stable": tunnel_status.get("tunnel_stable"),
        "workers_online": worker.get("workers_online"),
        "spread_verify": {
            "ok": spread.get("ok"),
            "passed": spread.get("checks_passed"),
            "total": spread.get("checks_total"),
        },
        "unit_actions": unit_actions,
        "commands_de": [
            "bash tools/king_ops.sh local-control status",
            "bash tools/king_ops.sh local-control repair",
            "bash tools/king_ops.sh worker-stability",
            "bash tools/king_ops.sh spread verify",
        ],
        "next_de": (
            None
            if tunnel_status.get("tunnel_stable")
            else "bash tools/king_ops.sh tunnel-stable setup"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    atomic_write_json(
        root / _POLICY_REL,
        {
            "schema_version": 1,
            "status": "ACTIVE",
            "controller": "king_ops",
            "updated_at_utc": doc["updated_at_utc"],
            "scope_de": "Hub :17890, Tunnel, lokaler Worker, Spread-Tick, Tunnel-Stable-Timer",
            "entrypoint_de": "bash tools/king_ops.sh local-control",
            "safety_de": "Kein Echtgeld, kein Champion-Wechsel, Operator-Souveränität unverändert",
        },
    )
    doc["tunnel"] = {"ok": tunnel.get("ok"), "url": tunnel.get("public_base_url")}
    return doc
