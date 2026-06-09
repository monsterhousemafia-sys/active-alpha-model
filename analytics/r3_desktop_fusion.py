"""R3 Desktop Fusion — Apple-Klarheit + Microsoft-Produktivität (Schritt A)."""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from analytics.r3_shell_icons import shell_icon_svg

_CONFIG_REL = Path("control/r3_os_fusion.json")


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


def load_fusion_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL)


def _expand_tokens(spec: Dict[str, Any]) -> List[str]:
    home = str(Path.home())
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    out: List[str] = []
    for part in list(spec.get("exec") or []):
        out.append(
            str(part)
            .replace("{home}", home)
            .replace("{user}", user)
            .replace("{root}", str(Path(spec.get("_root", ".")).resolve()))
        )
    return out


def _command_available(cmd: Sequence[str]) -> bool:
    return bool(cmd) and shutil.which(str(cmd[0])) is not None


def _resolve_cmd(root: Path, spec: Dict[str, Any]) -> List[str]:
    spec = {**spec, "_root": str(root)}
    cmd = _expand_tokens(spec)
    if _command_available(cmd):
        return cmd
    fb = list(spec.get("fallback_exec") or [])
    if fb:
        cmd = _expand_tokens({**spec, "exec": fb})
        if _command_available(cmd):
            return cmd
    return cmd


def _run_quiet(cmd: Sequence[str], *, timeout: float = 5.0) -> Optional[str]:
    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return (proc.stdout or proc.stderr or "").strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _updates_summary(root: Path) -> Dict[str, Any]:
    cfg = load_fusion_config(root).get("updates") or {}
    cmd = list(cfg.get("check_cmd") or ["apt", "list", "--upgradable"])
    if not _command_available(cmd):
        return {"updates_pending": None, "updates_de": "—", "updates_ok": False}
    out = _run_quiet(cmd, timeout=8) or ""
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("Listing")]
    count = len(lines)
    if count == 0:
        text = "Aktuell"
    elif count == 1:
        text = "1 Update"
    else:
        text = f"{count} Updates"
    return {"updates_pending": count, "updates_de": text, "updates_ok": True}


def build_fusion_status(root: Path) -> Dict[str, Any]:
    cfg = load_fusion_config(root)
    upd = _updates_summary(root)
    phase = str(cfg.get("phase") or "A").upper()
    phase_title = (
        cfg.get("phase_b_title_de")
        if phase == "B"
        else cfg.get("phase_a_title_de")
    )
    return {
        "fusion_phase": phase,
        "fusion_phase_title_de": phase_title,
        "updates_de": upd.get("updates_de"),
        "updates_pending": upd.get("updates_pending"),
        "updates_ok": upd.get("updates_ok"),
        "pinned_apps": list(cfg.get("pinned_apps") or []),
        "power_actions": [
            {
                "id": row.get("id"),
                "label_de": row.get("label_de"),
                "detail_de": row.get("detail_de"),
                "confirm_de": row.get("confirm_de"),
                "available": bool(_resolve_cmd(root, row)) if isinstance(row, dict) else False,
            }
            for row in (cfg.get("power_actions") or [])
            if isinstance(row, dict) and row.get("id")
        ],
    }


def fusion_search_index(root: Path) -> List[Dict[str, str]]:
    """Spotlight/Start-Index über Shell-Features."""
    from analytics.r3_ubuntu_shell import load_ubuntu_shell

    cfg = load_ubuntu_shell(root)
    out: List[Dict[str, str]] = []
    for row in cfg.get("features") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        fid = str(row["id"])
        out.append(
            {
                "id": fid,
                "label_de": str(row.get("label_de") or fid),
                "detail_de": str(row.get("detail_de") or ""),
                "category": str(row.get("category") or ""),
                "keywords": f"{fid} {row.get('label_de')} {row.get('detail_de')} {row.get('category')}".lower(),
            }
        )
    cfg_f = load_fusion_config(root)
    for row in cfg_f.get("power_actions") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        pid = str(row["id"])
        out.append(
            {
                "id": f"power:{pid}",
                "label_de": str(row.get("label_de") or pid),
                "detail_de": str(row.get("detail_de") or "Energie"),
                "category": "energie",
                "confirm_de": row.get("confirm_de"),
                "keywords": f"power {pid} {row.get('label_de')} energie".lower(),
            }
        )
    return out


