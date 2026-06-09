"""R3 native Kern-Apps — Dateien, Terminal, Einstellungen (Schritt A, ohne GNOME-Pflicht)."""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

_NATIVE_IDS = (
    "files",
    "terminal",
    "settings",
    "calculator",
    "screenshot",
    "apps",
    "network",
    "display",
    "power",
    "lock",
    "updates",
)
NATIVE_APP_IDS = frozenset(_NATIVE_IDS)
_TEXT_PREVIEW_EXT = frozenset(
    {".txt", ".md", ".json", ".py", ".sh", ".csv", ".log", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".html", ".js", ".ts"}
)
_IMAGE_PREVIEW_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})
_CONSOLE_WHITELIST = (
    "python3 tools/ai_kernel.py status",
    "python3 tools/ai_kernel.py warnings",
    "python3 tools/ai_kernel.py r3",
    "python3 tools/ai_kernel.py trading-day",
    "python3 tools/ai_kernel.py h1-status",
    "python3 tools/ai_kernel.py r3-migration-check",
    "python3 tools/ai_kernel.py r3-preserve",
    "python3 -m pytest tests/test_r3_system_plane.py -q",
    "ls -la",
    "pwd",
    "df -h",
    "free -h",
    "uname -a",
)
_CONFIG_REL = Path("control/r3_native_apps.json")


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


def load_native_config(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL)
    if doc:
        return doc
    return {
        "apps": {
            "files": {"label_de": "Dateien", "root": "{home}"},
            "terminal": {"label_de": "Terminal", "fallback_exec": ["ptyxis", "gnome-terminal", "kgx", "xterm"]},
            "settings": {"label_de": "Einstellungen"},
        }
    }


def native_apps_ready(root: Path) -> bool:
    root = Path(root)
    return (root / "control/r3_native_apps.json").is_file() and (root / "analytics/r3_native_apps.py").is_file()


def _safe_home_path(subpath: str = "") -> Path:
    home = Path.home().resolve()
    raw = str(subpath or "").strip().replace("\\", "/").lstrip("/")
    if ".." in raw.split("/"):
        return home
    target = (home / raw).resolve()
    if not str(target).startswith(str(home)):
        return home
    return target


def _safe_project_path(root: Path, subpath: str = "") -> Path:
    root = Path(root).resolve()
    raw = str(subpath or "").strip().replace("\\", "/").lstrip("/")
    if ".." in raw.split("/"):
        return root
    target = (root / raw).resolve()
    if not str(target).startswith(str(root)):
        return root
    return target


def list_project_files(root: Path, *, subpath: str = "", limit: int = 80) -> Dict[str, Any]:
    """Arbeitsbaum-Dateien — Projektroot-Bindung für R3 Desktop."""
    root = Path(root).resolve()
    base = _safe_project_path(root, subpath)
    entries: List[Dict[str, str]] = []
    try:
        for child in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:limit]:
            if child.name.startswith(".") and child.is_dir() and child.name not in (".cursor",):
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "kind": "dir" if child.is_dir() else "file",
                }
            )
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200], "path": str(base), "entries": []}
    rel = str(base.relative_to(root)) if base != root else ""
    parent_rel = ""
    if base != root:
        parent_rel = str(base.parent.relative_to(root)) if base.parent != root else ""
    return {
        "ok": True,
        "scope": "project",
        "project_root": str(root),
        "path": str(base),
        "relative_de": rel or "/",
        "parent_rel": parent_rel,
        "entries": entries,
    }


def list_files(root: Path, *, subpath: str = "", limit: int = 80) -> Dict[str, Any]:
    root = Path(root)
    base = _safe_home_path(subpath)
    entries: List[Dict[str, str]] = []
    try:
        for child in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:limit]:
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "kind": "dir" if child.is_dir() else "file",
                }
            )
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200], "path": str(base), "entries": []}
    home = Path.home().resolve()
    rel = str(base.relative_to(home)) if base != home else ""
    parent_rel = ""
    if base != home:
        parent_rel = str(base.parent.relative_to(home)) if base.parent != home else ""
    return {
        "ok": True,
        "path": str(base),
        "relative_de": rel or "~",
        "parent_rel": parent_rel,
        "entries": entries,
    }


def preview_file(path: str, *, max_bytes: int = 65536) -> Dict[str, Any]:
    import base64

    p = Path(str(path or "")).resolve()
    home = Path.home().resolve()
    if not str(p).startswith(str(home)) or not p.is_file():
        return {"ok": False, "error_de": "Datei nicht lesbar."}
    ext = p.suffix.lower()
    if ext in _IMAGE_PREVIEW_EXT:
        try:
            raw = p.read_bytes()[: max_bytes * 2]
            mime = "image/png" if ext == ".png" else "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
            return {
                "ok": True,
                "preview": True,
                "preview_kind": "image",
                "filename": p.name,
                "mime": mime,
                "content_b64": base64.b64encode(raw).decode("ascii"),
                "truncated": p.stat().st_size > len(raw),
            }
        except OSError as exc:
            return {"ok": False, "error_de": str(exc)[:200]}
    if ext not in _TEXT_PREVIEW_EXT:
        return {"ok": False, "preview": False, "error_de": "Keine Vorschau — xdg-open nutzen."}
    try:
        data = p.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200]}
    return {"ok": True, "preview": True, "preview_kind": "text", "filename": p.name, "content": data, "truncated": p.stat().st_size > max_bytes}


def open_path(path: str) -> Dict[str, Any]:
    prev = preview_file(path)
    if prev.get("ok") and prev.get("preview"):
        return {**prev, "message_de": f"Vorschau: {prev.get('filename')}"}
    p = Path(str(path or "")).resolve()
    home = Path.home().resolve()
    if not str(p).startswith(str(home)):
        return {"ok": False, "error_de": "Pfad außerhalb des Home-Verzeichnisses."}
    cmd = shutil.which("xdg-open")
    if not cmd:
        return {"ok": False, "error_de": "xdg-open nicht gefunden"}
    try:
        subprocess.Popen(
            [cmd, str(p)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True, "message_de": f"Öffne {_esc(p.name)}"}
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200]}


def run_terminal_action(root: Path, action_id: str) -> Dict[str, Any]:
    root = Path(root).resolve()
    cfg = load_native_config(root)
    actions = (cfg.get("terminal_actions") or {}) if isinstance(cfg.get("terminal_actions"), dict) else {}
    spec = actions.get(action_id)
    if not spec:
        return {"ok": False, "error_de": f"Unbekannte Terminal-Aktion: {action_id}"}
    raw = [str(x).replace("{root}", str(root)).replace("{home}", str(Path.home())) for x in (spec.get("exec") or [])]
    if not raw or not shutil.which(raw[0]):
        return {"ok": False, "error_de": "Befehl nicht verfügbar"}
    env = os.environ.copy()
    env.setdefault("AA_PROJECT_ROOT", str(root))
    try:
        subprocess.Popen(
            raw,
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True, "message_de": str(spec.get("label_de") or action_id)}
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200]}


