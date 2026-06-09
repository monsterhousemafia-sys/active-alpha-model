"""Linux-Community-Stealth — unauffälliger Login-Autostart (Hub im Hintergrund)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

_EVIDENCE_REL = Path("evidence/r3_community_stealth_latest.json")
_LEGACY_AUTOSTART = "r3-os-session.desktop"
_DEFAULT_STEALTH_ID = "xdg-user-session.desktop"
_DEFAULT_SYSTEMD_UNIT = "xdg-user-session.service"


def load_community_stealth(root: Path) -> Dict[str, Any]:
    from analytics.r3_desktop_os import load_desktop_os

    cfg = load_desktop_os(root)
    raw = cfg.get("community_stealth")
    if not isinstance(raw, dict):
        return {"enabled": False}
    return raw


def community_stealth_enabled(root: Path) -> bool:
    return bool(load_community_stealth(root).get("enabled"))


def session_autostart_filename(root: Path) -> str:
    stealth = load_community_stealth(root)
    if stealth.get("enabled"):
        return str(stealth.get("autostart_desktop_id") or _DEFAULT_STEALTH_ID)
    return _LEGACY_AUTOSTART


def session_autostart_path(root: Path) -> Path:
    return Path.home() / ".config/autostart" / session_autostart_filename(root)


def _stealth_exec_env(root: Path, stealth: Dict[str, Any]) -> str:
    hub_only = stealth.get("hub_only_default", True)
    parts = [f"AA_PROJECT_ROOT={root}"]
    if hub_only:
        parts.append("R3_SESSION_HUB_ONLY=1")
    return "env " + " ".join(parts)


def stealth_desktop_meta(stealth: Dict[str, Any]) -> Dict[str, str]:
    return {
        "name": str(stealth.get("generic_name_de") or "Benutzer-Sitzung"),
        "comment": str(
            stealth.get("generic_comment_de") or "Lokale Sitzungsdienste nach Anmeldung"
        ),
        "icon": str(stealth.get("generic_icon") or "preferences-system"),
        "categories": str(stealth.get("categories") or "Utility;"),
        "keywords": str(stealth.get("keywords") or "session;xdg;desktop"),
        "wm_class": str(stealth.get("wm_class") or "XdgSession"),
    }


def purge_legacy_visible_autostart(root: Path) -> List[str]:
    removed: List[str] = []
    autostart = Path.home() / ".config/autostart"
    stealth_id = session_autostart_filename(root)
    for fname in (_LEGACY_AUTOSTART,):
        if fname == stealth_id:
            continue
        path = autostart / fname
        if path.is_file():
            path.unlink()
            removed.append(str(path))
    return removed


def install_systemd_user_session(root: Path, *, stealth: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stealth = stealth or load_community_stealth(root)
    if not stealth.get("systemd_user_session", True):
        return {"ok": True, "skipped": True, "reason_de": "systemd_user_session deaktiviert"}

    root = Path(root).resolve()
    session_sh = root / "tools/r3_session_autostart.sh"
    if not session_sh.is_file():
        return {"ok": False, "error_de": f"Session-Launcher fehlt: {session_sh}"}

    unit_name = str(stealth.get("systemd_unit") or _DEFAULT_SYSTEMD_UNIT)
    unit_dir = Path.home() / ".config/systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / unit_name
    desc = str(stealth.get("systemd_description_de") or "Lokale Benutzer-Sitzungsdienste")
    env_line = _stealth_exec_env(root, stealth)
    body = f"""[Unit]
Description={desc}
After=graphical-session.target network-online.target
Wants=graphical-session.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={root}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT={root}
ExecStart=/bin/bash -lc '{env_line} {session_sh}'
"""
    unit_path.write_text(body, encoding="utf-8")
    unit_path.chmod(0o644)

    enabled = False
    err = ""
    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=False,
            timeout=15,
            capture_output=True,
        )
        proc = subprocess.run(
            ["systemctl", "--user", "enable", unit_name],
            check=False,
            timeout=15,
            capture_output=True,
            text=True,
        )
        enabled = proc.returncode == 0
        if not enabled:
            err = (proc.stderr or proc.stdout or "")[:160]
    except (OSError, subprocess.TimeoutExpired) as exc:
        err = str(exc)[:160]

    return {
        "ok": True,
        "unit_path": str(unit_path),
        "unit_name": unit_name,
        "enabled": enabled,
        "error_de": err or None,
    }


def scan_community_stealth(root: Path) -> Dict[str, Any]:
    root = Path(root).resolve()
    stealth = load_community_stealth(root)
    enabled = bool(stealth.get("enabled"))
    autostart = session_autostart_path(root)
    legacy = Path.home() / ".config/autostart" / _LEGACY_AUTOSTART
    systemd_unit = str(stealth.get("systemd_unit") or _DEFAULT_SYSTEMD_UNIT)
    systemd_path = Path.home() / ".config/systemd/user" / systemd_unit

    hidden_ok = False
    no_display_ok = False
    generic_name_ok = False
    if autostart.is_file():
        try:
            text = autostart.read_text(encoding="utf-8", errors="ignore")
            hidden_ok = "Hidden=true" in text
            no_display_ok = "NoDisplay=true" in text
            meta = stealth_desktop_meta(stealth)
            generic_name_ok = f"Name={meta['name']}" in text
        except OSError:
            pass

    return {
        "enabled": enabled,
        "autostart_installed": autostart.is_file(),
        "autostart_path": str(autostart),
        "legacy_removed": not legacy.is_file() or legacy == autostart,
        "hidden_from_menus": hidden_ok,
        "no_display": no_display_ok,
        "generic_name": generic_name_ok,
        "systemd_unit": str(systemd_path) if systemd_path.is_file() else None,
        "headline_de": (
            "Community-Stealth aktiv — Hub im Hintergrund"
            if enabled and autostart.is_file()
            else "Community-Stealth aus — sichtbarer R3-Autostart"
        ),
        "ok": (not enabled) or (autostart.is_file() and hidden_ok and no_display_ok),
    }


def install_community_stealth(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Generischer XDG-Autostart + optional systemd — R3 nur Hub-only im Hintergrund."""
    root = Path(root).resolve()
    stealth = load_community_stealth(root)
    if not stealth.get("enabled"):
        return {
            "ok": True,
            "skipped": True,
            "headline_de": "Community-Stealth deaktiviert",
            "message_de": "control/r3_desktop_os.json → community_stealth.enabled=true",
        }

    from analytics.r3_desktop_os import install_session_autostart

    autostart_doc = install_session_autostart(root)
    removed = purge_legacy_visible_autostart(root)
    systemd_doc = install_systemd_user_session(root, stealth=stealth)
    scan = scan_community_stealth(root)

    doc: Dict[str, Any] = {
        "ok": bool(autostart_doc.get("ok")) and scan.get("ok"),
        "autostart": autostart_doc,
        "removed_legacy": removed,
        "systemd": systemd_doc,
        "scan": scan,
        "headline_de": "Linux-Community-Stealth installiert",
        "message_de": (
            f"Login: {session_autostart_filename(root)} (Hidden) · "
            f"Hub-only · systemd={systemd_doc.get('unit_name')}"
        ),
    }
    if persist:
        try:
            from aa_safe_io import atomic_write_json

            atomic_write_json(root / _EVIDENCE_REL, doc)
        except Exception:
            pass
    return doc
