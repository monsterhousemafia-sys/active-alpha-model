"""Active-Alpha Linux Runtime — Slices, Limits, API, Evidence-Watch."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/aa_linux_runtime_latest.json")

_SLICES = {
    "aa-runtime.slice": """[Unit]
Description=Active Alpha Runtime
Documentation=file://{root}/docs/LINUX_COMMUNITY_DE.md
""",
    "aa-h1.slice": """[Unit]
Description=Active Alpha H1 Backtest
Documentation=file://{root}/docs/LINUX_COMMUNITY_DE.md
""",
    "aa-hub.slice": """[Unit]
Description=Active Alpha Preview Hub
Documentation=file://{root}/docs/LINUX_COMMUNITY_DE.md
""",
    "aa-tunnel.slice": """[Unit]
Description=Active Alpha Remote Tunnel
Documentation=file://{root}/docs/LINUX_COMMUNITY_DE.md
""",
    "aa-agent.slice": """[Unit]
Description=Active Alpha Agent Services (API, Watch)
Documentation=file://{root}/docs/LINUX_COMMUNITY_DE.md
""",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _unit_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"


def _py(root: Path) -> str:
    v = root / ".venv/bin/python3"
    return str(v) if v.is_file() else "python3"


def _common_service_env(root: Path) -> str:
    return f"""WorkingDirectory={root}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT={root}
Environment=PYTHONUNBUFFERED=1
"""


def _hub_service(root: Path) -> str:
    py = _py(root)
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha Preview Hub
After=network-online.target
PartOf=aa-runtime.slice

[Service]
Type=simple
Slice=aa-hub.slice
{env}
MemoryMax=1G
TasksMax=256
LimitNOFILE=8192
ExecStartPre={py} {root}/tools/preview_hub.py --stop
ExecStart={py} {root}/tools/preview_hub.py --daemon --port 17890
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=120
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-hub

[Install]
WantedBy=default.target
"""


def _tunnel_service(root: Path, tunnel_exec: str) -> str:
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha Remote Tunnel
After=network-online.target active-alpha-preview-hub.service
Wants=active-alpha-preview-hub.service
PartOf=aa-runtime.slice

[Service]
Type=simple
Slice=aa-tunnel.slice
{env}
EnvironmentFile=-{root}/control/server.env
MemoryMax=512M
TasksMax=64
LimitNOFILE=4096
ExecStart={tunnel_exec}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-tunnel

[Install]
WantedBy=default.target
"""


def _runtime_api_service(root: Path) -> str:
    py = _py(root)
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha Runtime API (Unix socket)
After=network-online.target
PartOf=aa-runtime.slice

[Service]
Type=simple
Slice=aa-agent.slice
{env}
MemoryMax=256M
TasksMax=64
LimitNOFILE=2048
ExecStart={py} {root}/analytics/runtime_api_server.py --serve
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-runtime-api

[Install]
WantedBy=default.target
"""


def _evidence_watch_service(root: Path) -> str:
    py = _py(root)
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha Evidence Watch (oneshot)
PartOf=aa-runtime.slice

[Service]
Type=oneshot
Slice=aa-agent.slice
{env}
ExecStart={py} {root}/tools/ai_kernel.py runtime-watch
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-evidence-watch
"""


def _evidence_watch_timer() -> str:
    return """[Unit]
Description=Active Alpha Evidence Watch timer

[Timer]
OnBootSec=45
OnUnitActiveSec=30
Persistent=true

[Install]
WantedBy=timers.target
"""


def _spread_tick_service(root: Path) -> str:
    py = _py(root)
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha Spread Tick (Launch phases)
PartOf=aa-runtime.slice

[Service]
Type=oneshot
Slice=aa-agent.slice
{env}
ExecStart={py} {root}/tools/ai_kernel.py spread-tick
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-spread-tick
"""


def _spread_tick_timer() -> str:
    return """[Unit]
Description=Active Alpha Spread Tick timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
"""


def _king_local_worker_service(root: Path) -> str:
    """König-PC: lokaler Compute-Worker gegen 127.0.0.1:17890 (kein Worker-Bundle)."""
    py = _py(root)
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha — König Local Compute Worker
After=network-online.target active-alpha-preview-hub.service
Wants=active-alpha-preview-hub.service
PartOf=aa-runtime.slice
ConditionPathExists=!{root}/control/preview_worker_join.json

[Service]
Type=simple
Slice=aa-agent.slice
{env}
ExecStart=/bin/bash -lc 'while true; do {py} {root}/tools/preview_federation_worker.py --join http://127.0.0.1:17890 --no-preview --once || true; sleep 30; done'
Restart=on-failure
RestartSec=45
StartLimitBurst=5
StartLimitIntervalSec=300
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-king-worker