def fusion_search(root: Path, query: str, *, limit: int = 12) -> Dict[str, Any]:
    q = str(query or "").strip().lower()
    index = fusion_search_index(root)
    if not q:
        return {"query": q, "results": index[:limit]}
    hits = []
    for row in index:
        if q in row.get("keywords") or q in row.get("label_de", "").lower():
            hit = {k: row[k] for k in ("id", "label_de", "detail_de", "category") if k in row}
            if row.get("confirm_de"):
                hit["confirm_de"] = row.get("confirm_de")
            hits.append(hit)
        if len(hits) >= limit:
            break
    return {"query": q, "results": hits}


def launch_power_action(root: Path, action_id: str) -> Dict[str, Any]:
    """Whitelist: nur konfigurierte Power-Aktionen."""
    root = Path(root)
    aid = str(action_id or "").strip()
    cfg = load_fusion_config(root)
    spec = None
    for row in cfg.get("power_actions") or []:
        if isinstance(row, dict) and str(row.get("id")) == aid:
            spec = row
            break
    if not spec:
        return {"ok": False, "error_de": f"Unbekannte Aktion: {aid}"}

    if aid != "lock" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "error_de": "Keine grafische Sitzung."}

    cmd = _resolve_cmd(root, spec)
    if not _command_available(cmd):
        return {"ok": False, "error_de": f"Befehl nicht verfügbar: {cmd[0] if cmd else '—'}"}

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
            "action_id": aid,
            "label_de": spec.get("label_de"),
            "message_de": f"{spec.get('label_de')} wird ausgeführt.",
        }
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200]}


