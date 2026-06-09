"""Cognitive Kernel — Nachfolger der ad-hoc Steuerung, Linux-Mainline bleibt."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_MANIFEST_REL = Path("control/cognitive_kernel_manifest.json")
_SUCCESSION_ACK_REL = Path("evidence/kernel_succession_operator_ack.json")
_EVIDENCE_REL = Path("evidence/cognitive_kernel_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def record_operator_succession(
    root: Path,
    *,
    detail_de: str = "Operator erlaubt Cognitive-Kernel-Nachfolge — kein Linux-Image-Tausch",
    approved_by: str = "user",
) -> Dict[str, Any]:
    root = Path(root)
    doc = {
        "schema_version": 1,
        "ok": True,
        "ack_at_utc": _utc_now(),
        "approved_by": approved_by,
        "succession_de": "Alter ad-hoc-Stack wird durch Cognitive Kernel abgelöst",
        "interface_foundation_de": "Grundlage: Cursor-Interface (natürliche Sprache) — Ollama-Fallback bei Ausfall",
        "linux_mainline_de": "Ubuntu-Kernel 7.x bleibt — nur Steuerungsschicht wird Nachfolger",
        "detail_de": detail_de,
        "forbidden_de": "/boot, vmlinuz, unsigned Module — Policy unverändert",
    }
    atomic_write_json(root / _SUCCESSION_ACK_REL, doc)
    try:
        from analytics.kernel_boundary_secure import write_apply_ack

        write_apply_ack(
            root,
            detail_de="Cognitive-Kernel-Nachfolge — Runtime Apply freigegeben",
        )
    except Exception:
        pass
    return doc


def load_manifest(root: Path) -> Dict[str, Any]:
    path = Path(root) / _MANIFEST_REL
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema_version": 1,
        "kernel_generation": 1,
        "name_de": "Cognitive Kernel",
    }


def _unit_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"


def _py(root: Path) -> str:
    v = root / ".venv/bin/python3"
    return str(v) if v.is_file() else "python3"


def _scheduler_service(root: Path) -> str:
    py = _py(root)
    return f"""[Unit]
Description=Active Alpha Cognitive Scheduler (v2)
PartOf=aa-runtime.slice

[Service]
Type=oneshot
Slice=aa-agent.slice
WorkingDirectory={root}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT={root}
ExecStart={py} {root}/tools/ai_kernel.py cognitive-scheduler
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-cognitive-scheduler
"""


def _observer_service(root: Path) -> str:
    py = _py(root)
    return f"""[Unit]
Description=Active Alpha Kernel Observer (eBPF/proc fallback)
PartOf=aa-runtime.slice

[Service]
Type=oneshot
Slice=aa-agent.slice
WorkingDirectory={root}
Environment=AA_PROJECT_ROOT={root}
ExecStart={py} {root}/tools/ai_kernel.py cognitive-observe
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aa-cognitive-observe
"""


def _timer_body(interval: str) -> str:
    return f"""[Unit]
Description=Active Alpha Cognitive Kernel timer

[Timer]
OnBootSec=60
OnUnitActiveSec={interval}
Persistent=true