def open_system_terminal(root: Path) -> Dict[str, Any]:
    cfg = load_native_config(root)
    app = (cfg.get("apps") or {}).get("terminal") or {}
    for cmd in list(app.get("fallback_exec") or ["ptyxis", "gnome-terminal", "kgx", "xterm"]):
        if shutil.which(str(cmd)):
            try:
                subprocess.Popen(
                    [str(cmd)],
                    cwd=str(root),
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {"ok": True, "message_de": "System-Terminal geöffnet"}
            except OSError:
                continue
    return {"ok": False, "error_de": "Kein Terminal-Programm gefunden"}


def _run_capture(cmd: List[str], *, timeout: float = 5.0) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return (proc.stdout or proc.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def list_apps(root: Path, *, limit: int = 60) -> Dict[str, Any]:
    _ = root
    apps: List[Dict[str, str]] = []
    seen: set[str] = set()
    for base in (Path("/usr/share/applications"), Path.home() / ".local/share/applications"):
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.desktop")):
            name = path.stem
            if name in seen or name.endswith("-qde") or "snap" in name and "store" in name:
                continue
            seen.add(name)
            label = name
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("Name=") and not line.startswith("Name["):
                        label = line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass
            apps.append({"id": name, "label_de": label, "path": str(path)})
            if len(apps) >= limit:
                break
        if len(apps) >= limit:
            break
    return {"ok": True, "count": len(apps), "apps": apps}


def network_panel(root: Path) -> Dict[str, Any]:
    from analytics.r3_system_plane import network_panel as _plane_network

    return _plane_network(root)


def display_panel(root: Path) -> Dict[str, Any]:
    from analytics.r3_system_plane import display_panel as _plane_display

    return _plane_display(root)


def power_panel(root: Path) -> Dict[str, Any]:
    from analytics.r3_system_plane import power_panel as _plane_power

    return _plane_power(root)


def updates_panel(root: Path) -> Dict[str, Any]:
    _ = root
    raw = _run_capture(["apt", "list", "--upgradable"], timeout=20)
    lines = [ln for ln in (raw or "").splitlines() if ln and not ln.startswith("Listing")]
    return {
        "ok": True,
        "panel": "updates",
        "count": len(lines),
        "packages": lines[:40],
        "headline_de": f"{len(lines)} aktualisierbare Pakete",
        "hint_de": "Installation: Schritt B oder Operator (apt)",
    }


def take_screenshot(root: Path) -> Dict[str, Any]:
    _ = Path(root)
    out_dir = Path.home() / ".local/share/r3-os/screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"r3-shot-{stamp}.png"
    for spec in (
        ["grim", str(target)],
        ["gnome-screenshot", "-f", str(target)],
        ["scrot", str(target)],
        ["import", "-window", "root", str(target)],
    ):
        if not shutil.which(spec[0]):
            continue
        try:
            subprocess.run(spec, check=False, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if target.is_file() and target.stat().st_size > 0:
                return {"ok": True, "path": str(target), "message_de": f"Screenshot: {target.name}"}
        except (OSError, subprocess.TimeoutExpired):
            continue
    if os.environ.get("DISPLAY"):
        try:
            from PIL import ImageGrab

            img = ImageGrab.grab()
            img.save(str(target))
            if target.is_file() and target.stat().st_size > 0:
                return {"ok": True, "path": str(target), "message_de": f"Screenshot (PIL): {target.name}"}
        except Exception:
            pass
    return {"ok": False, "error_de": "Kein Screenshot-Tool — apt install grim scrot oder gnome-screenshot"}


def lock_session() -> Dict[str, Any]:
    from analytics.r3_system_plane import lock_session as _plane_lock

    return _plane_lock()


def run_console_command(root: Path, command: str) -> Dict[str, Any]:
    root = Path(root)
    raw = str(command or "").strip()
    if raw not in _CONSOLE_WHITELIST:
        return {"ok": False, "error_de": "Befehl nicht freigegeben — nur Whitelist im R3-Terminal."}
    parts = raw.split()
    env = os.environ.copy()
    env.setdefault("AA_PROJECT_ROOT", str(root))
    try:
        proc = subprocess.run(
            parts,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()[:8000]
        return {"ok": proc.returncode == 0, "output": out, "exit_code": proc.returncode}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error_de": str(exc)[:200]}


def native_panel(root: Path, panel_id: str) -> Dict[str, Any]:
    from analytics.r3_system_plane import session_panel as _plane_session

    pid = str(panel_id or "").strip()
    fn_map = {
        "network": network_panel,
        "display": display_panel,
        "power": power_panel,
        "updates": updates_panel,
        "apps": list_apps,
        "settings": native_settings,
        "session": _plane_session,
    }
    fn = fn_map.get(pid)
    if fn:
        return fn(root)
    if pid == "calculator":
        return {"ok": True, "panel": "calculator", "headline_de": "Rechner"}
    if pid == "screenshot":
        return take_screenshot(root)
    if pid == "lock":
        return {"ok": True, "panel": "lock", "headline_de": "Sitzung sperren"}
    return {"ok": False, "error_de": f"Unbekanntes Panel: {pid}"}


def native_settings(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.r3_desktop_fusion import build_fusion_status
    from analytics.r3_step_a import evaluate_step_a

    try:
        from analytics.r3_os_supremacy import supremacy_status

        sup = supremacy_status(root)
    except Exception:
        sup = {}
    return {
        "ok": True,
        "hub_de": "http://127.0.0.1:17890/",
        "project_root": str(root.resolve()),
        "share_dir": str(Path.home() / ".local/share/r3-os"),
        "fusion": build_fusion_status(root),
        "step_a": evaluate_step_a(root),
        "supremacy_active": bool(sup.get("active")),
        "supremacy_headline_de": sup.get("headline_de"),
    }


def launch_native_app(root: Path, app_id: str) -> Dict[str, Any]:
    """Native Overlay — kein GNOME-Sprung."""
    aid = str(app_id or "").strip()
    if aid not in NATIVE_APP_IDS:
        return {"ok": False, "error_de": f"Keine native App: {aid}"}
    return {
        "ok": True,
        "app_id": aid,
        "native": True,
        "message_de": f"{aid} — R3 Oberfläche",
    }


def _warn_rows(doc: Dict[str, Any]) -> List[Any]:
    """Pilot-Warnungen — verschachteltes dict oder flache Liste."""
    if not doc:
        return []
    outer = doc.get("warnings")
    if isinstance(outer, list):
        return outer
    if isinstance(outer, dict):
        inner = outer.get("warnings") or outer.get("items")
        if isinstance(inner, list):
            return inner
    items = doc.get("items")
    return items if isinstance(items, list) else []


def build_notifications(root: Path, *, limit: int = 8) -> Dict[str, Any]:
    root = Path(root)
    items: List[Dict[str, str]] = []
    h1 = _load_json(root / "control/h1_governance_status.json")
    if h1:
        items.append(
            {
                "level": "info",
                "title_de": "H1 Validierung",
                "body_de": str(h1.get("headline_de") or h1.get("status") or "läuft"),
            }
        )
    warn = _load_json(root / "evidence/pilot_trading_day_warnings_latest.json")
    for row in _warn_rows(warn)[:3]:
        if isinstance(row, dict):
            items.append(
                {
                    "level": "warn",
                    "title_de": "Handel",
                    "body_de": str(row.get("message_de") or row.get("detail_de") or row)[:160],
                }
            )
    build = _load_json(root / "evidence/r3_build_kernel_latest.json")
    if build.get("headline_de") or build.get("reply_de"):
        items.append(
            {
                "level": "info",
                "title_de": "Bau-Kernel",
                "body_de": str(build.get("headline_de") or build.get("reply_de"))[:160],
            }
        )
    try:
        from analytics.r3_step_b import evaluate_step_b, is_phase_b_active

        if is_phase_b_active(root):
            bdoc = evaluate_step_b(root, persist=False)
            items.append(
                {
                    "level": "info",
                    "title_de": "Phase B",
                    "body_de": str(bdoc.get("headline_de") or "OS-Stack")[:160],
                }
            )
        else:
            from analytics.r3_step_a import evaluate_step_a as _eval

            step = _eval(root)
            if not step.get("step_a_code_complete"):
                items.append(
                    {
                        "level": "info",
                        "title_de": "Schritt A",
                        "body_de": f"{step.get('step_a_percent')}% — Ubuntu unsichtbar machen",
                    }
                )
    except Exception:
        pass
    return {"ok": True, "count": len(items[:limit]), "items": items[:limit]}


NATIVE_CSS = """
.r3-native-stage {
  position: fixed; inset: 0; z-index: 9000; pointer-events: none;
}
.r3-native-win {
  position: absolute; pointer-events: auto; display: flex; flex-direction: column;
  min-width: 300px; min-height: 180px; width: min(720px, 92vw); height: auto;
  max-width: 96vw; max-height: 90vh;
  background: #fff; border-radius: 14px; border: 1px solid rgba(0,0,0,.1);
  box-shadow: 0 18px 48px rgba(0,0,0,.16); overflow: hidden;
  transition: box-shadow .15s ease, border-color .15s ease;
}
.r3-native-win.focused {
  border-color: rgba(233,84,32,.4);
  box-shadow: 0 22px 56px rgba(0,0,0,.22);
}
.r3-native-win.minimized { display: none !important; }
.r3-native-win.snapped-left,
.r3-native-win.snapped-right,
.r3-native-win.snapped-max { border-radius: 12px; }
.r3-native-head {
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
  padding: 10px 12px 10px 14px; border-bottom: 1px solid rgba(0,0,0,.08);
  background: linear-gradient(180deg, #fafafa, #f4f4f4); cursor: grab; user-select: none;
}
.r3-native-head:active { cursor: grabbing; }
.r3-native-lights { display: flex; gap: 7px; flex-shrink: 0; }
.r3-native-light {
  width: 12px; height: 12px; border-radius: 50%; border: 0; padding: 0; cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.08);
}
.r3-native-light--close { background: #ff5f57; }
.r3-native-light--min { background: #febc2e; }
.r3-native-light--max { background: #28c840; }
.r3-native-light:hover { filter: brightness(.92); }
.r3-native-title {
  flex: 1; margin: 0; font-size: 13px; font-weight: 600; text-align: center;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.r3-native-tools { display: flex; gap: 4px; flex-shrink: 0; }
.r3-native-tool {
  border: 0; background: rgba(0,0,0,.05); border-radius: 8px; width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center; cursor: pointer; color: #555;
}
.r3-native-tool:hover { background: rgba(233,84,32,.12); color: #c34113; }
.r3-native-tool .r3-ico svg { width: 14px; height: 14px; }
.r3-native-body { flex: 1; overflow: auto; padding: 16px 18px 18px; min-height: 0; }
.r3-native-resize {
  position: absolute; right: 2px; bottom: 2px; width: 14px; height: 14px;
  cursor: nwse-resize; opacity: .35;
}
.r3-native-resize::after {
  content: ''; position: absolute; right: 3px; bottom: 3px; width: 8px; height: 8px;
  border-right: 2px solid #999; border-bottom: 2px solid #999; border-radius: 0 0 2px 0;
}
.r3-native-minibar {
  position: fixed; bottom: 78px; left: 50%; transform: translateX(-50%);
  z-index: 9050; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;
  max-width: min(96vw, 720px); pointer-events: auto;
}
.r3-native-minibar:empty { display: none; }
.r3-native-min-chip {
  padding: 8px 14px; border-radius: 999px; background: #fff; border: 1px solid rgba(0,0,0,.1);
  font-size: 12px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,.1);
}
.r3-native-min-chip:hover { border-color: #E95420; color: #c34113; }
.r3-native-files .row { display: flex; align-items: center; gap: 10px; }
.r3-native-body { padding: 16px 18px 18px; }
.r3-native-files .row {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px;
  border: 0; border-radius: 10px; background: transparent; text-align: left;
  font: inherit; cursor: pointer;
}
.r3-native-files .row:hover { background: #f5f5f5; }
.r3-native-cmd {
  display: block; width: 100%; margin-bottom: 8px; padding: 12px 14px; border-radius: 12px;
  border: 1px solid rgba(0,0,0,.08); background: #fafafa; font: inherit; text-align: left;
  cursor: pointer;
}
.r3-native-cmd:hover { border-color: #E95420; }
.r3-native-kv { display: grid; gap: 8px; font-size: 13px; }
.r3-native-kv div { padding: 10px 12px; background: #fafafa; border-radius: 10px; }
.r3-notify {
  margin: 0 22px 12px; padding: 12px 14px; border-radius: 14px; background: #fff;
  border: 1px solid rgba(0,0,0,.08);
}
.r3-notify h4 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: #8a8a8a; }
.r3-notify-item { font-size: 12px; padding: 6px 0; border-top: 1px solid rgba(0,0,0,.06); color: #444; }
.r3-notify-item.warn { color: #c0392b; }
.r3-plane-card {
  padding: 12px 14px; border-radius: 14px; background: #fafafa; border: 1px solid rgba(0,0,0,.08);
  margin-bottom: 10px; font-size: 13px;
}
.r3-plane-card b { display: block; margin-bottom: 6px; font-size: 14px; }
.r3-plane-meta { font-size: 11px; color: #8a8a8a; margin: 0 0 10px; line-height: 1.4; }
.r3-plane-slider {
  width: 100%; margin: 8px 0; accent-color: #E95420; cursor: pointer;
}
.r3-plane-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.r3-plane-btn {
  flex: 1; min-width: 88px; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(0,0,0,.1);
  background: #fff; font: inherit; font-size: 12px; cursor: pointer;
}
.r3-plane-btn:hover { border-color: #E95420; }
.r3-plane-btn.on { background: #fff5f0; border-color: #E95420; color: #c34113; font-weight: 600; }
.r3-plane-list { margin: 0; padding: 0; list-style: none; }
.r3-plane-list li { padding: 6px 0; border-top: 1px solid rgba(0,0,0,.06); font-size: 12px; }
.r3-spaces-bar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 9050; pointer-events: auto;
  display: flex; align-items: center; gap: 8px; padding: 6px 12px;
  background: rgba(10,10,15,.88); border-bottom: 1px solid rgba(255,255,255,.08);
  backdrop-filter: blur(12px);
}
.r3-spaces-bar button {
  border: 0; background: rgba(255,255,255,.08); color: #e5e5ea; border-radius: 10px;
  padding: 6px 12px; font: inherit; font-size: 12px; cursor: pointer;
}
.r3-spaces-bar button.active { background: #E95420; color: #fff; font-weight: 600; }
.r3-spaces-bar .r3-mission-btn { margin-left: auto; }
.r3-mission-overlay {
  position: fixed; inset: 0; z-index: 9200; pointer-events: auto;
  background: rgba(0,0,0,.55); backdrop-filter: blur(8px);
  display: none; align-items: center; justify-content: center; padding: 24px;
}
.r3-mission-overlay.open { display: flex; }
.r3-mission-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px; width: min(900px, 96vw);
}
.r3-mission-card {
  background: #fff; border-radius: 16px; padding: 16px; min-height: 120px;
  box-shadow: 0 12px 32px rgba(0,0,0,.2); cursor: pointer;
}
.r3-mission-card h4 { margin: 0 0 8px; font-size: 14px; }
.r3-mission-card p { margin: 0; font-size: 12px; color: #666; }
"""

from analytics.r3_icons import R3_ICON_CSS as _R3_ICON_CSS, render_icons_js as _render_icons_js  # noqa: E402

NATIVE_CSS = NATIVE_CSS + _R3_ICON_CSS

NATIVE_JS = """
window._r3Wins = window._r3Wins || { z: 9100, focused: null, layouts: {}, order: [] };
const R3_WIN_STORE = 'r3_win_layout_v1';
function r3WinLoadLayouts() {
  try {
    const raw = localStorage.getItem(R3_WIN_STORE);
    if (raw) window._r3Wins.layouts = JSON.parse(raw) || {};
  } catch (e) { window._r3Wins.layouts = {}; }
}
function r3WinSaveLayouts() {
  try { localStorage.setItem(R3_WIN_STORE, JSON.stringify(window._r3Wins.layouts || {})); } catch (e) {}
}
window.r3Spaces = window.r3Spaces || {
  active: 0, count: 4,
  labels: ['Haupt', 'Arbeit', 'Forschung', 'System'],
  missionVisible: false
};
function r3SpacesEnsureBar() {
  let bar = document.getElementById('r3-spaces-bar');
  if (bar) return bar;
  bar = document.createElement('div');
  bar.id = 'r3-spaces-bar';
  bar.className = 'r3-spaces-bar';
  (window.r3Spaces.labels || []).forEach((label, idx) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    b.dataset.space = String(idx);
    if (idx === window.r3Spaces.active) b.classList.add('active');
    b.onclick = () => r3SpacesSwitch(idx);
    bar.appendChild(b);
  });
  const mission = document.createElement('button');
  mission.type = 'button';
  mission.className = 'r3-mission-btn';
  mission.textContent = 'Mission Control';
  mission.onclick = () => r3MissionControlToggle();
  bar.appendChild(mission);
  document.body.appendChild(bar);
  let ov = document.getElementById('r3-mission-overlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'r3-mission-overlay';
    ov.className = 'r3-mission-overlay';
    ov.onclick = (e) => { if (e.target === ov) r3MissionControlToggle(); };
    document.body.appendChild(ov);
  }
  return bar;
}
function r3SpacesSwitch(idx) {
  window.r3Spaces.active = idx;
  document.querySelectorAll('#r3-spaces-bar button[data-space]').forEach((b) => {
    b.classList.toggle('active', parseInt(b.dataset.space, 10) === idx);
  });
  (window._r3Wins.order || []).forEach((id) => {
    const win = document.getElementById('r3-win-' + id);
    if (!win) return;
    const sp = parseInt(win.dataset.space || '0', 10);
    win.style.display = (sp === idx || win.classList.contains('minimized')) ? '' : 'none';
    if (sp !== idx && !win.classList.contains('minimized')) win.style.display = 'none';
    if (sp === idx) win.style.display = win.classList.contains('minimized') ? 'none' : 'flex';
  });
}
function r3MissionControlToggle() {
  window.r3Spaces.missionVisible = !window.r3Spaces.missionVisible;
  const ov = document.getElementById('r3-mission-overlay');
  if (!ov) return;
  ov.classList.toggle('open', window.r3Spaces.missionVisible);
  if (!window.r3Spaces.missionVisible) return;
  const grid = document.createElement('div');
  grid.className = 'r3-mission-grid';
  (window._r3Wins.order || []).forEach((id) => {
    const L = window._r3Wins.layouts[id] || {};
    const card = document.createElement('div');
    card.className = 'r3-mission-card';
    card.innerHTML = '<h4>' + r3WinEsc(L.title || id) + '</h4><p>Space ' +
      (window.r3Spaces.labels[parseInt(document.getElementById('r3-win-' + id)?.dataset.space || '0', 10)] || '—') + '</p>';
    card.onclick = () => { r3MissionControlToggle(); r3WinRestore(id); r3WinFocus(id); };
    grid.appendChild(card);
  });
  if (!grid.children.length) {
    const empty = document.createElement('p');
    empty.style.color = '#fff';
    empty.textContent = 'Keine Fenster — Native App öffnen';
    grid.appendChild(empty);
  }
  ov.innerHTML = '';
  ov.appendChild(grid);
}
function r3NativeWinEnsureStage() {
  let stage = document.getElementById('r3-native-stage');
  if (!stage) {
    stage = document.createElement('div');
    stage.id = 'r3-native-stage';
    stage.className = 'r3-native-stage';
    document.body.appendChild(stage);
    let mb = document.getElementById('r3-native-minibar');
    if (!mb) {
      mb = document.createElement('div');
      mb.id = 'r3-native-minibar';
      mb.className = 'r3-native-minibar';
      document.body.appendChild(mb);
    }
    r3WinLoadLayouts();
    r3SpacesEnsureBar();
    if (!window._r3WinKeysBound) {
      window._r3WinKeysBound = true;
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && window._r3Wins.focused) {
          r3NativeClose(window._r3Wins.focused);
          e.preventDefault();
        }
      });
    }
    if (!window._r3WinResizeBound) {
      window._r3WinResizeBound = true;
      window.addEventListener('resize', () => {
        (window._r3Wins.order || []).forEach((id) => {
          const win = document.getElementById('r3-win-' + id);
          const L = window._r3Wins.layouts[id];
          if (win && L && !L.minimized && L.snap && L.snap !== 'free') r3WinApplyLayout(win, L);
        });
      });
    }
  }
  return stage;
}
function r3WinEsc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
function r3WinDefaultLayout(winId) {
  const n = (window._r3Wins.order || []).length;
  const off = 24 + (n % 6) * 28;
  const w = Math.min(720, Math.round(window.innerWidth * 0.72));
  const h = Math.min(Math.round(window.innerHeight * 0.72), 560);
  return { x: off, y: off + 32, w: w, h: h, snap: 'free', minimized: false, title: winId };
}
function r3WinApplyLayout(win, layout) {
  const L = layout || r3WinDefaultLayout(win.dataset.winId);
  win.classList.remove('snapped-left', 'snapped-right', 'snapped-max');
  if (L.minimized) { win.classList.add('minimized'); return; }
  win.classList.remove('minimized');
  const pad = 12;
  const snap = L.snap || 'free';
  if (snap === 'left') {
    win.classList.add('snapped-left');
    win.style.left = pad + 'px';
    win.style.top = pad + 'px';
    win.style.width = Math.round((window.innerWidth - pad * 3) / 2) + 'px';
    win.style.height = (window.innerHeight - pad * 2) + 'px';
    return;
  }
  if (snap === 'right') {
    win.classList.add('snapped-right');
    const w = Math.round((window.innerWidth - pad * 3) / 2);
    win.style.left = (window.innerWidth - w - pad) + 'px';
    win.style.top = pad + 'px';
    win.style.width = w + 'px';
    win.style.height = (window.innerHeight - pad * 2) + 'px';
    return;
  }
  if (snap === 'max') {
    win.classList.add('snapped-max');
    win.style.left = pad + 'px';
    win.style.top = pad + 'px';
    win.style.width = (window.innerWidth - pad * 2) + 'px';
    win.style.height = (window.innerHeight - pad * 2) + 'px';
    return;
  }
  win.style.left = Math.max(8, L.x || 40) + 'px';
  win.style.top = Math.max(8, L.y || 48) + 'px';
  win.style.width = Math.max(300, L.w || 720) + 'px';
  win.style.height = Math.max(180, L.h || 480) + 'px';
}
function r3WinPersist(winId) {
  const win = document.getElementById('r3-win-' + winId);
  if (!win || win.classList.contains('minimized')) return;
  const cur = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
  const snap = cur.snap || 'free';
  if (snap === 'left' || snap === 'right' || snap === 'max') {
    window._r3Wins.layouts[winId] = Object.assign({}, cur, { snap: snap, minimized: false });
  } else {
    window._r3Wins.layouts[winId] = {
      x: parseInt(win.style.left, 10) || cur.x,
      y: parseInt(win.style.top, 10) || cur.y,
      w: parseInt(win.style.width, 10) || cur.w,
      h: parseInt(win.style.height, 10) || cur.h,
      snap: 'free', minimized: false, title: cur.title || winId
    };
  }
  r3WinSaveLayouts();
}
function r3WinFocus(winId) {
  window._r3Wins.focused = winId;
  window._r3Wins.z += 1;
  const win = document.getElementById('r3-win-' + winId);
  if (win) {
    win.style.zIndex = String(window._r3Wins.z);
    win.classList.add('focused');
    document.querySelectorAll('.r3-native-win').forEach((el) => {
      if (el.id !== 'r3-win-' + winId) el.classList.remove('focused');
    });
  }
}
function r3WinUpdateMinibar() {
  const mb = document.getElementById('r3-native-minibar');
  if (!mb) return;
  mb.innerHTML = '';
  (window._r3Wins.order || []).forEach((id) => {
    const L = window._r3Wins.layouts[id];
    if (!L || !L.minimized) return;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'r3-native-min-chip';
    chip.textContent = L.title || id;
    chip.onclick = () => r3WinRestore(id);
    mb.appendChild(chip);
  });
}
function r3WinRestore(winId) {
  const L = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
  L.minimized = false;
  window._r3Wins.layouts[winId] = L;
  const win = document.getElementById('r3-win-' + winId);
  if (win) {
    win.classList.remove('minimized');
    r3WinApplyLayout(win, L);
    r3WinFocus(winId);
  }
  r3WinSaveLayouts();
  r3WinUpdateMinibar();
}
function r3WinMinimize(winId) {
  const L = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
  L.minimized = true;
  window._r3Wins.layouts[winId] = L;
  const win = document.getElementById('r3-win-' + winId);
  if (win) win.classList.add('minimized');
  if (window._r3Wins.focused === winId) window._r3Wins.focused = null;
  r3WinSaveLayouts();
  r3WinUpdateMinibar();
}
function r3WinSnap(winId, mode) {
  const L = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
  L.snap = mode;
  L.minimized = false;
  window._r3Wins.layouts[winId] = L;
  const win = document.getElementById('r3-win-' + winId);
  if (win) {
    win.classList.remove('minimized');
    r3WinApplyLayout(win, L);
    r3WinFocus(winId);
  }
  r3WinSaveLayouts();
  r3WinUpdateMinibar();
}
function r3WinToggleMax(winId) {
  const L = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
  r3WinSnap(winId, L.snap === 'max' ? 'free' : 'max');
}
function r3WinWire(win, winId) {
  const head = win.querySelector('.r3-native-head');
  if (head && !head._r3Drag) {
    head._r3Drag = true;
    let sx = 0, sy = 0, ox = 0, oy = 0, dragging = false;
    const onMove = (e) => {
      if (!dragging) return;
      const L = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
      L.snap = 'free';
      L.x = ox + (e.clientX - sx);
      L.y = oy + (e.clientY - sy);
      window._r3Wins.layouts[winId] = L;
      r3WinApplyLayout(win, L);
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      r3WinPersist(winId);
    };
    head.addEventListener('mousedown', (e) => {
      if (e.target.closest('button')) return;
      r3WinFocus(winId);
      const L = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
      if (L.snap && L.snap !== 'free') { L.snap = 'free'; window._r3Wins.layouts[winId] = L; }
      dragging = true;
      sx = e.clientX; sy = e.clientY;
      ox = parseInt(win.style.left, 10) || L.x || 40;
      oy = parseInt(win.style.top, 10) || L.y || 48;
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      e.preventDefault();
    });
  }
  const handle = win.querySelector('.r3-native-resize');
  if (handle && !handle._r3Resize) {
    handle._r3Resize = true;
    let sx = 0, sy = 0, sw = 0, sh = 0, resizing = false;
    const onMove = (e) => {
      if (!resizing) return;
      const L = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
      L.snap = 'free';
      L.w = Math.max(300, sw + (e.clientX - sx));
      L.h = Math.max(180, sh + (e.clientY - sy));
      window._r3Wins.layouts[winId] = L;
      r3WinApplyLayout(win, L);
    };
    const onUp = () => {
      if (!resizing) return;
      resizing = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      r3WinPersist(winId);
    };
    handle.addEventListener('mousedown', (e) => {
      r3WinFocus(winId);
      resizing = true;
      sx = e.clientX; sy = e.clientY;
      sw = parseInt(win.style.width, 10) || 720;
      sh = parseInt(win.style.height, 10) || 480;
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      e.preventDefault();
      e.stopPropagation();
    });
  }
  win.addEventListener('mousedown', () => r3WinFocus(winId));
}
function r3WinMarkup(winId) {
  return '<div class="r3-native-head">' +
    '<div class="r3-native-lights">' +
    '<button type="button" class="r3-native-light r3-native-light--close" title="Schließen" aria-label="Schließen" onclick="r3NativeClose(\\'' + winId + '\\')"></button>' +
    '<button type="button" class="r3-native-light r3-native-light--min" title="Minimieren" aria-label="Minimieren" onclick="r3WinMinimize(\\'' + winId + '\\')"></button>' +
    '<button type="button" class="r3-native-light r3-native-light--max" title="Vollbild" aria-label="Vollbild" onclick="r3WinToggleMax(\\'' + winId + '\\')"></button>' +
    '</div>' +
    '<h3 class="r3-native-title"></h3>' +
    '<div class="r3-native-tools">' +
    '<button type="button" class="r3-native-tool" title="Links andocken" onclick="r3WinSnap(\\'' + winId + '\\',\\'left\\')">' + r3IconHtml('snap-left') + '</button>' +
    '<button type="button" class="r3-native-tool" title="Rechts andocken" onclick="r3WinSnap(\\'' + winId + '\\',\\'right\\')">' + r3IconHtml('snap-right') + '</button>' +
    '</div></div><div class="r3-native-body"></div><div class="r3-native-resize" aria-hidden="true"></div>';
}
function r3NativeClose(winId) {
  if (!winId) winId = window._r3Wins.focused;
  if (!winId) {
    const legacy = document.getElementById('r3-native-backdrop');
    if (legacy) { legacy.classList.remove('open'); legacy.innerHTML = ''; }
    return;
  }
  const win = document.getElementById('r3-win-' + winId);
  if (win) win.remove();
  delete window._r3Wins.layouts[winId];
  window._r3Wins.order = (window._r3Wins.order || []).filter((id) => id !== winId);
  if (window._r3Wins.focused === winId) window._r3Wins.focused = null;
  r3WinSaveLayouts();
  r3WinUpdateMinibar();
}
function r3NativeShell(title, inner, opts) {
  opts = opts || {};
  const winId = opts.id || ('win-' + Date.now());
  const stage = r3NativeWinEnsureStage();
  let win = document.getElementById('r3-win-' + winId);
  let layout = window._r3Wins.layouts[winId] || r3WinDefaultLayout(winId);
  layout.title = title;
  layout.minimized = false;
  window._r3Wins.layouts[winId] = layout;
  if (!window._r3Wins.order.includes(winId)) window._r3Wins.order.push(winId);
  if (win) {
    const body = win.querySelector('.r3-native-body');
    if (body) body.innerHTML = inner;
    const t = win.querySelector('.r3-native-title');
    if (t) t.textContent = title;
    win.classList.remove('minimized');
    r3WinApplyLayout(win, layout);
    r3WinFocus(winId);
    r3WinUpdateMinibar();
    if (opts.afterBind) opts.afterBind(win);
    return winId;
  }
  win = document.createElement('div');
  win.id = 'r3-win-' + winId;
  win.className = 'r3-native-win';
  win.dataset.winId = winId;
  win.dataset.space = String(window.r3Spaces.active || 0);
  win.innerHTML = r3WinMarkup(winId);
  const tNew = win.querySelector('.r3-native-title');
  if (tNew) tNew.textContent = title;
  win.querySelector('.r3-native-body').innerHTML = inner;
  r3WinApplyLayout(win, layout);
  stage.appendChild(win);
  r3WinWire(win, winId);
  r3WinFocus(winId);
  r3WinSaveLayouts();
  r3WinUpdateMinibar();
  if (opts.afterBind) opts.afterBind(win);
  r3SpacesSwitch(window.r3Spaces.active || 0);
  return winId;
}
async function r3NativeOpen(appId) {
  const map = {
    files: () => r3NativeFiles(''),
    terminal: () => r3NativeTerminal(),
    settings: () => r3NativeSettings(),
    calculator: () => r3NativeCalculator(),
    screenshot: () => r3NativeScreenshot(),
    apps: () => r3NativePanel('apps', 'Programme'),
    network: () => r3NativePanel('network', 'Netzwerk'),
    display: () => r3NativePanel('display', 'Bildschirm'),
    power: () => r3NativePanel('power', 'Energie'),
    updates: () => r3NativePanel('updates', 'Updates'),
    lock: () => r3NativeLock()
  };
  const opener = map[appId];
  if (!opener) {
    r3FusionToast('Keine native App: ' + appId, false);
    return;
  }
  try { opener(); } catch (e) {
    r3FusionToast('Fenster konnte nicht geöffnet werden', false);
    return;
  }
  fetch('/api/desktop/native?app=' + encodeURIComponent(appId), { cache: 'no-store' })
    .then((r) => r.json())
    .then((j) => { if (!j.ok) r3FusionToast(j.error_de || 'App nicht verfügbar', false); })
    .catch(() => {});
}
function r3NativeFilesBind(winId) {
  const root = document.getElementById('r3-win-' + (winId || 'files'));
  if (!root) return;
  root.querySelectorAll('.r3-native-files .row[data-r3-idx]').forEach((btn) => {
    btn.onclick = () => {
      const e = (window._r3FileEntries || [])[parseInt(btn.getAttribute('data-r3-idx') || '-1', 10)];
      if (!e) return;
      if (e.kind === 'dir') r3NativeFilesSub(e.name);
      else r3NativeOpenPath(e.path);
    };
  });
}
function r3NativeNetworkBind() {
  const root = document.getElementById('r3-win-network');
  if (!root) return;
  root.querySelectorAll('[data-r3-wifi-idx]').forEach((btn) => {
    btn.onclick = () => {
      const n = (window._r3WifiNetworks || [])[parseInt(btn.getAttribute('data-r3-wifi-idx') || '-1', 10)];
      if (n && n.ssid) r3NativeWifiConnect(n.ssid);
    };
  });
}
async function r3NativeProjectFiles(sub) {
  const r = await fetch('/api/desktop/project-files?path=' + encodeURIComponent(sub || ''), { cache: 'no-store' });
  const j = await r.json();
  if (!j.ok) { r3FusionToast(j.error_de || 'Fehler', false); return; }
  let html = '<p style="margin:0 0 10px;color:#8a8a8a"><button type="button" class="row" onclick="r3NativeFiles(\\'\\')">~ Home</button> · Projekt/' + (j.relative_de === '/' ? '' : j.relative_de) + '</p><div class="r3-native-files">';
  if (j.parent_rel !== undefined && j.relative_de !== '/') {
    html += '<button type="button" class="row" onclick="r3NativeProjectFiles(\\'' + (j.parent_rel || '') + '\\')">' + r3IconHtml('chevron-left', 'r3-ico r3-native-row-ico') + ' Überordner</button>';
    window._r3ProjectParentRel = j.parent_rel;
  }
  window._r3FileEntries = j.entries || [];
  window._r3FileEntries.forEach((e, i) => {
    const ic = r3IconHtml(e.kind === 'dir' ? 'folder' : 'file', 'r3-ico r3-native-row-ico');
    const name = r3WinEsc(e.name || '');
    html += '<button type="button" class="row" data-r3-idx="' + i + '">' + ic + '<span>' + name + '</span></button>';
  });
  html += '</div>';
  window._r3FilesSub = sub || '';
  window._r3FilesScope = 'project';
  r3NativeShell('Arbeitsbaum', html, { id: 'files', afterBind: () => r3NativeFilesBind('files') });
}
async function r3NativeFiles(sub) {
  const r = await fetch('/api/desktop/files?path=' + encodeURIComponent(sub || ''), { cache: 'no-store' });
  const j = await r.json();
  if (!j.ok) { r3FusionToast(j.error_de || 'Fehler', false); return; }
  let html = '<p style="margin:0 0 10px;color:#8a8a8a"><button type="button" class="row" onclick="r3NativeProjectFiles(\\'\\')">Projekt</button> · ~/' + (j.relative_de === '~' ? '' : j.relative_de) + '</p><div class="r3-native-files">';
  if (j.parent_rel !== undefined && j.relative_de !== '~') {
    html += '<button type="button" class="row" onclick="r3NativeFilesParent()">' + r3IconHtml('chevron-left', 'r3-ico r3-native-row-ico') + ' Überordner</button>';
    window._r3FilesParentRel = j.parent_rel;
  }
  window._r3FileEntries = j.entries || [];
  window._r3FileEntries.forEach((e, i) => {
    const ic = r3IconHtml(e.kind === 'dir' ? 'folder' : 'file', 'r3-ico r3-native-row-ico');
    const name = r3WinEsc(e.name || '');
    html += '<button type="button" class="row" data-r3-idx="' + i + '">' + ic + '<span>' + name + '</span></button>';
  });
  html += '</div>';
  window._r3FilesSub = sub || '';
  window._r3FilesScope = 'home';
  r3NativeShell('Dateien', html, { id: 'files', afterBind: () => r3NativeFilesBind('files') });
}
function r3NativeFilesSub(name) {
  const base = window._r3FilesSub || '';
  const next = base ? base + '/' + name : name;
  if (window._r3FilesScope === 'project') r3NativeProjectFiles(next);
  else r3NativeFiles(next);
}
function r3NativeFilesParent() {
  if (window._r3FilesScope === 'project') r3NativeProjectFiles(window._r3ProjectParentRel || '');
  else r3NativeFiles(window._r3FilesParentRel || '');
}
async function r3NativeOpenPath(path) {
  const pr = await fetch('/api/desktop/preview?path=' + encodeURIComponent(path), { cache: 'no-store' });
  const pj = await pr.json();
  if (pj.ok && pj.preview) {
    if (pj.preview_kind === 'image' && pj.content_b64) {
      const img = '<img src="data:' + (pj.mime || 'image/png') + ';base64,' + pj.content_b64 + '" style="max-width:100%;max-height:60vh;border-radius:10px" alt="Vorschau" />';
      r3NativeShell('Vorschau: ' + (pj.filename || ''), img, { id: 'preview' });
      return;
    }
    const pre = document.createElement('pre');
    pre.style.cssText = 'white-space:pre-wrap;font-size:12px;max-height:50vh;overflow:auto;background:#f5f5f5;padding:10px;border-radius:8px';
    pre.textContent = pj.content || '';
    r3NativeShell('Vorschau: ' + (pj.filename || ''), pre.outerHTML, { id: 'preview' });
    return;
  }
  const r = await fetch('/api/desktop/open?path=' + encodeURIComponent(path), { cache: 'no-store' });
  const j = await r.json();
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
}
async function r3NativeTerminal() {
  const html = '<p style="font-size:12px;color:#8a8a8a">Freigegebene Befehle — alles in R3, kein GNOME nötig.</p>' +
    '<input id="r3-term-cmd" style="width:100%;padding:10px;border-radius:10px;border:1px solid #ddd;margin-bottom:8px" placeholder="python3 tools/ai_kernel.py status" />' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeTermExec()">Ausführen</button>' +
    '<pre id="r3-term-out" style="font-size:11px;max-height:200px;overflow:auto;background:#f5f5f5;padding:8px;border-radius:8px"></pre>' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeTermRun(\\'cockpit\\')">Cockpit</button>' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeTermRun(\\'trading-day\\')">Trading-Day</button>';
  r3NativeShell('Terminal', html, { id: 'terminal' });
}
async function r3NativeTermExec() {
  const cmd = (document.getElementById('r3-term-cmd') || {}).value || '';
  const r = await fetch('/api/desktop/run', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({command: cmd}) });
  const j = await r.json();
  const out = document.getElementById('r3-term-out');
  if (out) out.textContent = j.output || j.error_de || '';
}
async function r3NativeTermRun(id) {
  const r = await fetch('/api/desktop/terminal?action=' + encodeURIComponent(id), { cache: 'no-store' });
  const j = await r.json();
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
}
async function r3NativeSettings() {
  const r = await fetch('/api/desktop/settings', { cache: 'no-store' });
  const j = await r.json();
  if (!j.ok) return;
  const s = j.settings || j;
  const sa = s.step_a || {};
  const html = '<div class="r3-native-kv">' +
    '<div><b>Hub</b><br>' + (s.hub_de || '') + '</div>' +
    '<div><b>Projekt</b><br>' + (s.project_root || '') + '</div>' +
    '<div><b>Schritt A</b><br>' + (sa.step_a_percent || 0) + '%</div>' +
    '<div><b>Supremacy</b><br>' + (s.supremacy_headline_de || '—') + '</div>' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeOpen(\\'network\\')">Netzwerk</button>' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeGnomeSettings(\\'sound\\')">Ton (Ubuntu)</button>' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeGnomeSettings(\\'bluetooth\\')">Bluetooth (Ubuntu)</button>' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeOpen(\\'updates\\')">Updates</button>' +
    '<button type="button" class="r3-native-cmd" onclick="r3NativeSessionPanel()">Sitzung</button>' +
    '</div>';
  r3NativeShell('R3 Einstellungen', html, { id: 'settings' });
}
async function r3PlaneAction(action, payload) {
  const r = await fetch('/api/desktop/plane', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ action: action }, payload || {}))
  });
  return r.json();
}
function r3PlaneEsc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
async function r3NativeGnomeSettings(page) {
  const r = await fetch('/api/desktop/launch?feature=settings', { cache: 'no-store' });
  const j = await r.json();
  if (!j.ok) { r3FusionToast(j.error_de || 'Ubuntu Einstellungen nicht verfügbar', false); return; }
  r3FusionToast('Ubuntu Einstellungen — Ton/Bluetooth dort', true);
}
function r3RenderNetworkPlane(j) {
  let html = '<p class="r3-plane-meta">' + r3PlaneEsc(j.headline_de) + '</p>';
  html += '<div class="r3-plane-card"><b>WLAN</b><div class="r3-plane-row">';
  html += '<button type="button" class="r3-plane-btn' + (j.wifi_enabled ? ' on' : '') + '" onclick="r3NativeWifi(true)">WLAN ein</button>';
  html += '<button type="button" class="r3-plane-btn' + (!j.wifi_enabled ? ' on' : '') + '" onclick="r3NativeWifi(false)">WLAN aus</button>';
  html += '</div></div>';
  if ((j.wifi_networks || []).length) {
    window._r3WifiNetworks = j.wifi_networks || [];
    html += '<div class="r3-plane-card"><b>Netze in Reichweite</b><ul class="r3-plane-list">';
    j.wifi_networks.forEach((n, i) => {
      const mark = n.active ? (' ' + r3IconHtml('check', 'r3-ico r3-ico--sm')) : '';
      const btn = n.active ? '' : '<button type="button" class="r3-plane-btn" style="margin-top:4px" data-r3-wifi-idx="' + i + '">Verbinden</button>';
      html += '<li>' + r3PlaneEsc(n.ssid) + ' · ' + (n.signal_pct || 0) + '%' + mark + btn + '</li>';
    });
    html += '</ul></div>';
  }
  if ((j.devices || []).length) {
    html += '<div class="r3-plane-card"><b>Geräte</b><ul class="r3-plane-list">';
    j.devices.forEach(d => { html += '<li>' + r3PlaneEsc(d.device) + ' · ' + r3PlaneEsc(d.state) + '</li>'; });
    html += '</ul></div>';
  }
  html += '<p class="r3-plane-meta">' + r3PlaneEsc(j.future_de || '') + '</p>';
  return html;
}
function r3RenderDisplayPlane(j) {
  let html = '<p class="r3-plane-meta">' + r3PlaneEsc(j.headline_de) + (j.wayland ? ' · Wayland' : '') + '</p>';
  if ((j.outputs || []).length) {
    html += '<div class="r3-plane-card"><b>Ausgänge</b><ul class="r3-plane-list">';
    j.outputs.forEach(o => {
      const st = o.connected ? (r3IconHtml('check', 'r3-ico r3-ico--sm') + ' ' + (o.resolution || '')) : 'getrennt';
      html += '<li><b>' + r3PlaneEsc(o.name) + '</b> — ' + r3PlaneEsc(st) + '</li>';
    });
    html += '</ul></div>';
  } else {
    html += '<div class="r3-plane-card"><p>Keine xrandr-Info — evtl. reines Wayland.</p></div>';
  }
  return html;
}
function r3RenderSessionPlane(j) {
  let html = '<p class="r3-plane-meta">' + r3PlaneEsc(j.headline_de) + '</p>';
  html += '<div class="r3-plane-card"><b>Sitzung</b>';
  html += '<p style="margin:6px 0 0;font-size:12px">ID: ' + r3PlaneEsc(j.session_id) + ' · ' + r3PlaneEsc(j.session_type) + '</p>';
  html += '<p style="margin:4px 0 0;font-size:12px">Status: ' + r3PlaneEsc(j.session_state) + '</p></div>';
  html += '<div class="r3-plane-row">';
  html += '<button type="button" class="r3-plane-btn" onclick="r3NativeSessionLock()">Sperren</button>';
  html += '<button type="button" class="r3-plane-btn" onclick="r3NativeSessionLogout()">Abmelden</button>';
  html += '</div>';
  if ((j.sessions || []).length) {
    html += '<div class="r3-plane-card"><b>Alle Sitzungen</b><ul class="r3-plane-list">';
    j.sessions.forEach(s => { html += '<li>#' + r3PlaneEsc(s.id) + ' · ' + r3PlaneEsc(s.user) + '</li>'; });
    html += '</ul></div>';
  }
  return html;
}
function r3RenderPowerPlane(j) {
  let html = '<p class="r3-plane-meta">' + r3PlaneEsc(j.headline_de) + '</p>';
  html += '<div class="r3-plane-card"><b>Status</b><p style="margin:6px 0 0">' + r3PlaneEsc(j.status_de || '—') + '</p></div>';
  html += '<div class="r3-plane-row">';
  html += '<button type="button" class="r3-plane-btn" onclick="r3FusionPower(\\'suspend\\', null)">Ruhezustand</button>';
  html += '<button type="button" class="r3-plane-btn" onclick="r3NativeSessionPanel()">Sitzung</button>';
  html += '<button type="button" class="r3-plane-btn" onclick="r3FusionPower(\\'lock\\', null)">Sperren</button>';
  html += '</div>';
  return html;
}
async function r3NativePanel(id, title) {
  const r = await fetch('/api/desktop/panel?panel=' + encodeURIComponent(id), { cache: 'no-store' });
  const j = await r.json();
  if (!j.ok) { r3FusionToast(j.error_de || 'Fehler', false); return; }
  let body = '';
  if (id === 'apps' && j.apps) {
    body = '<div class="r3-native-files">';
    (j.apps || []).forEach(a => { body += '<div class="row">' + r3IconHtml('package', 'r3-ico r3-native-row-ico') + '<span>' + (a.label_de || a.id) + '</span></div>'; });
    body += '</div>';
    r3NativeShell(title, body, { id: id });
    return;
  }
  if (id === 'updates' && j.packages) {
    body = '<p><b>' + (j.count || 0) + ' Pakete</b></p><pre style="font-size:10px;max-height:40vh;overflow:auto;background:#f5f5f5;padding:10px;border-radius:8px">';
    body += (j.packages || []).join('\\n') + '</pre><p style="font-size:11px;color:#888">' + (j.hint_de || '') + '</p>';
    r3NativeShell(title, body, { id: id });
    return;
  }
  if (id === 'network' && j.plane_ui) {
    r3NativeShell(title, r3RenderNetworkPlane(j), { id: id, afterBind: () => r3NativeNetworkBind() });
    return;
  }
  if (id === 'power' && j.plane_ui) {
    r3NativeShell(title, r3RenderPowerPlane(j), { id: id });
    return;
  }
  if (id === 'display' && j.plane_ui) {
    r3NativeShell(title, r3RenderDisplayPlane(j), { id: id });
    return;
  }
  if (id === 'session' && j.plane_ui) {
    r3NativeShell(title, r3RenderSessionPlane(j), { id: id });
    return;
  }
  body = '<pre style="font-size:11px;white-space:pre-wrap;max-height:50vh;overflow:auto;background:#f5f5f5;padding:10px;border-radius:8px">';
  body += (j.raw || j.raw_short || j.headline_de || JSON.stringify(j, null, 2)) + '</pre>';
  r3NativeShell(title, body, { id: id });
}
async function r3NativeWifi(on) {
  const j = await r3PlaneAction('wifi_radio', { enabled: !!on });
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
  if (j.ok) r3NativePanel('network', 'Netzwerk');
}
async function r3NativeWifiConnect(ssid) {
  const j = await r3PlaneAction('wifi_connect', { ssid: ssid });
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
  if (j.ok) r3NativePanel('network', 'Netzwerk');
}
async function r3NativeSessionPanel() {
  const r = await fetch('/api/desktop/panel?panel=session', { cache: 'no-store' });
  const j = await r.json();
  if (j.ok && j.plane_ui) r3NativeShell('Sitzung', r3RenderSessionPlane(j), { id: 'session' });
}
async function r3NativeSessionLock() {
  const j = await r3PlaneAction('lock', {});
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
  r3NativeClose();
}
async function r3NativeSessionLogout() {
  if (!window.confirm('Wirklich abmelden?')) return;
  const j = await r3PlaneAction('logout', {});
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
}
function r3NativeCalculator() {
  const html = '<div id="r3-calc-display" style="font-size:24px;padding:12px;text-align:right;background:#f0f0f0;border-radius:10px;margin-bottom:10px">0</div>' +
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px">' +
    ['7','8','9','/','4','5','6','*','1','2','3','-','0','.','=','+','C'].map(k =>
      '<button type="button" class="r3-native-cmd" style="margin:0" onclick="r3CalcKey(\\''+k+'\\')">'+k+'</button>').join('') +
    '</div>';
  window._r3Calc = '0';
  r3NativeShell('Rechner', html, { id: 'calculator' });
}
function r3CalcKey(k) {
  if (k === 'C') { window._r3Calc = '0'; }
  else if (k === '=') {
    try { window._r3Calc = String(Function('"use strict";return (' + window._r3Calc + ')')()); }
    catch(e) { window._r3Calc = 'Fehler'; }
  } else { window._r3Calc = window._r3Calc === '0' ? k : window._r3Calc + k; }
  const d = document.getElementById('r3-calc-display');
  if (d) d.textContent = window._r3Calc;
}
async function r3NativeScreenshot() {
  const r = await fetch('/api/desktop/screenshot', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
  const j = await r.json();
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
}
async function r3NativeLock() {
  const r = await fetch('/api/desktop/lock', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
  const j = await r.json();
  r3FusionToast(j.message_de || j.error_de || '', !!j.ok);
  r3NativeClose();
}
const R3_NATIVE_TILES = ['files','terminal','settings','calculator','screenshot','apps','network','display','power','lock','updates','aktien'];
async function r3LaunchDesktopMaybeNative(featureId, btn) {
  if (featureId === 'aktien') return r3LaunchDesktop(featureId, btn);
  if (R3_NATIVE_TILES.includes(featureId) && featureId !== 'aktien') {
    return r3NativeOpen(featureId);
  }
  return r3LaunchDesktop(featureId, btn);
}
""" + _render_icons_js()


def render_notifications_panel(root: Path) -> str:
    doc = build_notifications(root)
    rows = []
    for item in doc.get("items") or []:
        cls = "warn" if item.get("level") == "warn" else ""
        rows.append(
            f'<div class="r3-notify-item {cls}"><b>{_esc(item.get("title_de"))}</b> — {_esc(item.get("body_de"))}</div>'
        )
    if not rows:
        rows.append('<div class="r3-notify-item">Keine Meldungen</div>')
    return f"""
<div class="r3-notify" id="r3-notify-center" aria-label="Mitteilungen">
  <h4>Mitteilungen · Action Center</h4>
  {''.join(rows)}
</div>"""