FUSION_CSS = """
.r3-fusion { padding: 0 22px 16px; border-bottom: 1px solid rgba(0,0,0,.08); background: #fafafa; }
.r3-fusion-spotlight {
  display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
  padding: 10px 14px; border-radius: 12px; border: 1px solid rgba(0,0,0,.1);
  background: #fff;
}
.r3-fusion-spotlight svg { width: 18px; height: 18px; color: #8a8a8a; flex-shrink: 0; }
.r3-fusion-spotlight input {
  flex: 1; border: 0; background: transparent; font: inherit; font-size: 15px;
  color: #2e2e2e; outline: none;
}
.r3-fusion-spotlight kbd {
  font-size: 11px; padding: 3px 7px; border-radius: 6px; background: #f0f0f0;
  color: #6e6e6e; border: 1px solid rgba(0,0,0,.08);
}
.r3-fusion-dock {
  display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px;
}
.r3-fusion-dock-btn {
  display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-radius: 999px; border: 1px solid rgba(0,0,0,.08); background: #fff;
  color: #2e2e2e; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer;
}
.r3-fusion-dock-btn:hover { border-color: #E95420; }
.r3-fusion-dock--aktien { border-color: rgba(233,84,32,.35); background: #fff9f6; }
.r3-fusion-dock-model {
  font-size: 9px; font-weight: 800; color: #E95420; letter-spacing: .04em;
}
.r3-fusion-dock-ico { width: 18px; height: 18px; color: #E95420; display: grid; place-items: center; }
.r3-fusion-dock-ico svg { width: 16px; height: 16px; }
.r3-fusion-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.r3-fusion-toggle {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px;
  border-radius: 12px; border: 1px solid rgba(0,0,0,.08); background: #fff;
  font: inherit; font-size: 12px; font-weight: 600; color: #2e2e2e; cursor: pointer;
}
.r3-fusion-toggle:hover { border-color: #E95420; }
.r3-fusion-toggle-ico { width: 16px; height: 16px; color: #E95420; }
.r3-fusion-toggle-ico svg { width: 100%; height: 100%; }
.r3-fusion-updates {
  margin-left: auto; font-size: 12px; font-weight: 600; color: #6e6e6e;
  padding: 8px 12px; border-radius: 12px; background: #f0f0f0;
}
.r3-fusion-updates.has-updates { color: #E95420; background: rgba(233,84,32,.1); }
.r3-fusion-power-wrap { position: relative; }
.r3-fusion-power-menu {
  display: none; position: absolute; right: 0; top: calc(100% + 6px); z-index: 20;
  min-width: 200px; padding: 6px; border-radius: 14px; border: 1px solid rgba(0,0,0,.1);
  background: #fff; box-shadow: 0 12px 32px rgba(0,0,0,.12);
}
.r3-fusion-power-menu.open { display: block; }
.r3-fusion-power-menu button {
  display: flex; width: 100%; align-items: center; gap: 10px; padding: 10px 12px;
  border: 0; border-radius: 10px; background: transparent; font: inherit; font-size: 13px;
  font-weight: 600; color: #2e2e2e; cursor: pointer; text-align: left;
}
.r3-fusion-power-menu button:hover { background: #f5f5f5; }
.r3-fusion-power-menu button.danger { color: #c0392b; }
.r3-fusion-search-results {
  display: none; margin: 0 22px 12px; padding: 8px; border-radius: 12px;
  border: 1px solid rgba(0,0,0,.08); background: #fff;
}
.r3-fusion-search-results.open { display: block; }
.r3-fusion-search-results button {
  display: flex; width: 100%; gap: 10px; align-items: center; padding: 10px 12px;
  border: 0; border-radius: 10px; background: transparent; font: inherit; text-align: left;
  cursor: pointer; color: #2e2e2e;
}
.r3-fusion-search-results button:hover { background: #f5f5f5; }
.r3-fusion-search-results .sub { font-size: 11px; color: #8a8a8a; }
.r3-fusion-phase {
  font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  color: #8a8a8a; margin: 0 22px 8px;
}
.r3-desk-tile[data-fusion-hidden="1"] { display: none !important; }
.r3-desk-group[data-fusion-empty="1"] { display: none !important; }
@media (prefers-color-scheme: dark) {
  .r3-fusion { background: #333; border-bottom-color: rgba(255,255,255,.08); }
  .r3-fusion-spotlight, .r3-fusion-dock-btn, .r3-fusion-toggle, .r3-fusion-power-menu,
  .r3-fusion-search-results { background: #2b2b2b; border-color: rgba(255,255,255,.1); color: #f0f0f0; }
  .r3-fusion-spotlight input { color: #f0f0f0; }
  .r3-fusion-power-menu button:hover, .r3-fusion-search-results button:hover { background: #3a3a3a; }
}
"""