[Install]
WantedBy=timers.target
"""


def install_cognitive_kernel_v2(root: Path, *, enable: bool = True) -> Dict[str, Any]:
    """Nachfolger aktivieren — Runtime v2 + Scheduler + Observer."""
    root = Path(root)
    ack_path = root / _SUCCESSION_ACK_REL
    if not ack_path.is_file():
        return {
            "ok": False,
            "blocked_de": "Operator-Ack fehlt — evidence/kernel_succession_operator_ack.json",
        }

    from analytics.aa_linux_runtime import install_linux_runtime

    runtime = install_linux_runtime(root, enable=enable, _slice_install_only=True)

    unit_dir = _unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / "active-alpha-cognitive-scheduler.service").write_text(
        _scheduler_service(root), encoding="utf-8"
    )
    sched_iv = "5min"
    obs_iv = "10min"
    try:
        orch_path = root / "control/cognitive_orchestrator.json"
        if orch_path.is_file():
            orch = json.loads(orch_path.read_text(encoding="utf-8"))
            if orch.get("fast_mode"):
                sched_iv = str(orch.get("scheduler_interval") or "1min")
                obs_iv = str(orch.get("observer_interval") or "5min")
    except (json.JSONDecodeError, OSError):
        pass
    (unit_dir / "active-alpha-cognitive-scheduler.timer").write_text(
        _timer_body(sched_iv), encoding="utf-8"
    )
    (unit_dir / "active-alpha-cognitive-observe.service").write_text(
        _observer_service(root), encoding="utf-8"
    )
    (unit_dir / "active-alpha-cognitive-observe.timer").write_text(
        _timer_body(obs_iv), encoding="utf-8"
    )

    manifest = {
        "schema_version": 2,
        "kernel_generation": 2,
        "name_de": "Cognitive Kernel v2",
        "successor_de": "Ersetzt ad-hoc Hub/H1-Governance als einheitliche Steuerungsschicht",
        "linux_mainline_de": "Unverändert — Nachfolge nur auf Control-Plane-Ebene",
        "components": [
            "aa_linux_runtime",
            "aa_scheduler",
            "ebpf_observer",
            "runtime_api",
            "agent_mandate",
            "kernel_boundary_policy",
            "operator_sovereignty",
            "alpha_model_interface_kernel",
        ],
        "installed_at_utc": _utc_now(),
        "systemd_units": [
            "active-alpha-cognitive-scheduler.timer",
            "active-alpha-cognitive-observe.timer",
        ],
    }
    atomic_write_json(root / _MANIFEST_REL, manifest)

    if enable:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        for t in (
            "active-alpha-cognitive-scheduler.timer",
            "active-alpha-cognitive-observe.timer",
        ):
            subprocess.run(["systemctl", "--user", "enable", "--now", t], check=False)

    from analytics.aa_scheduler import run_aa_scheduler
    from analytics.ebpf_observer import run_kernel_observer

    sched = run_aa_scheduler(root)
    obs = run_kernel_observer(root)

    doc = {
        "schema_version": 2,
        "ok": True,
        "installed_at_utc": _utc_now(),
        "headline_de": "Cognitive Kernel v2 aktiv — Nachfolger des alten Steuerungsmodells",
        "runtime": runtime,
        "scheduler": sched,
        "observer": obs,
        "manifest": manifest,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    try:
        from analytics.runtime_structured_log import emit_runtime_log

        emit_runtime_log("cognitive-kernel", "succession_v2", root=root, persist=True)
    except Exception:
        pass
    return doc


def cognitive_kernel_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    manifest = load_manifest(root)
    ack = {}
    ack_path = root / _SUCCESSION_ACK_REL
    if ack_path.is_file():
        try:
            ack = json.loads(ack_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    try:
        from analytics.alpha_model_interface_kernel import interface_stack_status

        iface = interface_stack_status(root)
    except Exception:
        iface = {}
    gen = int(manifest.get("kernel_generation") or 1)
    successor = gen >= 2 and bool(ack.get("ok"))
    return {
        "schema_version": 1,
        "kernel_generation": gen,
        "successor_active": successor,
        "operator_ack": bool(ack.get("ok")),
        "name_de": manifest.get("name_de"),
        "manifest": manifest,
        "interface": iface,
        "interface_foundation_de": manifest.get("interface_foundation_de")
        or "Alpha Model Interface — Runtime primär, Werkstatt optional",
        "interface_fallback_de": manifest.get("interface_fallback_de")
        or "R3 KI im Cockpit",
        "build_kernel_de": "R3 Bau-Kernel — liest, schreibt, testet in Agenten-Schleife",
        "headline_de": (
            f"Cognitive Kernel v2 — Bau-Kernel · {iface.get('headline_de', 'R3')}"
            if successor
            else "Cognitive Kernel v1 — Nachfolge ausstehend"
        ),
    }
