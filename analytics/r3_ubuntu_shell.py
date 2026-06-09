"""R3 System — Desktop-Funktionen im Cockpit (eigenständige Oberfläche, keine Emoji-Kacheln)."""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from analytics.r3_desktop_fusion import (
    FUSION_CSS,
    FUSION_JS,
    build_fusion_status,
    render_fusion_chrome,
)
from analytics.r3_native_apps import NATIVE_APP_IDS, NATIVE_CSS, NATIVE_JS, render_notifications_panel
from analytics.r3_ubuntu_closure import CLOSURE_CSS, evaluate_ubuntu_closure, render_ubuntu_closure_section
from analytics.r3_icons import R3_ICON_CSS, shell_icon_svg
from analytics.r3_step_a import STEP_A_CSS, evaluate_step_a, render_step_a_progress
from analytics.r3_step_b import (
    STEP_B_CSS,
    evaluate_step_b,
    is_phase_b_active,
    render_step_b_progress,
)

_CONFIG_REL = Path("control/r3_ubuntu_shell.json")


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_ubuntu_shell(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL)
    if doc:
        return doc
    return {"section_title_de": "R3 System", "features": []}


def _feature_map(root: Path) -> Dict[str, Dict[str, Any]]:
    cfg = load_ubuntu_shell(root)
    out: Dict[str, Dict[str, Any]] = {}
    for row in cfg.get("features") or []:
        if isinstance(row, dict) and row.get("id"):
            out[str(row["id"])] = row
    return out


def _run_quiet(cmd: Sequence[str], *, timeout: float = 4.0) -> Optional[str]:
    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        text = (proc.stdout or proc.stderr or "").strip()
        return text or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _session_type() -> str:
    if os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland"
    if os.environ.get("DISPLAY"):
        return "X11"
    return "—"


def _wifi_summary() -> str:
    try:
        from analytics.r3_system_plane import get_network_state

        net = get_network_state()
        ssid = str(net.get("active_ssid") or "")
        if ssid and ssid != "—":
            return ssid
        return "Getrennt" if net.get("wifi_enabled") else "WLAN aus"
    except Exception:
        return "—"


def _expand_exec(root: Path, spec: Dict[str, Any]) -> List[str]:
    home = str(Path.home())
    raw = list(spec.get("exec") or [])
    out: List[str] = []
    for part in raw:
        out.append(str(part).replace("{home}", home).replace("{root}", str(root.resolve())))
    return out


def _resolve_launch_cmd(root: Path, spec: Dict[str, Any]) -> List[str]:
    cmd = _expand_exec(root, spec)
    if _command_available(cmd):
        return cmd
    fb = list(spec.get("fallback_exec") or [])
    if fb:
        cmd = _expand_exec(root, {"exec": fb})
        if _command_available(cmd):
            return cmd
    return cmd


def _command_available(cmd: Sequence[str]) -> bool:
    if not cmd:
        return False
    return shutil.which(str(cmd[0])) is not None


def _feature_available(root: Path, spec: Dict[str, Any]) -> bool:
    fid = str(spec.get("id") or "")
    if fid == "aktien":
        from analytics.r3_aktien_app import model_policy

        root_p = Path(root)
        launcher = root_p / "run_marktanalyse_linux.sh"
        return launcher.is_file() and bool(model_policy(root_p).get("ok"))
    if fid in NATIVE_APP_IDS:
        from analytics.r3_native_apps import native_apps_ready

        return native_apps_ready(Path(root))
    cmd = _resolve_launch_cmd(root, spec)
    return bool(cmd) and _command_available(cmd)


def _feature_available_fast(root: Path, spec: Dict[str, Any]) -> bool:
    fid = str(spec.get("id") or "")
    if fid == "aktien":
        return (Path(root) / "run_marktanalyse_linux.sh").is_file()
    if fid in NATIVE_APP_IDS:
        fb = list(spec.get("fallback_exec") or [])
        return bool(fb) and any(shutil.which(str(x)) for x in fb)
    cmd = _resolve_launch_cmd(root, spec)
    if cmd:
        return _command_available(cmd)
    return True