[Install]
WantedBy=default.target
"""


def _tunnel_stable_service(root: Path) -> str:
    py = _py(root)
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha — stabiler Tunnel (Token/Paste auto-apply)
After=network-online.target active-alpha-preview-hub.service
PartOf=aa-runtime.slice

[Service]
Type=oneshot
Slice=aa-tunnel.slice
{env}
EnvironmentFile=-{root}/control/server.env
ExecStart={py} -c "from pathlib import Path; from analytics.tunnel_control import tunnel_control_try_apply; import json, os; r=Path(os.environ.get('AA_PROJECT_ROOT', '{root}')); print(json.dumps(tunnel_control_try_apply(r, silent=True), ensure_ascii=False))"
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-tunnel-stable
"""


def _tunnel_stable_timer() -> str:
    return """[Unit]
Description=Active Alpha Tunnel-Stable timer

[Timer]
OnBootSec=90
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
"""


def _h1_resume_service(root: Path) -> str:
    py = _py(root)
    env = _common_service_env(root)
    return f"""[Unit]
Description=Active Alpha H1 resume if zombie
ConditionPathExists={root}/validation_runs
PartOf=aa-runtime.slice

[Service]
Type=oneshot
Slice=aa-h1.slice
{env}
MemoryMax=48G
TasksMax=512
LimitNOFILE=65536
Nice=8
IOSchedulingClass=idle
ExecStartPre={py} {root}/tools/ai_kernel.py runtime-h1-prep
ExecStart={py} {root}/tools/ai_kernel.py h1
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-h1-resume
"""


def _h1_resume_timer() -> str:
    return """[Unit]
Description=Active Alpha H1 zombie resume timer

[Timer]
OnBootSec=90
OnCalendar=*-*-* 06,10,14,18,22:05:00
Persistent=true

[Install]
WantedBy=timers.target
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def install_linux_runtime(
    root: Path,
    *,
    enable: bool = True,
    _slice_install_only: bool = False,
) -> Dict[str, Any]:
    """Slices, Limits, API, Evidence-Watch, Spread-Tick installieren."""
    root = Path(root)
    if not _slice_install_only:
        try:
            from analytics.linux_runtime_unified import install_authoritative_runtime, kernel_is_authoritative

            if kernel_is_authoritative(root):
                return install_authoritative_runtime(root, enable=enable)
        except Exception:
            pass
    try:
        from analytics.kernel_boundary_secure import audit_kernel_boundary

        audit_kernel_boundary(root)
    except Exception:
        pass
    unit_dir = _unit_dir()
    installed: List[str] = []
    errors: List[str] = []

    for name, body in _SLICES.items():
        _write(unit_dir / name, body.format(root=root))
        installed.append(name)

    _write(unit_dir / "active-alpha-preview-hub.service", _hub_service(root))
    installed.append("active-alpha-preview-hub.service")

    try:
        from analytics.remote_hub_access import cloudflared_path, load_tunnel_token

        cloudflared = cloudflared_path(root)
        token = load_tunnel_token(root)
        tunnel_exec = ""
        py = _py(root)
        if cloudflared and token:
            tunnel_exec = f"{cloudflared} tunnel --no-autoupdate run --token {token}"
        elif cloudflared:
            tunnel_exec = f"{py} {root}/tools/run_remote_tunnel.py"
        if tunnel_exec:
            _write(unit_dir / "active-alpha-remote-tunnel.service", _tunnel_service(root, tunnel_exec))
            installed.append("active-alpha-remote-tunnel.service")
    except Exception as exc:
        errors.append(f"tunnel: {exc}")

    _write(unit_dir / "active-alpha-runtime-api.service", _runtime_api_service(root))
    _write(unit_dir / "active-alpha-evidence-watch.service", _evidence_watch_service(root))
    _write(unit_dir / "active-alpha-evidence-watch.timer", _evidence_watch_timer())
    _write(unit_dir / "active-alpha-spread-tick.service", _spread_tick_service(root))
    _write(unit_dir / "active-alpha-spread-tick.timer", _spread_tick_timer())
    _write(unit_dir / "active-alpha-tunnel-stable.service", _tunnel_stable_service(root))
    _write(unit_dir / "active-alpha-tunnel-stable.timer", _tunnel_stable_timer())
    _write(unit_dir / "active-alpha-h1-resume.service", _h1_resume_service(root))
    _write(unit_dir / "active-alpha-h1-resume.timer", _h1_resume_timer())
    if not (root / "control/preview_worker_join.json").is_file():
        _write(unit_dir / "active-alpha-preview-worker.service", _king_local_worker_service(root))
        installed.append("active-alpha-preview-worker.service")
    installed.extend(
        [
            "active-alpha-runtime-api.service",
            "active-alpha-evidence-watch.service",
            "active-alpha-evidence-watch.timer",
            "active-alpha-spread-tick.service",
            "active-alpha-spread-tick.timer",
            "active-alpha-tunnel-stable.service",
            "active-alpha-tunnel-stable.timer",
            "active-alpha-h1-resume.service",
            "active-alpha-h1-resume.timer",
        ]
    )

    apparmor_dir = root / "control" / "apparmor"
    apparmor_dir.mkdir(parents=True, exist_ok=True)
    profile = apparmor_dir / "active-alpha-hub.profile"
    if not profile.is_file():
        profile.write_text(
            f"""# Optional — sudo apparmor_parser -r {profile}
