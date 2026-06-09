"""Formale Kernel-Nachfolge abschließen — Urkunde, Alt-Stack entfernen, Gates prüfen."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from aa_safe_io import atomic_write_json

_COMPLETE_REL = Path("evidence/kernel_succession_complete.json")
_DECOM_REL = Path("evidence/old_stack_decommission_latest.json")

_OLD_SERVICES = (
    "active-alpha-preview-hub.service",
    "active-alpha-remote-tunnel.service",
    "active-alpha-runtime-api.service",
    "active-alpha-stable-server.service",
    "active-alpha-preview-worker.service",
)

_OLD_TIMERS = (
    "active-alpha-h1-resume.timer",
    "active-alpha-h1-watch.timer",
    "active-alpha-evidence-watch.timer",
    "active-alpha-refresh.timer",
    "active-alpha-refresh-preus.timer",
    "active-alpha-refresh-usopen.timer",
    "active-alpha-trading-day.timer",
    "active-alpha-warnings.timer",
    "active-alpha-learn.timer",
    "active-alpha-gui-preview.timer",
    "active-alpha-spread-tick.timer",
    "active-alpha-spread-tick-1.timer",
    "active-alpha-spread-tick-2.timer",
    "active-alpha-spread-tick-3.timer",
    "active-alpha-spread-tick-4.timer",
    "active-alpha-boot.timer",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def decommission_old_stack(root: Path) -> Dict[str, Any]:
    """Alte ad-hoc-Services maskieren — Cognitive Kernel v2 + Cursor ersetzen sie."""
    root = Path(root)
    masked_services: List[str] = []
    disabled_timers: List[str] = []
    errors: List[str] = []

    for unit in _OLD_SERVICES:
        try:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=8)
            subprocess.run(["systemctl", "--user", "disable", unit], check=False, timeout=5)
            subprocess.run(["systemctl", "--user", "mask", unit], check=False, timeout=5)
            if _unit_state(unit) in ("masked", "disabled"):
                masked_services.append(unit)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{unit}: {exc}")

    for unit in _OLD_TIMERS:
        try:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=5)
            subprocess.run(["systemctl", "--user", "disable", unit], check=False, timeout=5)
            if _unit_state(unit) == "disabled":
                disabled_timers.append(unit)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{unit}: {exc}")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, timeout=5)

    doc = {
        "schema_version": 1,
        "decommissioned_at_utc": _utc_now(),
        "masked_services": masked_services,
        "disabled_timers": disabled_timers,
        "errors": errors,
        "headline_de": (
            f"Alter Stack abgemeldet — {len(masked_services)} Services maskiert, "
            f"{len(disabled_timers)} Timer aus"
        ),
        "ok": len(errors) == 0,
    }
    atomic_write_json(root / _DECOM_REL, doc)
    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(
            root,
            level="B",
            action="old_stack_decommission",
            result="OK" if doc["ok"] else "PARTIAL",
            details={"masked": len(masked_services), "timers": len(disabled_timers)},
        )
    except Exception:
        pass
    return doc


def succession_gates(root: Path) -> Dict[str, Any]:
    """Alle Gates für kernel_succession_complete.json."""
    root = Path(root)
    gates: Dict[str, Any] = {}

    try:
        from analytics.cognitive_kernel import cognitive_kernel_status

        ck = cognitive_kernel_status(root)
        gates["cognitive_kernel_v2"] = bool(ck.get("successor_active"))
    except Exception:
        gates["cognitive_kernel_v2"] = False

    gates["alpha_model_interface"] = (root / "control/alpha_model_interface.json").is_file()
    gates["operator_ack"] = (root / "evidence/kernel_succession_operator_ack.json").is_file()

    try:
        from analytics.live_profile_governance import h1_backtest_status

        h1 = h1_backtest_status(root)
        run_rel = str(h1.get("run_dir") or "")
        run = root / run_rel if run_rel else None
        sealed = bool(run and (run / "strategy_daily_returns.csv").is_file())
        gates["h1_sealed"] = sealed
        gates["h1_status"] = h1.get("status")
        gates["h1_run_dir"] = run_rel or None
    except Exception:
        gates["h1_sealed"] = False

    decom = {}
    decom_path = root / _DECOM_REL
    if decom_path.is_file():
        try:
            decom = json.loads(decom_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    gates["old_stack_decommissioned"] = bool(decom.get("ok")) and len(decom.get("masked_services") or []) >= 3

    blockers = [k for k, v in gates.items() if k.endswith(("_sealed", "_v2", "_foundation", "_ack", "_decommissioned")) and not v]
    return {
        "gates": gates,
        "blockers": blockers,
        "ready": len(blockers) == 0,
    }


def write_succession_complete(root: Path, *, force_decommission: bool = True) -> Dict[str, Any]:
    """Urkunde schreiben wenn alle Gates grün — sonst Blocker melden."""
    root = Path(root)
    if force_decommission:
        decommission_old_stack(root)

    check = succession_gates(root)
    if not check["ready"]:
        return {
            "schema_version": 1,
            "ok": False,
            "blockers": check["blockers"],
            "gates": check["gates"],
            "headline_de": f"Nachfolge noch offen — Blocker: {', '.join(check['blockers'])}",
            "hint_de": "H1 muss sealed sein (strategy_daily_returns.csv), dann erneut succession-finish",
        }

    try:
        from analytics.alpha_model_interface_kernel import interface_stack_status

        iface = interface_stack_status(root)
    except Exception:
        iface = {}

    doc = {
        "schema_version": 1,
        "ok": True,
        "completed_at_utc": _utc_now(),
        "approved_by": "user",
        "title_de": "Kernel-Nachfolge abgeschlossen",
        "summary_de": (
            "Alter ad-hoc-Linux-Steuerungsstack ist durch Cognitive Kernel v2 ersetzt. "
            "Grundlage: R3 KI lokal (Ollama + Cockpit). Cursor IDE optional. "
            "Ubuntu-Mainline unverändert."
        ),
        "gates": check["gates"],
        "interface": {
            "primary": "r3_ki",
            "fallback": "ollama_local",
            "active": iface.get("active_interface"),
        },
        "supersedes_de": [
            "Lose Timer-Orchestrierung als Steuerzentrale",
            "Hub/Tunnel als autonome Kontrollebene",
            "Ad-hoc H1-Governance ohne Souveränität",
        ],
        "evidence_files": [
            "evidence/kernel_succession_operator_ack.json",
            "control/alpha_model_interface.json",
            "control/cognitive_kernel_manifest.json",
            "evidence/old_stack_decommission_latest.json",
        ],
        "headline_de": "Kernel-Nachfolge vollständig — alter Stack abgelöst, H1 sealed",
    }
    atomic_write_json(root / _COMPLETE_REL, doc)

    deadline_path = root / "evidence/kernel_succession_deadline.json"
    if deadline_path.is_file():
        try:
            dl = json.loads(deadline_path.read_text(encoding="utf-8"))
            for ms in dl.get("milestones") or []:
                if ms.get("id") in ("succession_complete", "h1_owner_succession"):
                    ms["status"] = "DONE"
            dl["headline_de"] = "Nachfolge abgeschlossen — Urkunde kernel_succession_complete.json"
            atomic_write_json(deadline_path, dl)
        except (json.JSONDecodeError, OSError):
            pass

    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(root, level="A", action="kernel_succession_complete", result="OK")
    except Exception:
        pass
    return doc


def launch_r3_desktop(root: Path) -> Dict[str, Any]:
    """R3-Marktanalyse mit BIOS-Logo starten (native Linux UI)."""
    root = Path(root)
    import os

    display = os.environ.get("DISPLAY", "").strip()
    wayland = os.environ.get("WAYLAND_DISPLAY", "").strip()
    if not display and not wayland:
        return {
            "ok": False,
            "blocked_de": "Kein Display — R3-UI nur mit Desktop-Session",
            "hint_de": "bash run_marktanalyse_linux.sh auf dem Ubuntu-Desktop",
        }

    script = root / "run_marktanalyse_linux.sh"
    if not script.is_file():
        return {"ok": False, "blocked_de": "run_marktanalyse_linux.sh fehlt"}

    env = os.environ.copy()
    env["AA_LINUX_NATIVE_APP"] = "1"
    env["AA_PROJECT_ROOT"] = str(root)
    try:
        proc = subprocess.Popen(
            ["bash", str(script)],
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return {"ok": False, "blocked_de": str(exc)[:200]}

    return {
        "ok": True,
        "pid": proc.pid,
        "app_title": "R3",
        "headline_de": "R3 Marktanalyse gestartet — Marktanalyse BIOS v2.0",
        "launch_script": str(script),
    }