def build_shell_status(root: Path, *, fast: bool = False) -> Dict[str, Any]:
    """Live-Infos für R3 System (ohne Privilegien)."""
    root = Path(root)
    cfg = load_ubuntu_shell(root)
    supremacy: Dict[str, Any] = {}
    try:
        from analytics.r3_os_supremacy import supremacy_status

        supremacy = supremacy_status(root)
    except Exception:
        pass
    now = datetime.now().astimezone()
    features = []
    avail_fn = _feature_available_fast if fast else _feature_available
    for row in cfg.get("features") or []:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("id") or "")
        features.append(
            {
                "id": fid,
                "category": row.get("category"),
                "label_de": row.get("label_de"),
                "detail_de": row.get("detail_de"),
                "available": avail_fn(root, row),
            }
        )
    fusion = build_fusion_status(root)
    aktien: Dict[str, Any] = {}
    try:
        from analytics.r3_aktien_app import build_aktien_status

        aktien = build_aktien_status(root)
    except Exception:
        pass
    if fast:
        launch_doc: Dict[str, Any] = {}
        try:
            launch_doc = json.loads((root / "evidence/launch_progress_latest.json").read_text(encoding="utf-8"))
        except Exception:
            launch_doc = {}
        overall = int(launch_doc.get("overall_pct") or 0)
        step_a = {
            "step_a_percent": overall,
            "step_a_headline_de": str(launch_doc.get("headline_de") or "System bereit"),
        }
        step_b = (
            {
                "step_b_percent": overall,
                "step_b_headline_de": str(launch_doc.get("headline_de") or "Phase B"),
            }
            if is_phase_b_active(root)
            else {}
        )
        closure = {
            "closure_percent": overall,
            "headline_de": str(launch_doc.get("headline_de") or "Ubuntu-Abschluss"),
        }
    else:
        step_a = evaluate_step_a(root)
        step_b = evaluate_step_b(root) if is_phase_b_active(root) else {}
        closure = evaluate_ubuntu_closure(root)
    return {
        "schema_version": 3,
        "section_title_de": cfg.get("section_title_de"),
        "section_subtitle_de": cfg.get("section_subtitle_de"),
        "linux_mainline_de": cfg.get("linux_mainline_de"),
        "clock_de": now.strftime("%H:%M"),
        "date_de": now.strftime("%A, %d.%m.%Y"),
        "hostname": os.uname().nodename,
        "session_de": _session_type(),
        "wifi_de": _wifi_summary(),
        "home": str(Path.home()),
        "features": features,
        "r3_supremacy_active": bool(supremacy.get("active")),
        "r3_supremacy_headline_de": supremacy.get("headline_de"),
        **fusion,
        **aktien,
        **step_a,
        **({k: v for k, v in step_b.items() if k.startswith("step_b_") or k in ("phase", "phase_active", "headline_de", "h1_migration", "milestones")}),
        "step_b": step_b,
        "phase_b_active": is_phase_b_active(root),
        "ubuntu_closure": closure,
        "ubuntu_closure_pct": closure.get("closure_percent"),
    }


def launch_shell_feature(root: Path, feature_id: str) -> Dict[str, Any]:
    """Whitelist: nur konfigurierte Desktop-Funktionen starten."""
    root = Path(root)
    fid = str(feature_id or "").strip()
    if fid == "aktien":
        from analytics.r3_aktien_app import launch_aktien_app

        return launch_aktien_app(root)
    if fid in NATIVE_APP_IDS:
        from analytics.r3_native_apps import launch_native_app

        return launch_native_app(root, fid)
    spec = _feature_map(root).get(fid)
    if not spec:
        return {"ok": False, "error_de": f"Unbekannte Funktion: {fid}"}

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "error_de": "Keine grafische Sitzung — Start nur am Desktop."}

    cmd = _resolve_launch_cmd(root, spec)
    if not _command_available(cmd):
        return {"ok": False, "error_de": f"Programm nicht gefunden: {cmd[0] if cmd else '—'}"}

    env = os.environ.copy()
    env.setdefault("AA_PROJECT_ROOT", str(root.resolve()))
    try:
        subprocess.Popen(
            cmd,
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "ok": True,
            "feature_id": fid,
            "label_de": spec.get("label_de"),
            "message_de": f"{spec.get('label_de')} wird geöffnet.",
        }
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200]}


