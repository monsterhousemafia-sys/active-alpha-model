"""R3 — Entwicklungsspur: Pfad, nächste Änderungen, zuletzt sichtbar."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CODEX_REL = Path("control/r3_os_codex.json")
_TRAIL_EVIDENCE_REL = Path("evidence/r3_dev_trail_latest.json")
_TRAIL_SHARE_REL = Path(".local/share/r3-os/dev_trail.json")


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


def resolve_project_root(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root).resolve()
    env = os.environ.get("AA_PROJECT_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


def load_codex(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CODEX_REL)
    return doc or {"mission_de": "Neues Betriebssystem — gemeinsam geschrieben."}


def _trail_paths(root: Path) -> Dict[str, str]:
    from analytics.r3_paths import r3_share_dir

    project = resolve_project_root(root)
    share = r3_share_dir()
    return {
        "project_root": str(project),
        "project_label_de": str(project.name),
        "r3_share": str(share),
        "evidence_dir": str(project / "evidence"),
        "control_dir": str(project / "control"),
        "venv_python": str(project / ".venv/bin/python3"),
    }


def _seed_recent() -> List[Dict[str, Any]]:
    now = _utc_now()
    return [
        {
            "at_utc": now,
            "title_de": "Zentrale R3-KI-Eingabe",
            "detail_de": "Ein Eingabefenster im Cockpit — Ollama lokal, frei von Cursor.",
            "status": "done",
        },
        {
            "at_utc": now,
            "title_de": "Entwicklungsspur + Pfadanzeige",
            "detail_de": "Arbeitsbaum und nächste Änderungen dauerhaft im Preview sichtbar.",
            "status": "active",
        },
        {
            "at_utc": now,
            "title_de": "Tunnel-Anzeige bereinigt",
            "detail_de": "Kein Tunnel-in-Tunnel mehr — König sieht Lokal · :17890.",
            "status": "done",
        },
        {
            "at_utc": now,
            "title_de": "Natives R3-Fenster",
            "detail_de": "r3-cockpit öffnet Qt lokal statt Browser.",
            "status": "done",
        },
        {
            "at_utc": now,
            "title_de": "Ubuntu-Hintergrund entfernt",
            "detail_de": "Einheitlicher R3-Hintergrund #0a0a0f.",
            "status": "done",
        },
    ]


def load_trail_state(root: Path) -> Dict[str, Any]:
    root = Path(root)
    share_path = Path.home() / _TRAIL_SHARE_REL
    for path in (share_path, root / _TRAIL_EVIDENCE_REL):
        doc = _load_json(path)
        if doc.get("entries") or doc.get("next_de"):
            return doc
    return {
        "schema_version": 1,
        "entries": _seed_recent(),
        "next_de": list(load_codex(root).get("default_next_de") or []),
    }


def save_trail_state(root: Path, doc: Dict[str, Any]) -> None:
    root = Path(root)
    doc = dict(doc)
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(root / _TRAIL_EVIDENCE_REL, doc)
    share_path = Path.home() / _TRAIL_SHARE_REL
    share_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(share_path, doc)


def record_dev_change(
    root: Path,
    *,
    title_de: str,
    detail_de: str = "",
    status: str = "active",
) -> Dict[str, Any]:
    """Eintrag in die sichtbare Entwicklungsspur."""
    root = Path(root)
    state = load_trail_state(root)
    entries: List[Dict[str, Any]] = list(state.get("entries") or [])
    entry = {
        "at_utc": _utc_now(),
        "title_de": str(title_de or "").strip()[:200],
        "detail_de": str(detail_de or "").strip()[:400],
        "status": str(status or "active"),
    }
    entries = [entry] + [e for e in entries if e.get("title_de") != entry["title_de"]]
    state["entries"] = entries[:24]
    save_trail_state(root, state)
    return entry


def set_next_changes(root: Path, items: List[str]) -> Dict[str, Any]:
    root = Path(root)
    state = load_trail_state(root)
    state["next_de"] = [str(x).strip()[:220] for x in items if str(x).strip()][:8]
    save_trail_state(root, state)
    return state


def build_dev_trail(root: Path) -> Dict[str, Any]:
    root = Path(root)
    codex = load_codex(root)
    paths = _trail_paths(root)
    state = load_trail_state(root)
    entries = list(state.get("entries") or [])
    next_items = list(state.get("next_de") or codex.get("default_next_de") or [])

    try:
        from analytics.r3_local_surface import collect_ki_next_steps

        ki = collect_ki_next_steps(root)
        nxt = str(ki.get("next_step_de") or "").strip()
        if nxt and nxt not in next_items:
            next_items = [nxt] + next_items
    except Exception:
        pass

    active = [e for e in entries if str(e.get("status") or "") == "active"]
    recent = [e for e in entries if str(e.get("status") or "") != "planned"][:6]

    continuity_de = ""
    roles_status: Dict[str, Any] = {}
    try:
        from analytics.r3_conversation_continuity import continuity_status

        cont = continuity_status(root)
        if cont.get("preserved"):
            continuity_de = "Gespräch lokal gesichert — Cursor nicht nötig"
        else:
            continuity_de = "Gespräch sichern: ai_kernel r3-preserve"
    except Exception:
        pass
    try:
        from analytics.r3_kernel_roles import build_kernel_roles_status

        roles_status = build_kernel_roles_status(root)
    except Exception:
        pass
    build_status: Dict[str, Any] = {}
    try:
        from analytics.r3_build_channel import build_channel_status

        build_status = build_channel_status(root)
    except Exception:
        pass

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "mission_de": codex.get("mission_de"),
        "continuity_de": continuity_de,
        "kernel_roles": roles_status,
        "build_channel": build_status,
        "paths": paths,
        "next_de": next_items[:6],
        "active_de": [str(e.get("title_de") or "") for e in active[:3]],
        "recent": recent,
        "labels": {
            "workspace": codex.get("workspace_label_de", "Arbeitsbaum"),
            "data": codex.get("data_label_de", "Sitzungsdaten"),
            "next": codex.get("next_label_de", "Als Nächstes"),
            "recent": codex.get("recent_label_de", "Zuletzt sichtbar geändert"),
        },
        "agent_note_de": codex.get("agent_note_de"),
    }


def render_dev_trail_section(trail: Dict[str, Any]) -> str:
    import html

    esc = lambda t: html.escape(str(t or ""), quote=True)
    if not trail:
        return ""
    # Kernel-Rollen / Bau-Kernel: intern für API, nicht im Cockpit (Operator nutzt Cursor direkt).
    roles_html = ""
    build_html = ""
    paths = trail.get("paths") or {}
    project = esc(paths.get("project_root"))
    share = esc(paths.get("r3_share"))
    next_items = trail.get("next_de") or []
    recent = trail.get("recent") or []
    next_html = "".join(f"<li>{esc(x)}</li>" for x in next_items[:5])
    recent_html = ""
    for item in recent[:5]:
        status = str(item.get("status") or "")
        badge = "aktiv" if status == "active" else "fertig" if status == "done" else status
        recent_html += (
            f'<div class="dt-item dt-{esc(status)}">'
            f'<span class="dt-badge">{esc(badge)}</span>'
            f'<div><strong>{esc(item.get("title_de"))}</strong>'
            f'<p>{esc(item.get("detail_de"))}</p></div></div>'
        )
    labels = trail.get("labels") or {}
    return f"""
