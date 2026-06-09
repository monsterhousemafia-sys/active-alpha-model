"""Desktop-Migration — Alpha Model KI lokal als Sprache, Werkstatt optional."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_desktop_migration_latest.json")
_MARKER_REL = Path(".local/share/r3-os/desktop_local_primary.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _marker_path() -> Path:
    return Path.home() / _MARKER_REL


def is_desktop_cursor_primary(root: Path | None = None) -> bool:
    """True nur wenn Legacy-Cursor noch als primärer Kanal konfiguriert ist."""
    root = Path(root or Path(__file__).resolve().parents[1])
    try:
        from analytics.alpha_model_interface_kernel import load_foundation

        return str(load_foundation(root).get("primary_interface") or "") == "cursor_chat"
    except Exception:
        return False


def write_local_primary_policy(root: Path) -> Dict[str, Any]:
    """Foundation + Rollen — R3 KI lokal primär, Cursor IDE optional."""
    root = Path(root).resolve()
    foundation = {
        "schema_version": 2,
        "status": "AUTHORITATIVE",
        "approved_by": "user",
        "approved_at_utc": _utc_now(),
        "primary_interface": "r3_ki",
        "primary_label_de": "Alpha Model KI — lokaler Hauptkanal (Cockpit :17890 + Ollama)",
        "workshop_surface": "alpha_model_workshop",
        "workshop_label_de": "Alpha Model — Werkstatt",
        "workshop_interface": "ide_optional",
        "fallback_interface": "ollama_local",
        "fallback_label_de": "Ollama — lokales Modell (active-alpha-chat)",
        "succession_rule_de": (
            "Hauptkanal ist Alpha Model KI: active-alpha-chat, Cockpit :17890/desktop, ai_kernel. "
            "Werkstatt ist optional."
        ),
        "forbidden_de": [
            "Cloud-Composer als einziger Hauptkanal",
            "Linux-Hardware-Kernel ersetzen",
            "Externe Timer ohne Operator-Mandat",
            "Paralleler IDE-Klon als Steuerungsschicht",
        ],
    }
    atomic_write_json(root / "control/alpha_model_interface.json", foundation)

    roles = {
        "schema_version": 1,
        "r3_kernel_de": {
            "title": "R3 Kern",
            "definition_de": "Hub + Evidence + Ollama auf dem Desktop — Sprache lokal über R3 KI.",
            "components": [
                {
                    "id": "hub",
                    "label_de": "Hub",
                    "role_de": "Cockpit :17890/desktop — System-Oberfläche",
                },
                {
                    "id": "evidence",
                    "label_de": "Evidence",
                    "role_de": "Wahrheit, Spur, Läufe im Arbeitsbaum",
                },
                {
                    "id": "build_kernel",
                    "label_de": "Bau-Kernel",
                    "role_de": "/bau und /beitrag — Umsetzung mit Tests",
                },
                {
                    "id": "ollama",
                    "label_de": "Ollama",
                    "role_de": "Lokales Modell — Hauptkanal via active-alpha-chat",
                },
            ],
            "not_kernel_de": "R3 KI ist der Sprachkanal — Cursor IDE optional.",
        },
        "cursor_de": {
            "title": "Alpha Model — Werkstatt",
            "role_de": "Optionale Entwicklungsoberfläche — Wachstum im Workspace.",
            "not_kernel_de": "Werkstatt ersetzt nicht den Alpha Model Kern.",
            "when_active_de": "Optional aktiv — Entwicklung & Wachstum.",
            "when_inactive_de": "Nicht nötig — Alpha Model KI lokal ist Hauptkanal.",
        },
        "operator_channel_env": "AA_OPERATOR_CHANNEL",
        "operator_channel_value": "conversational",
    }
    atomic_write_json(root / "control/r3_kernel_roles.json", roles)

    llm_path = root / "control/local_llm.json"
    llm: Dict[str, Any] = {}
    if llm_path.is_file():
        try:
            llm = json.loads(llm_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            llm = {}
    llm.update(
        {
            "chat_mode": "primary",
            "note_de": "Ollama ist der lokale Hauptkanal — active-alpha-chat und Cockpit :17890.",
        }
    )
    atomic_write_json(llm_path, llm)

    ki_gui_path = root / "control/r3_ki_gui.json"
    ki_gui: Dict[str, Any] = {}
    if ki_gui_path.is_file():
        try:
            ki_gui = json.loads(ki_gui_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            ki_gui = {}
    ki_gui.update(
        {
            "replaces_de": "Cursor-Pflichtkanal — R3 KI lokal ist Hauptsprache; Cockpit = Chat + System",
            "independence_de": "Cockpit und active-alpha-chat laufen lokal — kein Cursor-Konto nötig",
            "model_home": "local_machine",
        }
    )
    atomic_write_json(ki_gui_path, ki_gui)

    unified_path = root / "control/r3_unified.json"
    unified: Dict[str, Any] = {}
    if unified_path.is_file():
        try:
            unified = json.loads(unified_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            unified = {}
    unified.update(
        {
            "headline_de": "Ein Werkzeug — Trading-ML, lokale KI, R3 Desktop",
            "tagline_de": "R3 KI lokal = Gespräch · Cockpit = System · Cursor IDE = optional",
            "default_pipeline": ["kombi", "prognose", "status_hint"],
        }
    )
    atomic_write_json(unified_path, unified)

    supremacy_path = root / "control/r3_os_supremacy.json"
    if supremacy_path.is_file():
        try:
            sup = json.loads(supremacy_path.read_text(encoding="utf-8"))
            sess = dict(sup.get("session") or {})
            sess["hub_path_kernel_ok"] = "/desktop"
            sess["hub_path_fallback"] = "/desktop"
            sup["session"] = sess
            atomic_write_json(supremacy_path, sup)
        except (json.JSONDecodeError, OSError):
            pass

    marker = {
        "schema_version": 1,
        "active": True,
        "migrated_at_utc": _utc_now(),
        "primary_interface": "r3_ki",
        "desktop_url": "http://127.0.0.1:17890/desktop",
        "headline_de": "Desktop-Migration — R3 KI lokal primär",
    }
    path = _marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        from analytics.alpha_model_interface_kernel import interface_stack_status

        interface_stack_status(root)
    except Exception:
        pass

    return {"ok": True, "foundation": foundation, "marker": marker}


def write_cursor_primary_policy(root: Path) -> Dict[str, Any]:
    """Legacy-Alias — schreibt lokale Primär-Policy."""
    return write_local_primary_policy(root)


def local_handoff_reply_de(root: Path) -> str:
    _ = root
    return (
        "Dein **Hauptkanal ist R3 KI lokal** — active-alpha-chat und Cockpit :17890.\n\n"
        "Freie Fragen und Steuerung:\n"
        "  active-alpha-chat  (Terminal)\n"
        "  http://127.0.0.1:17890/desktop\n\n"
        "Slash-Befehle im Cockpit:\n"
        "  /status · /geheimnis · /desktop · /join · /warnings · /learn\n\n"
        "Cursor IDE ist optional zum Code-Bauen — kein Konto-Gate für R3."
    )


def cursor_handoff_reply_de(root: Path) -> str:
    return local_handoff_reply_de(root)


def run_full_desktop_migration(root: Path, *, launch_ui: bool = True) -> Dict[str, Any]:
    """Policy + Desktop-Update + Evidence — vollständige Migration auf den Schreibtisch."""
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

    policy = _step("local_primary", "R3 KI lokal als Hauptsprache", lambda: write_local_primary_policy(root))

    def _desktop() -> Dict[str, Any]:
        from analytics.r3_desktop_update import run_desktop_update_action

        return run_desktop_update_action(root, launch_ui=launch_ui)

    desktop_doc = _step("desktop", "R3 Desktop Vollbild + Hub", _desktop)

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "ok": not errors,
        "migrated_at_utc": _utc_now(),
        "headline_de": (
            "Desktop-Migration abgeschlossen — R3 KI lokal primär"
            if not errors
            else f"Migration teilweise — Fehler: {', '.join(errors)}"
        ),
        "primary_interface": "r3_ki",
        "fallback_interface": "ollama_local",
        "desktop_url": "http://127.0.0.1:17890/desktop",
        "cursor_handoff_de": cursor_handoff_reply_de(root),
        "steps": steps,
        "policy": policy,
        "desktop_update": desktop_doc,
        "next_de": "Ab jetzt: active-alpha-chat oder Cockpit :17890. Werkstatt optional.",
    }
    path = root / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, doc)
    return doc