SHELL_CSS = CLOSURE_CSS + STEP_A_CSS + STEP_B_CSS + R3_ICON_CSS + """
.r3-desk {
  margin-bottom: 28px;
  padding: 0 !important;
  overflow: hidden;
  border: 1px solid rgba(0,0,0,.08);
  background: #fff;
}
.r3-desk-hero {
  display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
  gap: 16px; padding: 22px 22px 18px;
  border-bottom: 1px solid rgba(0,0,0,.08);
  background: #fafafa;
}
.r3-desk-brand { display: flex; align-items: center; gap: 14px; }
.r3-desk-mark {
  width: 48px; height: 48px; border-radius: 12px; flex-shrink: 0;
  background: #E95420;
  display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 15px;
  letter-spacing: -.02em; box-shadow: none;
}
.r3-desk-hero h2 { margin: 0 0 4px; font-size: 22px; letter-spacing: -.02em; color: #2e2e2e; }
.r3-desk-hero .subtitle { margin: 0; font-size: 14px; color: #6e6e6e; }
.r3-desk-status {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}
.r3-desk-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; padding: 7px 12px; border-radius: 999px;
  background: #f0f0f0; color: #5c5c5c; font-weight: 600;
  border: 1px solid rgba(0,0,0,.06);
}
.r3-desk-pill-ico { display: inline-flex; width: 14px; height: 14px; color: #8a8a8a; }
.r3-desk-pill-ico svg { width: 100%; height: 100%; }
.r3-desk-pill--accent {
  background: #ececec; color: #2e2e2e; border-color: rgba(0,0,0,.08);
}
.r3-desk-supremacy {
  margin: 0; padding: 12px 22px; font-size: 13px; font-weight: 600; line-height: 1.45;
  background: #f5f5f5; border-bottom: 1px solid rgba(0,0,0,.06); color: #4a4a4a;
}
.r3-desk-body { padding: 18px 22px 22px; background: #fff; }
.r3-desk-group { margin-bottom: 20px; }
.r3-desk-group:last-child { margin-bottom: 0; }
.r3-desk-group h3 {
  margin: 0 0 10px; font-size: 11px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: #8a8a8a;
}
.r3-desk-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 10px;
}
.r3-desk-tile {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 16px 10px 14px; min-height: 108px;
  border-radius: 14px; border: 1px solid rgba(0,0,0,.08);
  background: #fafafa;
  cursor: pointer; text-align: center; font-family: inherit; color: #2e2e2e;
  transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease, background .15s ease;
}
.r3-desk-tile:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0,0,0,.08);
  border-color: rgba(0,0,0,.14);
  background: #fff;
}
.r3-desk-tile:focus-visible { outline: 2px solid #E95420; outline-offset: 2px; }
.r3-desk-tile--busy { opacity: .65; pointer-events: none; }
.r3-desk-tile--off {
  opacity: .55; cursor: not-allowed;
}
.r3-desk-tile--aktien {
  border-color: rgba(233,84,32,.35);
  background: linear-gradient(180deg, #fff 0%, #fff9f6 100%);
}
.r3-desk-model {
  font-size: 9px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase;
  color: #E95420; padding: 2px 6px; border-radius: 6px; background: rgba(233,84,32,.1);
}
.r3-desk-ico {
  width: 44px; height: 44px; border-radius: 12px;
  display: grid; place-items: center;
  background: #fff;
  color: #E95420;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.08);
}
.r3-desk-tile--off .r3-desk-ico { color: #a8a8a8; background: #f0f0f0; }
.r3-desk-ico svg { width: 22px; height: 22px; }
.r3-desk-label { font-weight: 700; font-size: 13px; line-height: 1.2; color: #2e2e2e; }
.r3-desk-detail { font-size: 10px; color: #8a8a8a; line-height: 1.3; max-width: 100%; }
.r3-desk-foot {
  margin: 16px 0 0; padding-top: 14px; border-top: 1px solid rgba(0,0,0,.08);
  font-size: 12px; color: #8a8a8a; line-height: 1.45;
}
.r3-desk-toast { margin-top: 10px; font-size: 13px; min-height: 1.2em; font-weight: 600; }
.r3-desk-toast.ok { color: #2e7d32; }
.r3-desk-toast.fail { color: #c0392b; }
@media (prefers-color-scheme: dark) {
  .r3-desk { background: #2b2b2b; border-color: rgba(255,255,255,.1); }
  .r3-desk-hero { background: #333; border-bottom-color: rgba(255,255,255,.08); }
  .r3-desk-hero h2 { color: #f2f2f2; }
  .r3-desk-hero .subtitle { color: #b0b0b0; }
  .r3-desk-body { background: #2b2b2b; }
  .r3-desk-supremacy { background: #333; color: #d0d0d0; border-bottom-color: rgba(255,255,255,.08); }
  .r3-desk-pill { background: #3a3a3a; color: #c8c8c8; border-color: rgba(255,255,255,.08); }
  .r3-desk-pill--accent { background: #404040; color: #f0f0f0; }
  .r3-desk-tile { background: #353535; border-color: rgba(255,255,255,.1); color: #f0f0f0; }
  .r3-desk-tile:hover:not(:disabled) { background: #3d3d3d; border-color: rgba(255,255,255,.16); }
  .r3-desk-ico { background: #2b2b2b; box-shadow: inset 0 0 0 1px rgba(255,255,255,.1); }
  .r3-desk-label { color: #f0f0f0; }
  .r3-desk-detail, .r3-desk-foot, .r3-desk-group h3 { color: #a8a8a8; }
  .r3-desk-tile--off .r3-desk-ico { background: #3a3a3a; color: #777; }
}
@media (max-width: 520px) {
  .r3-desk-grid { grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .r3-desk-tile { min-height: 96px; padding: 12px 6px; }
}
""" + FUSION_CSS + NATIVE_CSS + STEP_A_CSS


