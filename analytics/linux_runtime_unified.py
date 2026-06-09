"""Harmonisiert Linux-Legacy mit Cognitive Kernel v2, Preview Hub und Operator-Stack."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/linux_runtime_unified.json")
_TIMERS_CATALOG_REL = Path("control/linux_operator_timers.json")
_DECOM_REL = Path("evidence/old_stack_decommission_latest.json")

_V2_TIMERS = (
    {
        "id": "cognitive-scheduler",
        "label_de": "Cognitive Scheduler v2",
        "schedule_de": "alle 5 min — H1, Hub, Prioritäten",
        "command": "ai_kernel cognitive-scheduler",
        "plane": "v2",
    },
    {
        "id": "cognitive-observe",
        "label_de": "Kernel Observer",
        "schedule_de": "alle 10 min — ebpf_observer",
        "command": "ai_kernel cognitive-observe",
        "plane": "v2",
    },
    {
        "id": "boot",
        "label_de": "Boot-Services",
        "schedule_de": "3 min nach Anmeldung/Boot",
        "command": "tools/linux_boot_services.sh",
        "plane": "v2",
    },
)

_LEGACY_TIMERS = (
    {
        "id": "trading-day",
        "label_de": "Trading-Day-Orchestrator",
        "schedule_de": "Mo–Fr 14:00 — Sync, Mark, Warnungen, Cockpit",
        "command": "ai_kernel trading-day --trading-day-phase full",
        "plane": "legacy",
    },
    {
        "id": "refresh",
        "label_de": "Headless Refresh",
        "schedule_de": "Mo–Fr 14:30–22:00 alle 30 min",
        "command": "ai_kernel refresh --refresh-mode snapshot",
        "plane": "legacy",
    },
    {
        "id": "refresh-preus",
        "label_de": "Pre-US Kurse",
        "schedule_de": "Mo–Fr 15:15 + 15:25",
        "command": "ai_kernel trading-day --trading-day-phase pre-us",
        "plane": "legacy",
    },
    {
        "id": "refresh-usopen",
        "label_de": "US-Eröffnung Burst",
        "schedule_de": "Mo–Fri 15:30–16:30 alle 5 min",
        "command": "ai_kernel trading-day --trading-day-phase us-open",
        "plane": "legacy",
    },
    {
        "id": "prognosis-eod",
        "label_de": "Prognose EOD (R3 Freischaltung)",
        "schedule_de": "täglich 22:15 CET — king_ops prognosis run",
        "command": "bash tools/king_ops.sh prognosis run",
        "plane": "legacy",
    },
    {
        "id": "learn",
        "label_de": "Lernzyklus (Worker → Preview)",
        "schedule_de": "täglich 22:05",
        "command": "ai_kernel learn",
        "plane": "legacy",
    },
    {
        "id": "gui-preview",
        "label_de": "R3 Cockpit (Tages-Aggregator)",
        "schedule_de": "täglich 22:25 nach learn",
        "command": "ai_kernel gui-preview",
        "plane": "legacy",
    },
    {
        "id": "h1-watch",
        "label_de": "H1-Backtest Watch + Governance",
        "schedule_de": "4× täglich 08/12/16/20",
        "command": "ai_kernel h1-watch",
        "plane": "legacy",
    },
    {
        "id": "warnings",
        "label_de": "Handels-Warnungen (cached snap)",
        "schedule_de": "Mo–Fr 14:25",
        "command": "ai_kernel warnings",
        "plane": "legacy",
    },
)


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


def load_runtime_unified(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _CONFIG_REL)
    if doc:
        return doc
    return {
        "schema_version": 1,
        "control_plane": "cognitive_kernel_v2",
        "status_spine": {"builder": "analytics/preview_system_status.py"},
    }


def is_old_stack_decommissioned(root: Path) -> bool:
    doc = _load_json(Path(root) / _DECOM_REL)
    return bool(doc.get("masked_services") or doc.get("disabled_timers"))


def cognitive_v2_active(root: Path) -> bool:
    try:
        from analytics.cognitive_kernel import cognitive_kernel_status

        return bool(cognitive_kernel_status(root).get("successor_active"))
    except Exception:
        return False


def kernel_is_authoritative(root: Path) -> bool:
    """Cognitive Kernel v2 — der einzige wahre Steuerungskernel."""
    return cognitive_v2_active(root)


def kernel_supremacy_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_runtime_unified(root)
    auth = kernel_is_authoritative(root)
    sup = cfg.get("kernel_supremacy") or {}
    return {
        "schema_version": 1,
        "authoritative": auth,
        "kernel_name_de": str(sup.get("name_de") or "Cognitive Kernel v2"),
        "supremacy_de": str(
            sup.get("doctrine_de")
            or "Der einzig wahre Steuerungskernel — Cursor-Interface, aa_scheduler, Preview Hub."
        ),
        "linux_mainline_de": str(
            sup.get("linux_mainline_de")
            or "Ubuntu-Kernel bleibt — nur die Userspace-Steuerungsschicht ist autoritativ."
        ),
        "sole_orchestrator": "active-alpha-cognitive-scheduler.timer",
        "sole_status_spine": "preview_system_status",
        "supersedes_de": list(
            sup.get("supersedes_de")
            or [
                "Legacy daily timers",
                "stable-server / server-bootstrap als König",
                "Parallele Hub-Systemd-Services nach Decommission",
            ]
        ),
        "legacy_blocked": auth,
    }


def control_plane_mode(root: Path) -> str:
    """v2 | legacy — kein Hybrid wenn Kernel autoritativ."""
    if kernel_is_authoritative(root):
        return "v2"
    return "legacy"


def _unit_state(unit: str) -> str:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-enabled", unit],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return (proc.stdout or "").strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _unit_usable(unit: str) -> bool:
    return _unit_state(unit) not in ("masked", "disabled", "not-found", "unknown")


def effective_keep_timers(root: Path) -> Set[str]:
    root = Path(root)
    mode = control_plane_mode(root)
    if mode == "v2":
        base = {
            "active-alpha-cognitive-scheduler.timer",
            "active-alpha-cognitive-observe.timer",
        }
    else:
        base = {
            "active-alpha-h1-resume.timer",
            "active-alpha-h1-watch.timer",
            "active-alpha-evidence-watch.timer",
            "active-alpha-cognitive-scheduler.timer",
            "active-alpha-cognitive-observe.timer",
        }
    return {u for u in base if _unit_usable(u)}


def effective_keep_services(root: Path) -> Set[str]:
    root = Path(root)
    if is_old_stack_decommissioned(root) or control_plane_mode(root) == "v2":
        return set()
    base = {
        "active-alpha-preview-hub.service",
        "active-alpha-remote-tunnel.service",
        "active-alpha-runtime-api.service",
    }
    return {u for u in base if _unit_usable(u)}


def runtime_profile(root: Path) -> Dict[str, Any]:
    root = Path(root)
    mode = control_plane_mode(root)
    decom = is_old_stack_decommissioned(root)
    lean = _load_json(root / "evidence/aa_lean_mode_latest.json")
    return {
        "schema_version": 1,
        "checked_at_utc": _utc_now(),
        "control_plane": mode,
        "config_control_plane": load_runtime_unified(root).get("control_plane"),
        "cognitive_v2_active": cognitive_v2_active(root),
        "old_stack_decommissioned": decom,
        "lean_mode": lean.get("mode"),
        "lean_active": bool(lean.get("enabled_at_utc")),
        "keep_timers": sorted(effective_keep_timers(root)),
        "keep_services": sorted(effective_keep_services(root)),
        "status_spine": "preview_system_status",
        "kernel_supremacy": kernel_supremacy_status(root),
        "headline_de": (
            kernel_supremacy_status(root).get("supremacy_de")
            if mode == "v2"
            else "Legacy — Nachfolge ausstehend (ai_kernel cognitive-succession)"
        ),
    }


def install_authoritative_runtime(root: Path, *, enable: bool = True) -> Dict[str, Any]:
    """Runtime nur unter Cognitive Kernel v2 — kein Legacy-Stack."""
    root = Path(root)
    messages: List[str] = []
    ck: Dict[str, Any] = {}
    ok = False
    try:
        from analytics.cognitive_kernel import install_cognitive_kernel_v2

        ck = install_cognitive_kernel_v2(root)
        messages.append(str(ck.get("headline_de") or "cognitive-kernel"))
        ok = bool(ck.get("ok", True))
    except Exception as exc:
        messages.append(f"cognitive-kernel: {exc}")
    catalog = sync_operator_timer_catalog(root)
    hub = ensure_preview_hub_boot(root) if enable else {"skipped": True}
    if hub.get("ok"):
        messages.append(f"Hub :{hub.get('port', 17890)}")
    federation: Dict[str, Any] = {}
    try:
        from analytics.aa_linux_runtime import install_linux_runtime

        federation = install_linux_runtime(root, enable=enable, _slice_install_only=True)
        messages.append(str(federation.get("headline_de") or "federation-systemd"))
        ok = ok and bool(federation.get("installed"))
    except Exception as exc:
        messages.append(f"federation-systemd: {exc}")
    doc = {
        "ok": ok,
        "schema_version": 1,
        "installed_at_utc": _utc_now(),
        "kernel_supremacy": kernel_supremacy_status(root),
        "cognitive_kernel": ck,
        "federation_systemd": federation,
        "timer_catalog": catalog,
        "hub": hub,
        "messages_de": messages,
        "headline_de": "Cognitive Kernel v2 + Federation systemd (Hub/Tunnel/Worker)",
        "legacy_skipped_de": "stable-server/bootstrap nicht reaktiviert — Hub/Tunnel/Worker via aa_linux_runtime",
    }
    atomic_write_json(root / "evidence/aa_linux_runtime_latest.json", doc)
    return doc


def sync_operator_timer_catalog(root: Path) -> Dict[str, Any]:
    """linux_operator_timers.json aus Unified-Definition spiegeln."""
    root = Path(root)
    mode = control_plane_mode(root)
    timers: List[Dict[str, Any]] = []
    if mode == "v2":
        timers.extend(dict(t) for t in _V2_TIMERS)
    elif mode == "legacy":
        timers.extend(dict(t) for t in _LEGACY_TIMERS)
        timers.extend(dict(t) for t in _V2_TIMERS)
    doc = {
        "schema_version": 3,
        "generated_at_utc": _utc_now(),
        "control_plane": mode,
        "source": "linux_runtime_unified",
        "timers": timers,
    }
    atomic_write_json(root / _TIMERS_CATALOG_REL, doc)
    return doc


def ensure_preview_hub_boot(root: Path) -> Dict[str, Any]:
    """Hub ohne privilegierten server-bootstrap — Scheduler-kompatibel."""
    root = Path(root)
    try:
        from analytics.hub_runtime import ensure_running

        port = int(ensure_running(root, restart=False))
        return {"ok": True, "port": port, "method": "hub_runtime.ensure_running"}
    except Exception as exc:
        return {"ok": False, "error_de": str(exc)[:200], "method": "ensure_hub_running"}


def install_operator_timers(root: Path) -> Dict[str, Any]:
    """Timer-Setup — nur Cognitive Kernel v2 wenn autoritativ."""
    root = Path(root)
    mode = control_plane_mode(root)
    catalog = sync_operator_timer_catalog(root)
    messages: List[str] = []
    code = 0

    if kernel_is_authoritative(root):
        messages.append("Cognitive Kernel v2 ist autoritativ — Legacy-Timer blockiert.")
        try:
            from analytics.cognitive_kernel import install_cognitive_kernel_v2

            ck = install_cognitive_kernel_v2(root)
            messages.append(str(ck.get("headline_de") or "cognitive-kernel"))
            code = 0 if ck.get("ok", True) else 1
        except Exception as exc:
            messages.append(f"cognitive-kernel: {exc}")
            code = 1
        return {
            "ok": code == 0,
            "control_plane": mode,
            "kernel_supremacy": kernel_supremacy_status(root),
            "catalog": catalog,
            "messages_de": messages,
            "headline_de": "Einziger Kernel — v2 Timer",
        }

    proc = subprocess.run(
        ["bash", "tools/setup_linux_daily_timers.sh"],
        cwd=str(root),
        check=False,
    )
    if proc.returncode != 0:
        code = proc.returncode
        messages.append("Legacy setup_linux_daily_timers.sh fehlgeschlagen")
    else:
        messages.append("Legacy daily timers (Nachfolge noch nicht aktiv)")
    return {
        "ok": code == 0,
        "control_plane": mode,
        "catalog": catalog,
        "messages_de": messages,
        "headline_de": "Legacy-Timer — cognitive-succession ausstehend",
    }


def install_harmonized_autostart(root: Path) -> Dict[str, Any]:
    """Vollständiger Autostart — v2-first, Legacy nur wenn erlaubt."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []
    code = 0

    for script, label in (
        ("tools/setup_r3_desktop_os.sh", "r3_desktop_os"),
        ("tools/setup_linux_autostart.sh", "menu_autostart"),
    ):
        proc = subprocess.run(["bash", script], cwd=str(root), check=False)
        steps.append({"step": label, "ok": proc.returncode == 0})
        if proc.returncode != 0:
            code = proc.returncode

    timer_doc = install_operator_timers(root)
    steps.append({"step": "timers", "ok": timer_doc.get("ok"), "detail": timer_doc.get("headline_de")})
    if not timer_doc.get("ok"):
        code = 1

    if kernel_is_authoritative(root):
        rt = install_authoritative_runtime(root)
        steps.append({"step": "authoritative_runtime", "ok": rt.get("ok"), "detail": rt.get("headline_de")})
    elif not is_old_stack_decommissioned(root):
        proc = subprocess.run(["bash", "tools/setup_aa_runtime.sh"], cwd=str(root), check=False)
        steps.append({"step": "runtime_install", "ok": proc.returncode == 0})

    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    boot_script = root / "tools/linux_boot_services.sh"
    boot_script.chmod(0o755)
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path("python3")

    boot_service = f"""[Unit]
Description=R3 — Boot-Services (harmonized v2)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={root}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT={root}
ExecStart={boot_script}
"""
    boot_timer = """[Unit]
Description=R3 timer — boot services

[Timer]
OnBootSec=3min
Persistent=true

[Install]
WantedBy=timers.target
"""
    (unit_dir / "active-alpha-boot.service").write_text(boot_service, encoding="utf-8")
    (unit_dir / "active-alpha-boot.timer").write_text(boot_timer, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, timeout=5)
    if _unit_usable("active-alpha-boot.timer"):
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "active-alpha-boot.timer"],
            check=False,
            timeout=8,
        )
        steps.append({"step": "boot_timer", "ok": True})
    else:
        steps.append({"step": "boot_timer", "ok": False, "detail": "boot timer masked/disabled"})

    try:
        subprocess.run(["loginctl", "enable-linger", os.environ.get("USER", "")], check=False, timeout=5)
    except Exception:
        pass

    profile = runtime_profile(root)
    return {
        "ok": code == 0,
        "steps": steps,
        "profile": profile,
        "timer_install": timer_doc,
        "headline_de": profile.get("headline_de"),
    }