FUSION_JS = """
function r3FusionToast(msg, ok) {
  const toast = document.getElementById('r3-desk-toast');
  if (!toast) return;
  toast.className = 'r3-desk-toast ' + (ok ? 'ok' : 'fail');
  toast.textContent = msg;
}
async function r3LaunchDesktopFeature(featureId, btn) {
  if (featureId.startsWith('power:')) {
    return r3FusionPower(featureId.slice(6), null);
  }
  return r3LaunchDesktop(featureId, btn);
}
async function r3FusionPower(actionId, confirmText) {
  if (confirmText && !window.confirm(confirmText)) return;
  try {
    const r = await fetch('/api/desktop/power?action=' + encodeURIComponent(actionId), { cache: 'no-store' });
    const j = await r.json();
    r3FusionToast(j.message_de || j.error_de || (j.ok ? 'OK' : 'Fehler'), j.ok);
    const menu = document.getElementById('r3-fusion-power-menu');
    if (menu) menu.classList.remove('open');
  } catch (e) {
    r3FusionToast('Verbindung fehlgeschlagen', false);
  }
}
function r3FusionTogglePowerMenu() {
  const menu = document.getElementById('r3-fusion-power-menu');
  if (menu) menu.classList.toggle('open');
}
document.addEventListener('click', (e) => {
  const menu = document.getElementById('r3-fusion-power-menu');
  const btn = document.getElementById('r3-fusion-power-btn');
  if (menu && btn && !menu.contains(e.target) && !btn.contains(e.target)) {
    menu.classList.remove('open');
  }
});
let r3FusionSearchTimer = null;
function r3FusionFilterTiles(q) {
  const query = (q || '').trim().toLowerCase();
  const tiles = document.querySelectorAll('.r3-desk-tile');
  const groups = document.querySelectorAll('.r3-desk-group');
  tiles.forEach((t) => {
    const label = (t.querySelector('.r3-desk-label')?.textContent || '').toLowerCase();
    const detail = (t.querySelector('.r3-desk-detail')?.textContent || '').toLowerCase();
    const show = !query || label.includes(query) || detail.includes(query);
    t.dataset.fusionHidden = show ? '0' : '1';
  });
  groups.forEach((g) => {
    const visible = g.querySelectorAll('.r3-desk-tile:not([data-fusion-hidden="1"])').length;
    g.dataset.fusionEmpty = visible ? '0' : '1';
  });
}
async function r3FusionSearchRemote(q) {
  const box = document.getElementById('r3-fusion-search-results');
  if (!box) return;
  const query = (q || '').trim();
  if (!query) { box.classList.remove('open'); box.innerHTML = ''; r3FusionFilterTiles(''); return; }
  r3FusionFilterTiles(query);
  try {
    const r = await fetch('/api/desktop/search?q=' + encodeURIComponent(query), { cache: 'no-store' });
    const j = await r.json();
    const rows = (j.results || []).slice(0, 8);
    if (!rows.length) { box.classList.remove('open'); return; }
    box.innerHTML = rows.map((row) => {
      const id = row.id || '';
      const onclick = id.startsWith('power:')
        ? "r3FusionPower('" + id.slice(6) + "', " + JSON.stringify(row.confirm_de || null) + ")"
        : "r3LaunchDesktopMaybeNative('" + id + "', null)";
      return '<button type="button" onclick="' + onclick + '"><div><div>' + (row.label_de || '') +
        '</div><div class="sub">' + (row.detail_de || '') + '</div></div></button>';
    }).join('');
    box.classList.add('open');
  } catch (e) {}
}
function r3FusionOnSearchInput(el) {
  clearTimeout(r3FusionSearchTimer);
  r3FusionSearchTimer = setTimeout(() => r3FusionSearchRemote(el.value), 120);
}
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    const inp = document.getElementById('r3-fusion-search');
    if (inp) { e.preventDefault(); inp.focus(); inp.select(); }
  }
});
function r3FusionOpenUpdates() {
  if (typeof r3NativeOpen === 'function') r3NativeOpen('updates');
  else r3LaunchDesktop('updates', null);
}
function r3FusionScrollBau() {
  const el = document.getElementById('r3-build-kernel');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  else r3FusionToast('Bau-Kernel — /bau im Chat', true);
}
"""


