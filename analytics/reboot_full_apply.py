"""Neustart — Vorbereitung, Pending-Marker, Post-Boot-Verifikation."""
from __future__ import annotations

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_PENDING_REL = Path("evidence/reboot_apply_pending.json")
_COMPLETE_REL = Path("evidence/reboot_apply_complete_latest.json")


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


def _autostart_ok() -> Dict[str, Any]:
    home = Path.home()
    desktop = home / ".config/autostart/r3-os-session.desktop"
    boot_timer = home / ".config/systemd/user/active-alpha-boot.timer"
    return {
        "r3_session_desktop": desktop.is_file(),
        "boot_timer": boot_timer.is_file(),
        "desktop_path": str(desktop) if desktop.is_file() else None,
    }


def prepare_before_reboot(root: Path) -> Dict[str, Any]:
    """Alle sicheren Schritte vor Reboot — Evidence persistieren, Pending setzen."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    def _step(step_id: str, label_de: str, fn) -> None:
        try:
            result = fn()
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else bool(result)
            steps.append({"id": step_id, "label_de": label_de, "ok": ok, "detail": result})
        except Exception as exc:
            steps.append({"id": step_id, "label_de": label_de, "ok": False, "error_de": str(exc)[:160]})

    _step(
        "r3_align",
        "R3 Abgleich",
        lambda: __import__(
            "analytics.r3_runtime_upgrade", fromlist=["align_r3_surface"]
        ).align_r3_surface(root, scan_upgrades=True, warm_cache=True, sync_flow=False, persist=True),
    )
    _step(
        "stack",
        "Stack reparieren",
        lambda: __import__(
            "analytics.stack_integrity", fromlist=["verify_or_repair"]
        ).verify_or_repair(root, auto_repair=True, persist=True),
    )
    _step(
        "linux_apply",
        "Linux-Potenzial (sicher)",
        lambda: __import__(
            "analytics.linux_potential", fromlist=["apply_linux_potential_safe"]
        ).apply_linux_potential_safe(root),
    )
    _step(
        "growth",
        "R3 Wachstum",
        lambda: __import__(
            "analytics.r3_local_growth", fromlist=["scan_local_growth"]
        ).scan_local_growth(
            root,
            persist=True,
            force=True,
            fast=bool(_load_json(root / "evidence/stack_integrity_latest.json").get("stack_ok")),
        ),
    )
    _step(
        "series",
        "Serienreife",
        lambda: __import__(
            "analytics.series_readiness", fromlist=["scan_series_readiness"]
        ).scan_series_readiness(root, persist=True, force=True, fast=True),
    )
    _step(
        "audit",
        "Systemaudit",
        lambda: __import__(
            "analytics.system_audit", fromlist=["run_system_audit"]
        ).run_system_audit(root, persist=True, live_stack=False, run_tests=False),
    )

    autostart = _autostart_ok()
    series = _load_json(root / "evidence/series_readiness_latest.json")
    audit = _load_json(root / "evidence/system_audit_latest.json")
    ok_n = sum(1 for s in steps if s.get("ok"))

    pending: Dict[str, Any] = {
        "schema_version": 1,
        "scheduled_at_utc": _utc_now(),
        "hostname": platform.node(),
        "pid": os.getpid(),
        "steps_ok": ok_n,
        "steps_total": len(steps),
        "series_ready": bool(series.get("series_ready")),
        "audit_ok": bool(audit.get("audit_ok")),
        "autostart": autostart,
        "headline_de": "Neustart geplant — Post-Boot: Hub, Stack, Audit",
        "post_boot_de": [
            "linux_boot_services.sh (NVMe, Hub, Symlinks)",
            "r3_session_autostart.sh (Login: repair_stack)",
            "reboot_apply complete_after_reboot",
        ],
    }
    atomic_write_json(root / _PENDING_REL, pending)

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok_n == len(steps),
        "steps": steps,
        "pending_path": str(_PENDING_REL).replace("\\", "/"),
        "series_ready": series.get("series_ready"),
        "audit_ok": audit.get("audit_ok"),
        "autostart": autostart,
        "headline_de": (
            f"Vorbereitung OK — {ok_n}/{len(steps)} Schritte · Serienreife={'ja' if series.get('series_ready') else 'nein'}"
        ),
        "next_de": "AA_OPERATOR_APPROVE_D=1 bash tools/reboot_full_apply.sh --reboot",
    }


def complete_after_reboot(root: Path) -> Dict[str, Any]:
    """Nach Login/Boot — Pending abarbeiten, Stack + Audit verifizieren."""
    root = Path(root)
    pending = _load_json(root / _PENDING_REL)
    if not pending.get("scheduled_at_utc"):
        return {"ok": True, "skipped": True, "headline_de": "Kein ausstehender Neustart-Apply"}

    steps: List[Dict[str, Any]] = []

    def _step(step_id: str, label_de: str, fn) -> None:
        try:
            result = fn()
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else bool(result)
            steps.append({"id": step_id, "label_de": label_de, "ok": ok, "detail": result})
        except Exception as exc:
            steps.append({"id": step_id, "label_de": label_de, "ok": False, "error_de": str(exc)[:160]})

    _step(
        "nvme_symlinks",
        "NVMe-Symlinks",
        lambda: {
            "ok": True,
            **__import__(
                "execution.linux_nvme_storage", fromlist=["repair_migrated_symlinks"]
            ).repair_migrated_symlinks(root),
        },
    )
    _step(
        "hub",
        "Hub",
        lambda: {
            "ok": True,
            "port": __import__("analytics.hub_runtime", fromlist=["ensure_running"]).ensure_running(root),
        },
    )
    _step(
        "stack",
        "Stack",
        lambda: __import__(
            "analytics.stack_integrity", fromlist=["verify_or_repair"]
        ).verify_or_repair(root, auto_repair=True, persist=True),
    )
    _step(
        "r3_align",
        "R3 Abgleich",
        lambda: __import__(
            "analytics.r3_runtime_upgrade", fromlist=["align_r3_surface"]
        ).align_r3_surface(root, scan_upgrades=True, warm_cache=True, sync_flow=False, persist=True),
    )
    _step(
        "audit",
        "Systemaudit",
        lambda: __import__(
            "analytics.system_audit", fromlist=["run_system_audit"]
        ).run_system_audit(root, persist=True, live_stack=True, run_tests=False),
    )

    audit = _load_json(root / "evidence/system_audit_latest.json")
    series = _load_json(root / "evidence/series_readiness_latest.json")
    ok_n = sum(1 for s in steps if s.get("ok"))

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "completed_at_utc": _utc_now(),
        "ok": ok_n == len(steps) and bool(audit.get("audit_ok")),
        "steps": steps,
        "pending_scheduled_at_utc": pending.get("scheduled_at_utc"),
        "audit_ok": audit.get("audit_ok"),
        "series_ready": series.get("series_ready"),
        "headline_de": str(audit.get("headline_de") or "Post-Boot Apply abgeschlossen"),
        "next_de": str(audit.get("next_de") or "http://127.0.0.1:17890/r3"),
    }
    atomic_write_json(root / _COMPLETE_REL, doc)
    try:
        (root / _PENDING_REL).unlink(missing_ok=True)
    except OSError:
        pass
    return doc


def reboot_pending(root: Path) -> bool:
    return (Path(root) / _PENDING_REL).is_file()
