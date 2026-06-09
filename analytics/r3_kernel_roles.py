"""R3-Kern vs. Cursor — klare Rollentrennung für UI und KI-Kontext."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_ROLES_REL = Path("control/r3_kernel_roles.json")
_EVIDENCE_REL = Path("evidence/r3_kernel_roles_latest.json")


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


def load_kernel_roles(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _ROLES_REL) or {
        "r3_kernel_de": {
            "title": "R3 Kern",
            "definition_de": "Ollama + Hub + Evidence",
        },
        "cursor_de": {
            "title": "Cursor",
            "role_de": "Werkzeug zum Bauen — wie eine IDE",
            "not_kernel_de": "Nicht der Kernel",
        },
    }


def _hub_healthy(root: Path) -> bool:
    try:
        from analytics.launch_progress_board import _hub_healthy

        return bool(_hub_healthy(root))
    except Exception:
        return False


def _evidence_ok(root: Path) -> bool:
    project = Path(root)
    markers = (
        project / "evidence/r3_dev_trail_latest.json",
        project / "evidence/r3_continuity_latest.json",
        Path.home() / ".local/share/r3-os/conversation/continuity_manifest.json",
    )
    return any(p.is_file() for p in markers)


def _ollama_ready(root: Path) -> Dict[str, Any]:
    try:
        from analytics.local_llm_bridge import health_report

        return health_report(root)
    except Exception as exc:
        return {"ready": False, "detail_de": str(exc)[:120]}


def cursor_build_session_active(cfg: Dict[str, Any] | None = None) -> bool:
    cfg = cfg or {}
    env = str(cfg.get("operator_channel_env") or "AA_OPERATOR_CHANNEL")
    val = str(cfg.get("operator_channel_value") or "conversational").strip().lower()
    return os.environ.get(env, "").strip().lower() == val


def build_kernel_roles_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_kernel_roles(root)
    kernel_cfg = cfg.get("r3_kernel_de") or {}
    cursor_cfg = cfg.get("cursor_de") or {}
    ollama = _ollama_ready(root)
    hub_ok = _hub_healthy(root)
    evidence_ok = _evidence_ok(root)
    cursor_active = cursor_build_session_active(cfg)

    build_ok = False
    try:
        from analytics.r3_build_kernel import build_kernel_status

        build_ok = bool(build_kernel_status(root).get("ollama_ready"))
    except Exception:
        build_ok = bool(ollama.get("ready"))

    components: List[Dict[str, Any]] = []
    for comp in kernel_cfg.get("components") or []:
        cid = str(comp.get("id") or "")
        ok = {
            "build_kernel": build_ok,
            "ollama": bool(ollama.get("ready")),
            "hub": hub_ok,
            "evidence": evidence_ok,
        }.get(cid, False)
        components.append(
            {
                "id": cid,
                "label_de": comp.get("label_de"),
                "role_de": comp.get("role_de"),
                "ok": ok,
            }
        )

    kernel_ok = all(c.get("ok") for c in components) if components else hub_ok

    doc = {
        "schema_version": 1,
        "checked_at_utc": _utc_now(),
        "r3_kernel": {
            "title_de": kernel_cfg.get("title", "R3 Kern"),
            "definition_de": kernel_cfg.get("definition_de"),
            "not_part_of_kernel_de": kernel_cfg.get("not_kernel_de"),
            "components": components,
            "ok": kernel_ok,
            "headline_de": "R3 Kern — Bau-Kernel + Hub + Evidence",
        },
        "cursor": {
            "title_de": cursor_cfg.get("title", "Cursor"),
            "role_de": cursor_cfg.get("role_de"),
            "not_kernel_de": cursor_cfg.get("not_kernel_de"),
            "active": cursor_active,
            "status_de": (
                cursor_cfg.get("when_active_de")
                if cursor_active
                else cursor_cfg.get("when_inactive_de")
            ),
            "headline_de": (
                "Cursor — Bau-Werkzeug (IDE), nicht der R3-Kern"
                if cursor_active
                else "Cursor — optional; R3-Kern läuft lokal"
            ),
        },
        "separation_de": (
            "Cursor (Legacy) + Bau-Kernel parallel — /bau startet den echten Entwicklungs-Kernel."
            if cursor_active
            else "Bau-Kernel ist der Kernel: /bau <Aufgabe> — Agent wie Cursor, lokal über Ollama."
        ),
        "ok": kernel_ok,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def roles_context_de(root: Path, *, max_chars: int = 2200) -> str:
    status = build_kernel_roles_status(root)
    kernel = status.get("r3_kernel") or {}
    cursor = status.get("cursor") or {}
    lines = [
        f"## {kernel.get('title_de')}",
        str(kernel.get("definition_de") or ""),
        str(kernel.get("not_part_of_kernel_de") or ""),
        "",
        "Komponenten:",
    ]
    for comp in kernel.get("components") or []:
        mark = "ok" if comp.get("ok") else "—"
        lines.append(f"- {comp.get('label_de')} ({mark}): {comp.get('role_de')}")
    lines.extend(
        [
            "",
            f"## {cursor.get('title_de')}",
            str(cursor.get("role_de") or ""),
            str(cursor.get("not_kernel_de") or ""),
            str(cursor.get("status_de") or ""),
            "",
            str(status.get("separation_de") or ""),
        ]
    )
    return "\n".join(lines)[:max_chars]


def render_roles_section(status: Dict[str, Any]) -> str:
    import html

    esc = lambda t: html.escape(str(t or ""), quote=True)
    if not status:
        return ""
    kernel = status.get("r3_kernel") or {}
    cursor = status.get("cursor") or {}
    comps_html = ""
    for comp in kernel.get("components") or []:
        ok = comp.get("ok")
        cls = "kr-ok" if ok else "kr-warn"
        mark = "●" if ok else "○"
        comps_html += (
            f'<div class="kr-comp {cls}">'
            f'<span class="kr-mark">{mark}</span>'
            f'<div><strong>{esc(comp.get("label_de"))}</strong>'
            f'<p>{esc(comp.get("role_de"))}</p></div></div>'
        )
    cursor_cls = "kr-cursor-active" if cursor.get("active") else "kr-cursor-idle"
    return f"""
<div class="kernel-roles" id="kernel-roles" aria-label="R3 Kern und Cursor">
  <div class="kr-col kr-kernel">
    <div class="kr-eyebrow">{esc(kernel.get("title_de"))}</div>
    <p class="kr-def">{esc(kernel.get("definition_de"))}</p>
    <div class="kr-comps">{comps_html}</div>
  </div>
  <div class="kr-col kr-cursor {cursor_cls}">
    <div class="kr-eyebrow">{esc(cursor.get("title_de"))}</div>
    <p class="kr-role">{esc(cursor.get("role_de"))}</p>
    <p class="kr-not">{esc(cursor.get("not_kernel_de"))}</p>
    <p class="kr-status">{esc(cursor.get("status_de"))}</p>
  </div>
</div>"""
