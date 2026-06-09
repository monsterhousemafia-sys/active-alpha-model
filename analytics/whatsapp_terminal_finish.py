"""Terminal-Aufgabe WhatsApp-Spread sauber beenden."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/whatsapp_terminal_finish_latest.json")


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


def _stop_systemd_units() -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "list-units", "aa-whatsapp-*", "--no-legend", "--plain"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        names = [line.split()[0] for line in (proc.stdout or "").splitlines() if line.strip()]
        for name in names:
            stop = subprocess.run(
                ["systemctl", "--user", "stop", name],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            steps.append({"unit": name, "ok": stop.returncode == 0})
    except (OSError, subprocess.TimeoutExpired) as exc:
        steps.append({"ok": False, "detail_de": str(exc)[:120]})
    if not steps:
        steps.append({"ok": True, "detail_de": "keine aa-whatsapp-* Units aktiv"})
    return steps


def finish_terminal_task(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    spread = _load_json(root / "evidence/whatsapp_spread_latest.json")
    auto = _load_json(root / "evidence/whatsapp_auto_send_latest.json")
    cfg_path = root / "control/whatsapp_spread.json"
    cfg = _load_json(cfg_path)
    cfg["auto_send_mode"] = "manual"
    cfg["terminal_task"] = {
        "status": "beendet",
        "finished_at_utc": _utc_now(),
        "send_ok": bool(spread.get("send_ok")),
        "prepare_ok": bool(spread.get("prepare_ok")),
    }
    if persist:
        atomic_write_json(cfg_path, cfg)

    doc = {
        "schema_version": 1,
        "ok": True,
        "status": "beendet",
        "headline_de": "Terminal-Aufgabe beendet",
        "summary_de": _summary(spread),
        "send_ok": spread.get("send_ok"),
        "prepare_ok": spread.get("prepare_ok"),
        "delivery_mode": spread.get("delivery_mode"),
        "phone_e164": spread.get("phone_e164"),
        "join_url": _join_from_spread(spread),
        "zip_path": spread.get("zip_path"),
        "auto_send_mode_now": "manual",
        "stopped_units": _stop_systemd_units(),
        "last_auto_send": auto.get("detail_de"),
        "next_de": [
            "Spread-Infrastruktur bleibt aktiv (Join-Link, ZIP, Texte)",
            "Manuell senden: wa.me-Link oder erneut `whatsapp durch` nach install",
            "Vollauto später: bash tools/whatsapp_terminal_all.sh install && send",
        ],
        "updated_at_utc": _utc_now(),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _join_from_spread(spread: Dict[str, Any]) -> str:
    for step in spread.get("steps") or []:
        if step.get("kind") == "join_check":
            return str(step.get("join_url") or "")
    return ""


def _summary(spread: Dict[str, Any]) -> str:
    if spread.get("send_ok"):
        return "Spread automatisch gesendet — Terminal-Aufgabe erledigt"
    if spread.get("prepare_ok"):
        return "Spread vorbereitet (Chat/ZIP) — Senden manuell offen; Terminal beendet Auto-Versuche"
    return "Terminal beendet — letzter Spread-Lauf unvollständig"
