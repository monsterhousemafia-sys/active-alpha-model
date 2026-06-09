"""Einmaliger Post-Reboot-Kill: Entfaltungsraum führt /self-uninstall execute nach Neustart aus."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_PENDING_NAME = "post_reboot_self_uninstall.pending"
_EVIDENCE_REL = Path("evidence/alpha_model_post_reboot_kill_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pending_path() -> Path:
    return Path.home() / ".local/share/alpha-model" / _PENDING_NAME


def schedule_post_reboot_kill(root: Path, *, reason_de: str = "") -> Dict[str, Any]:
    """Vormerken: nach nächster Anmeldung führt der Entfaltungsraum Self-Uninstall aus."""
    root = Path(root)
    pending = _pending_path()
    pending.parent.mkdir(parents=True, exist_ok=True)

    try:
        from analytics.r3_conversation_continuity import verify_r3_chat_ready

        mig = verify_r3_chat_ready(root)
    except Exception as exc:
        mig = {"error_de": str(exc)[:120]}

    doc = {
        "schema_version": 1,
        "scheduled_at_utc": _utc_now(),
        "reason_de": reason_de or "Migration abgeschlossen — Cursor-Kill + apt remove nach Reboot",
        "purge_user_data": True,
        "apt_remove_cursor": True,
        "migration": {
            "checks_passed": mig.get("checks_passed"),
            "checks_total": mig.get("checks_total"),
            "ready": bool(mig.get("ready_for_r3_chat")),
        },
        "execute_env": "AA_SELF_UNINSTALL_EXECUTE=1",
        "primary_cli": "alpha-model-agent",
    }
    atomic_write_json(pending, doc)
    atomic_write_json(
        root / _EVIDENCE_REL,
        {
            **doc,
            "status": "SCHEDULED",
            "headline_de": "Post-Reboot-Kill vorgemerkt — Entfaltungsraum demontiert Cursor nach Anmeldung",
            "pending_path": str(pending),
        },
    )
    return {
        "ok": True,
        "scheduled": True,
        "pending_path": str(pending),
        "headline_de": "Nach Reboot: Entfaltungsraum führt /self-uninstall execute aus",
        "migration_ready": bool(mig.get("ready_for_r3_chat")),
    }


def run_post_reboot_kill_if_pending(root: Path) -> Dict[str, Any]:
    """Session-Autostart-Hook — nur wenn Pending-Flag gesetzt."""
    root = Path(root)
    pending = _pending_path()
    if not pending.is_file():
        return {"ok": True, "skipped": True, "reason_de": "kein Pending"}

    try:
        sched = json.loads(pending.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        sched = {}

    os.environ["AA_SELF_UNINSTALL_EXECUTE"] = "1"
    os.environ["AA_AGENT_CHAMBER"] = "1"

    from analytics.alpha_model_self_uninstall import run_self_uninstall

    doc = run_self_uninstall(root, dry_run=False, force_execute=True)

    apt_note = ""
    if not (Path("/usr/bin/cursor").is_file()):
        apt_note = "cursor-Paket nicht installiert"
    elif not doc.get("ok"):
        import subprocess

        try:
            proc = subprocess.run(
                ["sudo", "-n", "apt-get", "remove", "-y", "cursor"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            apt_note = f"apt retry exit={proc.returncode}"
        except (OSError, subprocess.TimeoutExpired) as exc:
            apt_note = f"apt retry fehlgeschlagen: {exc}"[:80]

    try:
        pending.unlink()
    except OSError:
        pass

    out = {
        "schema_version": 1,
        "ran_at_utc": _utc_now(),
        "scheduled_at_utc": sched.get("scheduled_at_utc"),
        "status": "EXECUTED" if doc.get("ok") else "FAILED",
        "self_uninstall": {
            "ok": doc.get("ok"),
            "dry_run": doc.get("dry_run"),
            "steps_passed": doc.get("steps_passed"),
            "steps_total": doc.get("steps_total"),
            "headline_de": doc.get("headline_de"),
        },
        "apt_remove_de": apt_note or None,
        "headline_de": (
            "Migration abgeschlossen — Cursor weg, Entfaltungsraum primär"
            if doc.get("ok")
            else "Post-Reboot-Kill fehlgeschlagen — alpha-model-agent → /self-uninstall execute"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out


def post_reboot_kill_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    pending = _pending_path()
    ev = root / _EVIDENCE_REL
    status: Dict[str, Any] = {
        "pending": pending.is_file(),
        "pending_path": str(pending),
        "evidence_path": str(ev),
    }
    if pending.is_file():
        try:
            status["pending_doc"] = json.loads(pending.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    if ev.is_file():
        try:
            status["latest"] = json.loads(ev.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return status