SHELL_JS = """
async function r3LaunchDesktop(featureId, btn) {
  if (btn && btn.classList.contains('r3-desk-tile--off')) return;
  const toast = document.getElementById('r3-desk-toast');
  if (btn) btn.classList.add('r3-desk-tile--busy');
  if (toast) { toast.className = 'r3-desk-toast'; toast.textContent = 'Starte…'; }
  try {
    const r = await fetch('/api/desktop/launch?feature=' + encodeURIComponent(featureId), { cache: 'no-store' });
    const j = await r.json();
    if (toast) {
      toast.className = 'r3-desk-toast ' + (j.ok ? 'ok' : 'fail');
      toast.textContent = j.message_de || j.error_de || (j.ok ? 'OK' : 'Fehler');
    }
  } catch (e) {
    if (toast) { toast.className = 'r3-desk-toast fail'; toast.textContent = 'Verbindung fehlgeschlagen'; }
  } finally {
    if (btn) btn.classList.remove('r3-desk-tile--busy');
  }
}
async function r3RefreshShellMeta() {
  try {
    const r = await fetch('/api/desktop/shell', { cache: 'no-store' });
    const j = await r.json();
    const set = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.textContent = val; };
    set('r3-desk-clock', j.clock_de);
    set('r3-desk-wifi-val', j.wifi_de);
    const upd = document.getElementById('r3-fusion-updates');
    if (upd && j.updates_de) {
      upd.textContent = j.updates_de;
      upd.classList.toggle('has-updates', (j.updates_pending || 0) > 0);
    }
    const stepBFill = document.querySelector('.r3-stepb-fill');
    if (stepBFill && j.step_b_percent != null) stepBFill.style.width = j.step_b_percent + '%';
    const stepFill = document.querySelector('.r3-stepa-fill');
    if (stepFill && j.step_a_percent != null) stepFill.style.width = j.step_a_percent + '%';
  } catch (e) {}
}
setInterval(r3RefreshShellMeta, 30000);
""" + FUSION_JS + NATIVE_JS