<section class="dev-trail" id="dev-trail" aria-label="Entwicklungsspur">
  <div class="dt-head">
    <div>
      <div class="dt-eyebrow">Gemeinsame Entwicklung</div>
      <h2 class="dt-title">Neues Betriebssystem</h2>
      <p class="dt-mission">{esc(trail.get('mission_de'))}</p>
  <p class="dt-continuity">{esc(trail.get('continuity_de'))}</p>
    </div>
  </div>
  {roles_html}
  {build_html}
  <div class="dt-paths">
    <div class="dt-path">
      <span class="dt-path-k">{esc(labels.get('workspace'))}</span>
      <code class="dt-path-v" id="dt-project-root">{project}</code>
      <button type="button" class="dt-copy" data-copy="dt-project-root">Kopieren</button>
    </div>
    <div class="dt-path">
      <span class="dt-path-k">{esc(labels.get('data'))}</span>
      <code class="dt-path-v" id="dt-r3-share">{share}</code>
      <button type="button" class="dt-copy" data-copy="dt-r3-share">Kopieren</button>
    </div>
  </div>
  <div class="dt-grid">
    <div class="dt-col">
      <h3>{esc(labels.get('next'))}</h3>
      <ul class="dt-next" id="dt-next">{next_html}</ul>
    </div>
    <div class="dt-col">
      <h3>{esc(labels.get('recent'))}</h3>
      <div class="dt-recent" id="dt-recent">{recent_html}</div>
    </div>
  </div>
  <p class="dt-note">{esc(trail.get('agent_note_de'))}</p>
</section>"""
