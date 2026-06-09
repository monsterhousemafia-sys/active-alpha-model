"""Desktop-Update — Phase B auf dem echten Schreibtisch (nicht nur Hub-API)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_EVIDENCE_REL = Path("evidence/r3_desktop_update_latest.json")
_DESKTOP_SHELL_PATH = "/desktop"
_DESKTOP_SHELL_PATH_LEGACY = "/#r3-desktop-shell"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def desktop_hub_path(root: Path) -> str:
    """Primäre R3-URL für Sitzung — Login oder Desktop (Phase B)."""
    root = Path(root)
    try:
        from analytics.r3_step_b import is_phase_b_active

        if is_phase_b_active(root):
            from analytics.r3_session_manager import resolve_hub_entry_path

            return resolve_hub_entry_path(root)
    except Exception:
        pass
    try:
        from analytics.r3_os_supremacy import load_supremacy

        cfg = load_supremacy(root)
        sess = cfg.get("session") or {}
        return str(sess.get("hub_path_kernel_ok") or sess.get("hub_path_fallback") or "/")
    except Exception:
        return "/"


def run_desktop_update_action(root: Path, *, launch_ui: bool = True) -> Dict[str, Any]:
    """
    Vollständige Desktop-Aktualisierung:
    Supremacy · Autostart · Hub · Phase-B-Evidence · R3-Vollbild öffnen.
    """
    root = Path(root).resolve()
    steps: List[Dict[str, Any]] = []
    errors: List[str] = []

    def _step(sid: str, label_de: str, fn) -> Dict[str, Any]:
        try:
            out = fn()
            row = {"id": sid, "label_de": label_de, "ok": bool(out.get("ok", True)), "detail": out}
            steps.append(row)
            if not row["ok"]:
                errors.append(label_de)
            return out
        except Exception as exc:
            row = {"id": sid, "label_de": label_de, "ok": False, "error_de": str(exc)[:200]}
            steps.append(row)
            errors.append(label_de)
            return row

    _step(
        "supremacy",
        "R3 Supremacy (GNOME zurücknehmen)",
        lambda: __import__("analytics.r3_os_supremacy", fromlist=["install_r3_supremacy"]).install_r3_supremacy(root),
    )
    _step(
        "desktop_os",
        "Desktop-Einträge & Autostart",
        lambda: __import__("analytics.r3_desktop_os", fromlist=["install_desktop_os"]).install_desktop_os(root),
    )

    def _hub() -> Dict[str, Any]:
        from tools.preview_hub import ensure_hub_running

        port = int(ensure_hub_running(root, port=17890, restart=True))
        return {"ok": True, "port": port, "url": f"http://127.0.0.1:{port}{desktop_hub_path(root)}"}

    hub_out = _step("hub", "Preview-Hub neu starten", _hub)
    hub_port = int(hub_out.get("port") or 17890)

    def _phase_b() -> Dict[str, Any]:
        from analytics.r3_step_b import evaluate_step_b, is_phase_b_active

        doc = evaluate_step_b(root, persist=True)
        return {"ok": is_phase_b_active(root), "headline_de": doc.get("headline_de"), "percent": doc.get("step_b_percent")}

    phase_doc = _step("phase_b", "Phase-B-Stand schreiben", _phase_b)

    def _h1() -> Dict[str, Any]:
        from analytics.h1_migration_guard import ensure_h1_migration_healthy

        return ensure_h1_migration_healthy(root, auto_fix=True)

    _step("h1_guard", "H1-Migration stabil", _h1)

    launch_doc: Dict[str, Any] = {"ok": False, "skipped": True}
    if launch_ui and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        path = desktop_hub_path(root)

        def _launch() -> Dict[str, Any]:
            from analytics.r3_local_cockpit import launch_session_cockpit

            return launch_session_cockpit(
                root,
                hub_path=path,
                port=hub_port,
                fullscreen=True,
                block=False,
            )

        launch_doc = _step("launch", "R3 Desktop Vollbild", _launch)
    else:
        steps.append(
            {
                "id": "launch",
                "label_de": "R3 Desktop Vollbild",
                "ok": False,
                "error_de": "Keine grafische Sitzung — nur Hub/Autostart aktualisiert",
            }
        )

    notified = False
    try:
        from analytics.operator_visibility import notify_desktop_if_available

        title = "R3 — Phase B Desktop-Update"
        body = str(phase_doc.get("headline_de") or "Desktop aktualisiert")[:180]
        notified = notify_desktop_if_available(title, body)
    except Exception:
        pass

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "ok": not errors,
        "updated_at_utc": _utc_now(),
        "phase": "B",
        "desktop_hub_path": desktop_hub_path(root),
        "headline_de": (
            f"Desktop-Update OK — Phase B · {phase_doc.get('percent', '?')}%"
            if not errors
            else f"Desktop-Update teilweise — Fehler: {', '.join(errors)}"
        ),
        "steps": steps,
        "launch": launch_doc.get("detail") or launch_doc,
        "notify_desktop": notified,
        "next_de": "R3 sollte im Vollbild erscheinen. Falls nicht: bash tools/r3_cockpit.sh",
    }
    path = root / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc
