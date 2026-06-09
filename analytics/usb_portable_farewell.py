"""USB-Klon verabschieden — finaler Sync, Evidence, Autostart aus."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/usb_portable_farewell_latest.json")
_MANIFEST = Path("control/usb_deploy_manifest.json")
_SEAL = Path("evidence/usb_portable_seal_latest.json")


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


def _disable_usb_autostart_timer() -> Dict[str, Any]:
    try:
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", "active-alpha-usb-autostart.timer"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        active = subprocess.run(
            ["systemctl", "--user", "is-active", "active-alpha-usb-autostart.timer"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return {
            "ok": active.stdout.strip() != "active",
            "timer_state": active.stdout.strip() or "inactive",
            "detail_de": "USB-Autostart-Timer gestoppt — Quell-PC beobachtet Stick nicht mehr",
        }
    except Exception as exc:
        return {"ok": False, "detail_de": str(exc)[:120]}


def _pause_usb_autostart_policy(root: Path) -> None:
    path = root / "control/usb_portable_autostart.json"
    pol = _load_json(path)
    if not pol:
        return
    pol["enabled"] = False
    pol["farewell_at_utc"] = _utc_now()
    pol["note_de"] = "Verabschiedet — kein auto install-local mehr auf diesem Quell-PC."
    atomic_write_json(path, pol)


def farewell_usb_clone(
    root: Path,
    *,
    usb_mount: Optional[str] = None,
    usb_project: Optional[str] = None,
    farewell_by_de: str = "Operator",
    sync_before: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Verabschiedet den USB-Klon — Evidence, Manifest, Brief auf Stick."""
    root = Path(root).resolve()
    steps: List[Dict[str, Any]] = []

    if usb_mount is None:
        usb_mount = "/run/media/machinax7/USB Stick"
    if usb_project is None:
        usb_project = str(Path(usb_mount) / "active_alpha_model")

    usb_path = Path(usb_project)
    seal = _load_json(root / _SEAL)
    manifest = _load_json(usb_path / _MANIFEST) if usb_path.is_dir() else _load_json(root / _MANIFEST)

    if sync_before and usb_path.is_dir() and (root / "tools/usb_full_project_deploy.sh").is_file():
        try:
            proc = subprocess.run(
                ["bash", str(root / "tools/usb_full_project_deploy.sh"), str(usb_mount)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=7200,
                check=False,
            )
            steps.append(
                {
                    "step": "final_deploy_sync",
                    "ok": proc.returncode == 0,
                    "detail_de": (proc.stdout or proc.stderr or "")[-200:],
                }
            )
        except Exception as exc:
            steps.append({"step": "final_deploy_sync", "ok": False, "detail_de": str(exc)[:120]})
    elif not usb_path.is_dir():
        steps.append(
            {
                "step": "final_deploy_sync",
                "ok": True,
                "skipped": True,
                "detail_de": f"USB nicht eingehängt ({usb_project})",
            }
        )

    timer = _disable_usb_autostart_timer()
    steps.append({"step": "disable_usb_timer", **timer})
    _pause_usb_autostart_policy(root)
    steps.append(
        {
            "step": "pause_autostart_policy",
            "ok": True,
            "detail_de": "control/usb_portable_autostart.json → enabled=false",
        }
    )

    farewell_note = (
        "Active Alpha Model — Verabschiedung des USB-Klons\n"
        "==================================================\n"
        f"Verabschiedet: {_utc_now()}\n"
        f"Quelle: {root}\n"
        f"Segnung: {seal.get('status') or '—'} ({seal.get('blessed_at_utc') or '—'})\n"
        "\n"
        "Auf neuem PC / nach Stecken:\n"
        "  cd active_alpha_model\n"
        "  ./USB_WEITERARBEITEN.sh --full-setup\n"
        "\n"
        "Governance bleibt: kein Auto-Execute, R3-Bestätigung für Orders.\n"
        "T212-Keys auf neuem PC neu einrichten.\n"
        "\n"
        "Auf Wiedersehen — der Klon trägt alles Nötige mit.\n"
    )

    if usb_path.is_dir():
        try:
            (Path(usb_mount) / "VERABSCHIEDUNG_ACTIVE_ALPHA.txt").write_text(
                farewell_note, encoding="utf-8"
            )
            m = _load_json(usb_path / _MANIFEST)
            m["farewell"] = True
            m["farewell_at_utc"] = _utc_now()
            m["farewell_by_de"] = farewell_by_de
            m["farewell_headline_de"] = "USB-Klon verabschiedet — bereit für anderen Rechner"
            m["blessed"] = seal.get("blessed", m.get("blessed"))
            atomic_write_json(usb_path / _MANIFEST, m)
            (usb_path / "control/usb_portable_farewell.json").parent.mkdir(parents=True, exist_ok=True)
            steps.append({"step": "usb_farewell_brief", "ok": True, "detail_de": "VERABSCHIEDUNG_ACTIVE_ALPHA.txt"})
        except OSError as exc:
            steps.append({"step": "usb_farewell_brief", "ok": False, "detail_de": str(exc)[:120]})
        try:
            subprocess.run(["sync"], timeout=60, check=False)
            steps.append({"step": "sync", "ok": True})
        except Exception:
            steps.append({"step": "sync", "ok": False})

    ok = all(s.get("ok", True) or s.get("skipped") for s in steps)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "status": "FAREWELL" if ok else "FAREWELL_PARTIAL",
        "ok": ok,
        "headline_de": "USB-Klon verabschiedet — Stick kann sicher entfernt werden"
        if ok
        else "Verabschiedung mit Hinweisen — Stick prüfen",
        "farewell_at_utc": _utc_now(),
        "farewell_by_de": farewell_by_de,
        "source_root": str(root),
        "usb_project": usb_project,
        "usb_mounted": usb_path.is_dir(),
        "seal_status": seal.get("status"),
        "manifest_deployed_at_utc": manifest.get("deployed_at_utc"),
        "steps": steps,
        "next_de": "Stick im Dateimanager auswerfen, dann physisch abziehen.",
        "on_new_pc_de": "./USB_WEITERARBEITEN.sh --full-setup",
    }

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
