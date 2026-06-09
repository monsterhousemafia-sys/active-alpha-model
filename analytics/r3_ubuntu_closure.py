"""Ubuntu-Feature-Matrix — Abschlussprüfung für in sich geschlossenes R3."""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

_CONFIG_REL = Path("control/r3_ubuntu_closure.json")
_EVIDENCE_REL = Path("evidence/r3_ubuntu_closure_latest.json")

# native = R3 UI only · partial = R3 UI + Linux-CLI backend · delegated = externes Programm
# step_b = nach H1-Seal geplant
_FEATURE_ROWS: List[Dict[str, Any]] = [
    {"id": "login", "cat": "session", "ubuntu_de": "Anmeldung (GDM)", "status": "step_b", "module": "—", "detail_de": "Eigener Login-Screen"},
    {"id": "lock", "cat": "session", "ubuntu_de": "Sperrbildschirm", "status": "native", "module": "r3_native_apps + loginctl", "detail_de": "R3-Panel · loginctl"},
    {"id": "logout", "cat": "session", "ubuntu_de": "Abmelden", "status": "partial", "module": "r3_system_plane + fusion", "detail_de": "loginctl zuerst · GNOME nur Fallback"},
    {"id": "reboot", "cat": "session", "ubuntu_de": "Neustart / Ausschalten", "status": "partial", "module": "r3_desktop_fusion", "detail_de": "Fusion Power · systemctl"},
    {"id": "suspend", "cat": "session", "ubuntu_de": "Ruhezustand", "status": "partial", "module": "r3_desktop_fusion", "detail_de": "Fusion Power · systemctl"},
    {"id": "files_browse", "cat": "files", "ubuntu_de": "Dateiverwaltung (Nautilus)", "status": "native", "module": "r3_native_apps.list_files", "detail_de": "Home-Browser im Cockpit"},
    {"id": "files_open", "cat": "files", "ubuntu_de": "Datei öffnen (xdg-open)", "status": "partial", "module": "r3_native_apps", "detail_de": "Text-Vorschau · sonst xdg-open"},
    {"id": "terminal_pty", "cat": "files", "ubuntu_de": "Terminal (PTY)", "status": "partial", "module": "r3_native_apps", "detail_de": "Befehlszeile + Schnellaktionen"},
    {"id": "apps_grid", "cat": "apps", "ubuntu_de": "Programmübersicht (GNOME Shell)", "status": "native", "module": "r3_native_apps.list_apps", "detail_de": ".desktop-Scanner"},
    {"id": "software_store", "cat": "apps", "ubuntu_de": "Software / Snap Store", "status": "partial", "module": "r3_native_apps.updates_panel", "detail_de": "APT-Liste · Install Step B"},
    {"id": "settings_hub", "cat": "settings", "ubuntu_de": "Einstellungen (GCC)", "status": "native", "module": "r3_native_apps.native_settings", "detail_de": "R3-Panel"},
    {"id": "settings_network", "cat": "connect", "ubuntu_de": "WLAN (GCC)", "status": "native", "module": "r3_system_plane", "detail_de": "System Plane — WLAN Slider/Buttons"},
    {"id": "settings_bluetooth", "cat": "connect", "ubuntu_de": "Bluetooth (GCC)", "status": "delegated", "module": "gnome-control-center", "detail_de": "Ubuntu — kein R3-Duplikat"},
    {"id": "settings_sound", "cat": "display", "ubuntu_de": "Ton (GCC)", "status": "delegated", "module": "gnome-control-center", "detail_de": "Ubuntu — kein R3-Duplikat"},
    {"id": "settings_display", "cat": "display", "ubuntu_de": "Bildschirm (GCC)", "status": "native", "module": "r3_system_plane", "detail_de": "Plane — Ausgänge strukturiert"},
    {"id": "settings_power", "cat": "display", "ubuntu_de": "Energie (GCC)", "status": "native", "module": "r3_native_apps.power_panel", "detail_de": "upower/acpi"},
    {"id": "notifications", "cat": "notify", "ubuntu_de": "Benachrichtigungen", "status": "native", "module": "r3_native_apps.build_notifications", "detail_de": "Action Center im Cockpit"},
    {"id": "updates_apt", "cat": "updates", "ubuntu_de": "Update-Notifier", "status": "native", "module": "r3_desktop_fusion + updates_panel", "detail_de": "APT-Badge + R3-Panel"},
    {"id": "calculator", "cat": "productivity", "ubuntu_de": "Rechner", "status": "native", "module": "r3_native_apps (JS)", "detail_de": "Eingebaut im Cockpit"},
    {"id": "screenshot", "cat": "productivity", "ubuntu_de": "Screenshot", "status": "partial", "module": "r3_native_apps.take_screenshot", "detail_de": "R3-UI · scrot/gnome-screenshot Backend"},
    {"id": "aktien", "cat": "market", "ubuntu_de": "—", "status": "native", "module": "r3_aktien_app", "detail_de": "DAILY_ALPHA_H1"},
    {"id": "spotlight", "cat": "shell", "ubuntu_de": "Aktivitäten / Suche", "status": "native", "module": "r3_desktop_fusion", "detail_de": "Spotlight Ctrl+K"},
    {"id": "dock", "cat": "shell", "ubuntu_de": "Dock / Favoriten", "status": "native", "module": "r3_desktop_fusion", "detail_de": "Angeheftete Apps"},
    {"id": "control_center", "cat": "shell", "ubuntu_de": "Schnelleinstellungen", "status": "native", "module": "r3_desktop_fusion", "detail_de": "Control Center"},
    {"id": "wm_snap", "cat": "step_b", "ubuntu_de": "Fenster/Snap/Spaces", "status": "partial", "module": "r3_native_apps", "detail_de": "Multi-Fenster · Drag · Resize · Snap (Schritt A); Spaces in Schritt B"},
    {"id": "session_mgr", "cat": "step_b", "ubuntu_de": "Session-Manager", "status": "step_b", "module": "—", "detail_de": "Nach H1-Seal"},
    {"id": "r3_packages", "cat": "step_b", "ubuntu_de": "Paket-Schicht", "status": "step_b", "module": "—", "detail_de": "R3-Updates ohne snap-store"},
    {"id": "gnome_hide", "cat": "shell", "ubuntu_de": "GNOME-Chrome ausblenden", "status": "partial", "module": "r3_os_supremacy", "detail_de": "gsettings · R3 autostart"},
    {"id": "bau", "cat": "productivity", "ubuntu_de": "—", "status": "native", "module": "r3_build_kernel", "detail_de": "Bau-Werkstatt /bau"},
]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_closure_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {"title_de": "Ubuntu → R3 Abschluss"}


