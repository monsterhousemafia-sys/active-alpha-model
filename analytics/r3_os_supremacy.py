"""R3 OS Supremacy — Ubuntu-Sitzung läuft in R3, Legacy-Oberfläche entfällt."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_os_supremacy.json")
_MARKER_REL = Path(".local/share/r3-os/session_supremacy.json")


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


def load_supremacy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL)
    return doc or {"mode": "takeover", "session": {"browser_app_mode": True}}


def _home() -> Path:
    return Path.home()


def _is_essential(name: str, prefixes: List[str], allow: Set[str]) -> bool:
    if name in allow:
        return True
    low = name.lower()
    return any(low.startswith(str(p).lower()) for p in prefixes)


def _disable_autostart_file(path: Path) -> Path:
    backup = path.with_name(path.name + ".bak-r3")
    if backup.is_file():
        return backup
    path.rename(backup)
    return backup


_R3_DESKTOP_BG = "#0a0a0f"
_BACKGROUND_KEYS = (
    "picture-uri",
    "picture-uri-dark",
    "color-shading-type",
    "primary-color",
    "secondary-color",
    "picture-options",
)


def _gsettings_get(schema: str, key: str) -> str:
    if not shutil.which("gsettings"):
        return ""
    try:
        proc = subprocess.run(
            ["gsettings", "get", schema, key],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (proc.stdout or "").strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _gsettings_run(cmd: List[str]) -> bool:
    if not shutil.which("gsettings"):
        return False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _backup_ubuntu_background() -> None:
    schema = "org.gnome.desktop.background"
    backup = _home() / ".local/share/r3-os/ubuntu_background_backup.json"
    if backup.is_file():
        return
    doc = {key: _gsettings_get(schema, key) for key in _BACKGROUND_KEYS}
    doc["backed_up_at_utc"] = _utc_now()
    backup.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(backup, doc)


def remove_ubuntu_background(*, color: str = _R3_DESKTOP_BG) -> List[str]:
    """Ubuntu-Wallpaper entfernen — einheitlicher R3-Hintergrund."""
    schema = "org.gnome.desktop.background"
    steps: List[str] = []
    if not shutil.which("gsettings"):
        return steps

    _backup_ubuntu_background()
    cmds = [
        ["gsettings", "set", schema, "picture-uri", ""],
        ["gsettings", "set", schema, "picture-uri-dark", ""],
        ["gsettings", "set", schema, "color-shading-type", "solid"],
        ["gsettings", "set", schema, "primary-color", color],
        ["gsettings", "set", schema, "secondary-color", color],
        ["gsettings", "set", schema, "picture-options", "none"],
        ["gsettings", "set", schema, "show-desktop-icons", "false"],
    ]
    for cmd in cmds:
        if _gsettings_run(cmd):
            steps.append(" ".join(cmd[2:]))
    return steps


def _apply_gnome_minimize() -> List[str]:
    """GNOME-UI zurücknehmen — R3 bleibt im Vordergrund."""
    steps: List[str] = []
    cmds = [
        ["gsettings", "set", "org.gnome.shell", "favorite-apps", "[]"],
        ["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "dock-fixed", "false"],
        ["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "autohide", "true"],
        ["gsettings", "set", "org.gnome.shell.extensions.dash-to-dock", "intellihide", "true"],
    ]
    for cmd in cmds:
        if _gsettings_run(cmd):
            steps.append(" ".join(cmd[2:]))
    return steps


def decommission_foreign_autostart(root: Path) -> Dict[str, Any]:
    cfg = load_supremacy(root)
    autostart = _home() / ".config/autostart"
    allow = set(cfg.get("autostart_allowlist") or ["r3-os-session.desktop"])
    prefixes = list(cfg.get("autostart_essential_prefixes") or [])
    legacy = set(cfg.get("legacy_autostart_ids") or [])
    disabled: List[str] = []
    kept: List[str] = []

    if not autostart.is_dir():
        return {"disabled": disabled, "kept": kept}

    for path in sorted(autostart.glob("*.desktop")):
        name = path.name
        if name.endswith(".bak-r3"):
            continue
        if _is_essential(name, prefixes, allow) or name.startswith("r3-"):
            kept.append(name)
            continue
        if name in legacy or not name.startswith("r3-"):
            try:
                disabled.append(str(_disable_autostart_file(path)))
            except OSError:
                pass
    return {"disabled": disabled, "kept": kept}


def remove_legacy_desktops(root: Path) -> List[str]:
    cfg = load_supremacy(root)
    removed: List[str] = []
    ids = list(cfg.get("legacy_desktop_ids") or [])
    for base in (_home() / ".local/share/applications", Path(root), _home() / ".config/autostart"):
        if not base.is_dir():
            continue
        for name in ids:
            p = base / name
            if p.is_file():
                try:
                    p.unlink()
                    removed.append(str(p))
                except OSError:
                    pass
    return removed


def install_r3_native(root: Path) -> Dict[str, Any]:
    """Vollständig native R3-Sitzung — Pfade, Preview, Supremacy."""
    root = Path(root).resolve()
    from analytics.r3_paths import migrate_legacy_share

    paths = migrate_legacy_share()
    supremacy = install_r3_supremacy(root)
    preview = {"ok": False}
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path("python3")
    try:
        proc = subprocess.run(
            [str(py), "tools/run_gui_preview.py", "--backend-only", "--skip-chat", "--force"],
            cwd=str(root),
            check=False,
            timeout=120,
        )
        preview = {"ok": proc.returncode == 0}
    except Exception as exc:
        preview = {"ok": False, "error_de": str(exc)[:120]}
    try:
        from tools.preview_hub import ensure_hub_running

        port = int(ensure_hub_running(root, restart=False))
        preview["hub_port"] = port
    except Exception as exc:
        preview["hub_error_de"] = str(exc)[:120]
    supremacy["native"] = {
        "paths": paths,
        "preview_refresh": preview,
        "cli_de": "r3-cockpit · r3-welt · r3-show",
    }
    return supremacy


def install_r3_supremacy(root: Path) -> Dict[str, Any]:
    """R3 wird zur Sitzung — nur der R3-Stack bleibt als Oberfläche."""
    root = Path(root).resolve()
    cfg = load_supremacy(root)

    from analytics.r3_desktop_os import install_desktop_os

    desktop = install_desktop_os(root)
    autostart = decommission_foreign_autostart(root)
    legacy_removed = remove_legacy_desktops(root)
    gnome_steps: List[str] = []
    if cfg.get("remove_ubuntu_background", True):
        gnome_steps.extend(
            remove_ubuntu_background(color=str(cfg.get("desktop_background_color") or _R3_DESKTOP_BG))
        )
    if cfg.get("gnome_minimize_ui"):
        gnome_steps.extend(_apply_gnome_minimize())

    marker = {
        "schema_version": 1,
        "installed_at_utc": _utc_now(),
        "mode": str(cfg.get("mode") or "takeover"),
        "headline_de": str(cfg.get("headline_de") or "R3 — Ubuntu läuft in dir"),
        "linux_mainline_de": cfg.get("linux_mainline_de"),
        "survives_de": list(cfg.get("survives_de") or []),
        "autostart": autostart,
        "legacy_desktops_removed": legacy_removed,
        "gnome_minimize_applied": gnome_steps,
        "session_env": {"R3_SESSION": "1"},
    }
    share = _home() / ".local/share/r3-os"
    share.mkdir(parents=True, exist_ok=True)
    atomic_write_json(share / "session_supremacy.json", marker)

    return {
        "ok": bool(desktop.get("ok", True)),
        "headline_de": marker["headline_de"],
        "message_de": "Ubuntu läuft jetzt in R3 — alte Oberfläche ist deaktiviert, nur der R3-Stack bleibt.",
        "linux_mainline_de": cfg.get("linux_mainline_de"),
        "desktop": desktop,
        "autostart_disabled": len(autostart.get("disabled") or []),
        "legacy_removed": len(legacy_removed),
        "gnome_tweaks": len(gnome_steps),
        "survives_de": marker["survives_de"],
        "next_de": "Neu anmelden oder: bash tools/r3_session_browser.sh",
    }


def supremacy_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    marker = _load_json(_home() / ".local/share/r3-os/session_supremacy.json")
    cfg = load_supremacy(root)
    return {
        "schema_version": 1,
        "active": bool(marker),
        "mode": cfg.get("mode"),
        "headline_de": cfg.get("headline_de"),
        "marker": marker,
        "r3_session_env": os.environ.get("R3_SESSION") == "1",
    }