def render_fusion_chrome(
    root: Path,
    *,
    shell_cfg: Dict[str, Any],
    fusion_doc: Optional[Dict[str, Any]] = None,
) -> str:
    root = Path(root)
    cfg = load_fusion_config(root)
    doc = fusion_doc or build_fusion_status(root)
    feature_map = {
        str(r.get("id")): r
        for r in (shell_cfg.get("features") or [])
        if isinstance(r, dict) and r.get("id")
    }

    dock_btns = []
    for fid in cfg.get("pinned_apps") or []:
        spec = feature_map.get(str(fid))
        if not spec:
            continue
        aktien_cls = " r3-fusion-dock--aktien" if fid == "aktien" else ""
        model_tag = (
            '<span class="r3-fusion-dock-model">H1</span>' if fid == "aktien" else ""
        )
        dock_btns.append(
            f"""<button type="button" class="r3-fusion-dock-btn{aktien_cls}" onclick="r3LaunchDesktopMaybeNative('{_esc(fid)}', this)" title="{_esc(spec.get('detail_de'))}">
  <span class="r3-fusion-dock-ico">{shell_icon_svg(str(fid))}</span>
  <span>{_esc(spec.get('label_de'))}</span>{model_tag}
</button>"""
        )
    if "bau" in [str(x) for x in (cfg.get("pinned_apps") or [])]:
        dock_btns.insert(
            min(4, len(dock_btns)),
            """<button type="button" class="r3-fusion-dock-btn" onclick="r3FusionScrollBau()" title="Bau-Werkstatt ohne Cursor">
  <span class="r3-fusion-dock-ico">"""
            + shell_icon_svg("bau")
            + """</span><span>Bauen</span></button>""",
        )

    toggles = []
    for row in cfg.get("control_toggles") or []:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("feature") or row.get("id") or "")
        toggles.append(
            f"""<button type="button" class="r3-fusion-toggle" onclick="r3LaunchDesktop('{_esc(fid)}', this)" title="{_esc(row.get('label_de'))}">
  <span class="r3-fusion-toggle-ico">{shell_icon_svg(fid)}</span>
  <span>{_esc(row.get('label_de'))}</span>
</button>"""
        )

    power_items = []
    for row in cfg.get("power_actions") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        pid = str(row["id"])
        confirm = row.get("confirm_de")
        confirm_arg = _esc(confirm) if confirm else ""
        onclick = (
            f"r3FusionPower('{_esc(pid)}', '{confirm_arg}')"
            if confirm
            else f"r3FusionPower('{_esc(pid)}', null)"
        )
        danger = " danger" if pid in ("shutdown", "reboot") else ""
        power_items.append(
            f'<button type="button" class="{danger.strip()}" onclick="{onclick}">'
            f'{shell_icon_svg("power" if pid != "lock" else "lock")} '
            f'<span>{_esc(row.get("label_de"))}</span></button>'
        )

    upd_cls = "r3-fusion-updates"
    pending = doc.get("updates_pending")
    if isinstance(pending, int) and pending > 0:
        upd_cls += " has-updates"

    phase = _esc(doc.get("fusion_phase") or "A")
    phase_title = _esc(
        doc.get("fusion_phase_title_de")
        or (cfg.get("phase_b_title_de") if phase == "B" else cfg.get("phase_a_title_de"))
        or "Schritt A"
    )

    return f"""
<p class="r3-fusion-phase" title="{phase_title}">Fusion · Phase {phase} — {phase_title}</p>
<div class="r3-fusion">
  <div class="r3-fusion-spotlight">
    {shell_icon_svg("apps")}
    <input type="search" id="r3-fusion-search" placeholder="Suchen — Apps, Einstellungen, Energie …" autocomplete="off"
      aria-label="Spotlight-Suche" oninput="r3FusionOnSearchInput(this)" />
    <kbd>Ctrl+K</kbd>
  </div>
  <div class="r3-fusion-dock" aria-label="Dock">{''.join(dock_btns)}</div>
  <div class="r3-fusion-bar" aria-label="Control Center">
    {''.join(toggles)}
    <div class="r3-fusion-power-wrap">
      <button type="button" class="r3-fusion-toggle" id="r3-fusion-power-btn" onclick="r3FusionTogglePowerMenu()">
        <span class="r3-fusion-toggle-ico">{shell_icon_svg("power")}</span>
        <span>Energie</span>
      </button>
      <div class="r3-fusion-power-menu" id="r3-fusion-power-menu">{''.join(power_items)}</div>
    </div>
    <button type="button" class="{upd_cls}" id="r3-fusion-updates" title="Updates — R3-Panel" onclick="r3FusionOpenUpdates()" style="border:0;cursor:pointer;font:inherit;">{_esc(doc.get('updates_de'))}</button>
  </div>
</div>
<div class="r3-fusion-search-results" id="r3-fusion-search-results" aria-live="polite"></div>"""