#include <tunables/global>
profile active-alpha-hub flags=(attach_disconnected) {{
  {root}/.venv/bin/python3 mr,
  {root}/tools/preview_hub.py r,
  {root}/evidence/** rw,
  {root}/control/** r,
  network tcp port 17890,
  deny /home/*/.ssh/** r,
}}
""",
            encoding="utf-8",
        )
        installed.append(str(profile.relative_to(root)))

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    if enable:
        for unit in (
            "active-alpha-preview-hub.service",
            "active-alpha-runtime-api.service",
            "active-alpha-evidence-watch.timer",
            "active-alpha-spread-tick.timer",
            "active-alpha-h1-resume.timer",
        ):
            subprocess.run(["systemctl", "--user", "enable", unit], check=False)
        for unit in (
            "active-alpha-preview-hub.service",
            "active-alpha-runtime-api.service",
        ):
            subprocess.run(["systemctl", "--user", "restart", unit], check=False)
        for timer in (
            "active-alpha-evidence-watch.timer",
            "active-alpha-spread-tick.timer",
            "active-alpha-tunnel-stable.timer",
            "active-alpha-h1-resume.timer",
        ):
            subprocess.run(["systemctl", "--user", "enable", "--now", timer], check=False)
        tunnel_unit = unit_dir / "active-alpha-remote-tunnel.service"
        if tunnel_unit.is_file():
            subprocess.run(["systemctl", "--user", "enable", "active-alpha-remote-tunnel.service"], check=False)
            subprocess.run(["systemctl", "--user", "restart", "active-alpha-remote-tunnel.service"], check=False)
        worker_unit = unit_dir / "active-alpha-preview-worker.service"
        if worker_unit.is_file() and not (root / "control/preview_worker_join.json").is_file():
            subprocess.run(["systemctl", "--user", "enable", "active-alpha-preview-worker.service"], check=False)
            subprocess.run(["systemctl", "--user", "restart", "active-alpha-preview-worker.service"], check=False)

    doc = {
        "schema_version": 1,
        "installed_at_utc": _utc_now(),
        "installed": installed,
        "errors": errors,
        "unit_dir": str(unit_dir),
        "headline_de": "Linux Runtime installiert — Slices, Limits, API, Watch",
        "journal_de": "journalctl --user -t aa-hub -t aa-runtime-api -t aa-evidence-watch -f",
        "api_query_de": f"{_py(root)} {root}/analytics/runtime_api_server.py --query h1.status",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    try:
        from analytics.runtime_structured_log import emit_runtime_log

        emit_runtime_log("runtime-install", "complete", root=root, persist=True, units=len(installed))
    except Exception:
        pass
    return doc


def build_runtime_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    units = [
        "aa-runtime.slice",
        "aa-h1.slice",
        "aa-hub.slice",
        "aa-tunnel.slice",
        "aa-agent.slice",
        "active-alpha-preview-hub.service",
        "active-alpha-runtime-api.service",
        "active-alpha-evidence-watch.timer",
        "active-alpha-spread-tick.timer",
        "active-alpha-h1-resume.timer",
    ]
    states: Dict[str, str] = {}
    for unit in units:
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            states[unit] = (proc.stdout or proc.stderr or "unknown").strip()
        except Exception:
            states[unit] = "error"

    api_ok = False
    try:
        from analytics.runtime_api_server import query

        ping = query(root, "ping")
        api_ok = bool(ping.get("ok"))
    except Exception:
        pass

    watch_doc: Dict[str, Any] = {}
    watch_path = root / "evidence/runtime_watch_latest.json"
    if watch_path.is_file():
        try:
            watch_doc = json.loads(watch_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "systemd": states,
        "runtime_api_ok": api_ok,
        "watch_event_count": int(watch_doc.get("event_count") or 0),
        "h1_from_watch": watch_doc.get("h1"),
        "headline_de": "Runtime aktiv" if api_ok else "Runtime teilweise — ai_kernel runtime-install",
    }


def runtime_h1_prep(root: Path) -> Dict[str, Any]:
    """NUMA/vmtouch vor H1-Start — nur bei ZOMBIE/Resume."""
    root = Path(root)
    from analytics.live_profile_governance import h1_backtest_status

    status = h1_backtest_status(root)
    out: Dict[str, Any] = {"status": status.get("status"), "prep": []}
    if str(status.get("status")) not in ("ZOMBIE", "RUNNING", "MISSING"):
        return out
    try:
        from execution.h1_linux_boost import numa_exec_prefix, warm_run_artifacts

        prefix = numa_exec_prefix()
        if prefix:
            out["numa_prefix"] = prefix
            out["prep"].append("numactl")
        warm = warm_run_artifacts(root, status.get("run_dir"))
        out["warm"] = warm
        if warm.get("warmed"):
            out["prep"].append("vmtouch")
    except Exception as exc:
        out["prep_error"] = str(exc)[:200]
    return out