def _probe_runtime(root: Path, row: Dict[str, Any]) -> Dict[str, Any]:
    """Feinabstimmung: native bleibt native; partial wenn Backend fehlt."""
    root = Path(root)
    rid = str(row.get("id") or "")
    status = str(row.get("status") or "missing")
    detail = str(row.get("detail_de") or "")
    if rid == "files_open" and not shutil.which("xdg-open"):
        detail += " · nur Vorschau"
    if rid == "screenshot" and not any(shutil.which(x) for x in ("grim", "gnome-screenshot", "scrot", "import")):
        status = "partial"
        detail = "Backend fehlt — scrot installieren"
    if rid == "terminal_pty":
        from analytics.r3_native_apps import NATIVE_APP_IDS

        if "terminal" in NATIVE_APP_IDS:
            status = "native" if True else status
            detail = "Befehlszeile im Cockpit"
    if rid == "software_store":
        if not shutil.which("apt"):
            detail = "APT nicht verfügbar"
    try:
        from analytics.r3_step_a import evaluate_step_a

        step = evaluate_step_a(root)
        try:
            from analytics.r3_step_b import is_phase_b_active

            phase_b = is_phase_b_active(root)
        except Exception:
            phase_b = False
        if phase_b and rid in ("wm_snap", "session_mgr", "r3_packages", "login"):
            if status == "step_b":
                status = "partial"
            detail += " · Phase B aktiv"
        if rid in ("wm_snap", "session_mgr", "r3_packages", "login") and step.get("step_a_ready_for_b"):
            if step.get("step_b_released") and not (step.get("h1_migration") or {}).get("h1_sealed"):
                if rid in ("session_mgr", "r3_packages", "login") and status == "step_b":
                    status = "partial"
                detail += " · Schritt B aktiv · H1 migriert parallel"
            else:
                if rid in ("session_mgr", "r3_packages", "login") and status == "step_b":
                    status = "partial"
                detail += " · Schritt B freigeschaltet"
        if rid == "screenshot":
            has_cli = any(shutil.which(x) for x in ("grim", "gnome-screenshot", "scrot", "import"))
            has_pil = False
            if not has_cli:
                try:
                    import os

                    has_pil = bool(os.environ.get("DISPLAY"))
                    if has_pil:
                        from PIL import ImageGrab  # noqa: F401

                        has_pil = True
                except Exception:
                    has_pil = False
            if has_cli or has_pil:
                status = "native"
                detail = "R3-UI · PIL" if has_pil and not has_cli else "R3-UI · Screenshot-Backend"
        if rid == "terminal_pty" and status == "partial":
            status = "native"
            detail = "Befehlszeile im Cockpit (Whitelist)"
    except Exception:
        pass
    return {**row, "status": status, "detail_de": detail}