def _category_order(cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    cats = cfg.get("categories") or []
    out: List[Dict[str, str]] = []
    for row in cats:
        if isinstance(row, dict) and row.get("id"):
            out.append({"id": str(row["id"]), "label_de": str(row.get("label_de") or row["id"])})
    if not out:
        out = [
            {"id": "markt", "label_de": "Markt"},
            {"id": "werkzeug", "label_de": "Werkzeug"},
            {"id": "system", "label_de": "System"},
            {"id": "verbindung", "label_de": "Verbindung"},
            {"id": "darstellung", "label_de": "Darstellung"},
        ]
    return out


def _render_tile(root: Path, row: Dict[str, Any], *, available: bool = True) -> str:
    fid = str(row.get("id") or "")
    extra_cls = " r3-desk-tile--aktien" if fid == "aktien" else ""
    off_cls = "" if available else " r3-desk-tile--off"
    dis = "" if available else ' disabled aria-disabled="true"'
    title = _esc(row.get("detail_de"))
    if not available:
        title = f"{title} · nicht installiert"
    model_badge = ""
    if fid == "aktien":
        model_badge = '<span class="r3-desk-model">DAILY_ALPHA_H1</span>'
    return f"""<button type="button" class="r3-desk-tile{extra_cls}{off_cls}"{dis}
  onclick="r3LaunchDesktopMaybeNative('{_esc(fid)}', this)" title="{title}">
  <span class="r3-desk-ico">{shell_icon_svg(fid)}</span>
  <span class="r3-desk-label">{_esc(row.get('label_de'))}</span>
  <span class="r3-desk-detail">{_esc(row.get('detail_de'))}</span>
  {model_badge}
</button>"""


def render_ubuntu_shell_section(
    root: Path,
    status: Optional[Dict[str, Any]] = None,
    *,
    fast: bool = False,
) -> str:
    root = Path(root)
    doc = status or build_shell_status(root)
    cfg = load_ubuntu_shell(root)
    avail_map = {
        str(f.get("id")): bool(f.get("available"))
        for f in (doc.get("features") or [])
        if isinstance(f, dict)
    }
    by_cat: Dict[str, List[str]] = {}
    for row in cfg.get("features") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        cid = str(row.get("category") or "werkzeug")
        fid = str(row["id"])
        avail_fn = _feature_available_fast if fast else _feature_available
        tile = _render_tile(root, row, available=avail_map.get(fid, avail_fn(root, row)))
        by_cat.setdefault(cid, []).append(tile)

    groups = []
    for cat in _category_order(cfg):
        tiles = by_cat.get(cat["id"])
        if not tiles:
            continue
        groups.append(
            f"""<div class="r3-desk-group">
  <h3>{_esc(cat['label_de'])}</h3>
  <div class="r3-desk-grid">{''.join(tiles)}</div>
</div>"""
        )

    note = _esc(doc.get("linux_mainline_de") or cfg.get("linux_mainline_de") or "")
    supremacy_banner = ""
    if doc.get("r3_supremacy_active"):
        supremacy_banner = (
            f'<p class="r3-desk-supremacy">'
            f'{_esc(doc.get("r3_supremacy_headline_de") or "R3 — dein Stack ist die Oberfläche")}'
            f" · Nur R3 Cockpit steuert den Weg.</p>"
        )

    wifi_ico = shell_icon_svg("network")
    fusion_html = render_fusion_chrome(root, shell_cfg=cfg, fusion_doc=doc)
    if is_phase_b_active(root):
        step_progress_html = render_step_b_progress(root, doc.get("step_b") or evaluate_step_b(root))
    else:
        step_progress_html = render_step_a_progress(root, doc)
    if fast:
        pct = int((doc.get("ubuntu_closure") or {}).get("closure_percent") or doc.get("step_a_percent") or 0)
        closure_html = (
            f'<div class="r3-closure-bar" id="r3-closure-fast">'
            f'<span>Ubuntu-Abschluss (schnell)</span><strong>{pct}%</strong></div>'
        )
        notify_html = ""
    else:
        notify_html = render_notifications_panel(root)
        closure_html = render_ubuntu_closure_section(root, doc.get("ubuntu_closure"))

    return f"""
<section class="card r3-desk" id="r3-desktop-shell" aria-label="R3 System">
  {supremacy_banner}
  {closure_html}
  {step_progress_html}
  <div class="r3-desk-hero">
    <div class="r3-desk-brand">
      <div class="r3-desk-mark" aria-hidden="true">R3</div>
      <div>
        <h2>{_esc(doc.get('section_title_de') or 'R3 System')}</h2>
        <p class="subtitle">{_esc(doc.get('section_subtitle_de') or '')}</p>
      </div>
    </div>
    <div class="r3-desk-status">
      <span class="r3-desk-pill r3-desk-pill--accent" id="r3-desk-clock">{_esc(doc.get('clock_de'))}</span>
      <span class="r3-desk-pill">{_esc(doc.get('hostname'))}</span>
      <span class="r3-desk-pill">{_esc(doc.get('session_de'))}</span>
      <span class="r3-desk-pill">
        <span class="r3-desk-pill-ico">{wifi_ico}</span>
        <span id="r3-desk-wifi-val">{_esc(doc.get('wifi_de'))}</span>
      </span>
    </div>
  </div>
  {fusion_html}
  {notify_html}
  <div class="r3-desk-body">
    {''.join(groups)}
    <p class="r3-desk-foot">{note}</p>
    <div id="r3-desk-toast" class="r3-desk-toast" aria-live="polite"></div>
  </div>
</section>"""


def shell_desktop_entries(root: Path, *, os_name: str = "R3", icon_name: str = "r3-os") -> Dict[str, Dict[str, str]]:
    """Desktop-Einträge für häufig genutzte Arbeitsflächen-Apps."""
    root = Path(root).resolve()
    cfg = load_ubuntu_shell(root)
    launch_sh = root / "tools/r3_shell_launch.sh"
    out: Dict[str, Dict[str, str]] = {}
    for cmd, fid in (cfg.get("quick_bin_commands") or {}).items():
        spec = _feature_map(root).get(str(fid))
        if not spec:
            continue
        label = str(spec.get("label_de") or fid)
        out[f"R3-{label}.desktop"] = {
            "name": f"{os_name} — {label}",
            "comment": str(spec.get("detail_de") or label),
            "exec": f"env AA_PROJECT_ROOT={root} {launch_sh} {fid}",
            "icon": str(spec.get("desktop_icon") or icon_name),
            "keywords": f"r3;{fid};desktop",
        }
    return out