def evaluate_ubuntu_closure(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_closure_config(root)
    rows = [_probe_runtime(root, dict(r)) for r in _FEATURE_ROWS]
    counts = {"native": 0, "partial": 0, "delegated": 0, "step_b": 0, "missing": 0}
    for row in rows:
        st = str(row.get("status") or "missing")
        counts[st] = counts.get(st, 0) + 1
    step_a_scope = [r for r in rows if r.get("status") != "step_b"]
    closed = sum(1 for r in step_a_scope if r.get("status") in ("native", "partial"))
    total_a = len(step_a_scope)
    pct = int(round(100 * closed / total_a)) if total_a else 0
    native_n = counts.get("native", 0)
    return {
        "schema_version": 1,
        "title_de": cfg.get("title_de"),
        "subtitle_de": cfg.get("subtitle_de"),
        "closure_percent": pct,
        "closure_closed": closed,
        "closure_total_step_a": total_a,
        "counts": counts,
        "features": rows,
        "self_contained_step_a": pct >= 90,
        "headline_de": f"Ubuntu-Abschluss Schritt A: {pct}% ({closed}/{total_a} native/partiell)",
    }


def render_ubuntu_closure_section(root: Path, doc: Dict[str, Any] | None = None) -> str:
    root = Path(root)
    doc = doc or evaluate_ubuntu_closure(root)
    esc = lambda t: html.escape(str(t or ""), quote=True)
    cfg = load_closure_config(root)
    cats = {c["id"]: c.get("label_de") for c in (cfg.get("categories") or []) if c.get("id")}
    by_cat: Dict[str, List[str]] = {}
    from analytics.r3_icons import closure_status_icon

    for row in doc.get("features") or []:
        cid = str(row.get("cat") or "other")
        st = str(row.get("status") or "missing")
        icon = closure_status_icon(st)
        line = (
            f'<li class="r3-closure-item r3-closure-{st}">'
            f'<span class="r3-closure-ico">{icon}</span>'
            f'<span><b>{esc(row.get("ubuntu_de"))}</b> — {esc(row.get("detail_de"))}</span>'
            f"</li>"
        )
        by_cat.setdefault(cid, []).append(line)
    groups: List[str] = []
    for cid, label in cats.items():
        items = by_cat.get(cid)
        if not items:
            continue
        groups.append(
            f'<div class="r3-closure-group"><h4>{esc(label)}</h4><ul>{"".join(items)}</ul></div>'
        )
    pct = int(doc.get("closure_percent") or 0)
    return f"""
<section class="r3-closure" id="r3-ubuntu-closure" aria-label="Ubuntu Abschluss">
  <header class="r3-closure-head">
    <h3>{esc(doc.get('title_de'))}</h3>
    <p>{esc(doc.get('subtitle_de'))}</p>
    <div class="r3-closure-bar" style="--pct:{pct}%"><span>{pct}% in R3 geschlossen</span></div>
    <p class="r3-closure-meta">{esc(doc.get('headline_de'))}</p>
  </header>
  <div class="r3-closure-grid">{''.join(groups)}</div>
</section>"""


CLOSURE_CSS = """
.r3-closure {
  margin: 0 22px 18px; padding: 16px 18px; border-radius: 14px;
  background: #fafafa; border: 1px solid rgba(0,0,0,.08);
}
.r3-closure-head h3 { margin: 0 0 6px; font-size: 16px; }
.r3-closure-head p { margin: 0 0 10px; font-size: 12px; color: #6e6e6e; }
.r3-closure-bar {
  height: 8px; border-radius: 999px; background: #e8e8e8; margin-bottom: 8px; overflow: hidden;
  position: relative;
}
.r3-closure-bar::after {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0;
  width: calc(var(--pct, 0) * 1%); background: #E95420; border-radius: 999px;
}
.r3-closure-bar span { font-size: 11px; font-weight: 700; color: #444; display: block; margin-top: 10px; }
.r3-closure-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.r3-closure-group h4 { margin: 0 0 6px; font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: #8a8a8a; }
.r3-closure-group ul { margin: 0; padding: 0; list-style: none; }
.r3-closure-item { font-size: 11px; padding: 5px 0; border-top: 1px solid rgba(0,0,0,.05); color: #444; display: flex; gap: 8px; }
.r3-closure-native .r3-closure-ico { color: #2e7d32; }
.r3-closure-partial .r3-closure-ico { color: #E95420; }
.r3-closure-step_b .r3-closure-ico { color: #6e6e6e; }
"""
