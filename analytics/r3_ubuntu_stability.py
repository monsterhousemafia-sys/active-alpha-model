"""R3 — Ubuntu/Wayland-Stabilität (Qt WebEngine, Keyring, Cockpit)."""
from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, MutableMapping, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_ubuntu_stability_latest.json")

_CHROMIUM_STABILITY_FLAGS = (
    "--password-store=basic",
    "--disable-features=DBusSecretPortal,HardwareMediaKeyHandling",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _xcb_cursor_available() -> bool:
    for lib in ("libxcb-cursor.so.0", "libxcb-cursor.so"):
        for d in ("/usr/lib/x86_64-linux-gnu", "/usr/lib"):
            if (Path(d) / lib).is_file():
                return True
    return False


def is_ubuntu() -> bool:
    try:
        data = platform.freedesktop_os_release()
        return "ubuntu" in str(data.get("ID", "")).lower() or "ubuntu" in str(
            data.get("ID_LIKE", "")
        ).lower()
    except Exception:
        return Path("/etc/os-release").is_file()


def session_info() -> Dict[str, Any]:
    return {
        "ubuntu": is_ubuntu(),
        "display": os.environ.get("DISPLAY") or "",
        "wayland": os.environ.get("WAYLAND_DISPLAY") or "",
        "xdg_runtime": os.environ.get("XDG_RUNTIME_DIR") or "",
        "desktop_session": os.environ.get("XDG_CURRENT_DESKTOP") or "",
    }


def apply_ubuntu_qt_env(env: Optional[MutableMapping[str, str]] = None) -> Dict[str, str]:
    """Qt WebEngine auf Ubuntu stabilisieren — Keyring-/Wayland-Crashes vermeiden."""
    out: Dict[str, str] = dict(env if env is not None else os.environ)
    flags = [f for f in _CHROMIUM_STABILITY_FLAGS]
    prev = str(out.get("QTWEBENGINE_CHROMIUM_FLAGS") or "").strip()
    if prev:
        flags.insert(0, prev)
    out["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(dict.fromkeys(flags))

    out.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    out.setdefault("QTWEBENGINEPROCESS_PATH", "")

    if os.environ.get("R3_FORCE_XCB") == "1" and _xcb_cursor_available():
        out["QT_QPA_PLATFORM"] = "xcb"
    elif out.get("WAYLAND_DISPLAY") and os.environ.get("R3_FORCE_WAYLAND") == "1":
        out.setdefault("QT_QPA_PLATFORM", "wayland")

    if is_ubuntu() and not out.get("GNOME_KEYRING_CONTROL"):
        out.setdefault("SECRET_SERVICE_DISABLE", "1")

    out.setdefault("AA_LINUX_NATIVE_APP", "1")
    return out


def resolve_fullscreen(
    session_cfg: Dict[str, Any],
    *,
    env: Optional[Dict[str, str]] = None,
) -> bool:
    """Wayland: Fenster statt Vollbild — weniger Compositor-Abstürze."""
    e = env if env is not None else os.environ
    if e.get("R3_FULLSCREEN") == "1":
        return True
    if e.get("R3_FULLSCREEN") == "0":
        return False
    if e.get("WAYLAND_DISPLAY") and e.get("R3_FORCE_FULLSCREEN") != "1":
        return bool(session_cfg.get("start_fullscreen_wayland", False))
    return bool(session_cfg.get("start_fullscreen", True))


def stabilize_stack(
    root: Path,
    *,
    relaunch_cockpit: bool = True,
    restart_hub: bool = False,
) -> Dict[str, Any]:
    """Hub + R3 reparieren, optional Cockpit neu starten (Ubuntu-safe)."""
    root = Path(root)
    steps: list[Dict[str, Any]] = []

    env = apply_ubuntu_qt_env()
    for key, val in env.items():
        if val:
            os.environ[key] = val

    try:
        from analytics.r3_cockpit_lock import clear_cockpit_pid, is_cockpit_running, read_cockpit_pid

        if relaunch_cockpit and is_cockpit_running():
            pid = read_cockpit_pid()
            if pid and pid > 0:
                try:
                    os.kill(int(pid), 15)
                    steps.append({"step": "stop_cockpit", "ok": True, "pid": pid})
                except OSError as exc:
                    steps.append({"step": "stop_cockpit", "ok": False, "error": str(exc)[:80]})
            clear_cockpit_pid()
    except Exception as exc:
        steps.append({"step": "stop_cockpit", "ok": False, "error": str(exc)[:80]})

    if restart_hub:
        try:
            from analytics.hub_runtime import ensure_running

            ensure_running(root, restart=True)
            steps.append({"step": "restart_hub", "ok": True})
        except Exception as exc:
            steps.append({"step": "restart_hub", "ok": False, "error": str(exc)[:80]})

    try:
        from analytics.stack_integrity import repair_stack
        from analytics.r3_runtime import default_surface_path

        doc = repair_stack(
            root,
            surface_path=default_surface_path(root),
            launch_cockpit_window=bool(relaunch_cockpit),
            block=False,
            persist=True,
        )
        steps.append({"step": "repair_stack", "ok": bool(doc.get("stack_ok"))})
    except Exception as exc:
        doc = {"stack_ok": False, "error_de": str(exc)[:200]}
        steps.append({"step": "repair_stack", "ok": False, "error": str(exc)[:80]})

    try:
        subprocess.run(
            ["systemctl", "--user", "reset-failed", "active-alpha-remote-tunnel.service"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        steps.append({"step": "reset_failed_tunnel_unit", "ok": True})
    except Exception as exc:
        steps.append({"step": "reset_failed_tunnel_unit", "ok": False, "error": str(exc)[:60]})

    out = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "session": session_info(),
        "qt_env_applied": {
            "QT_QPA_PLATFORM": env.get("QT_QPA_PLATFORM"),
            "QTWEBENGINE_DISABLE_SANDBOX": env.get("QTWEBENGINE_DISABLE_SANDBOX"),
            "QTWEBENGINE_CHROMIUM_FLAGS": env.get("QTWEBENGINE_CHROMIUM_FLAGS"),
        },
        "stack_ok": bool(doc.get("stack_ok")),
        "launch": doc.get("launch"),
        "steps": steps,
        "headline_de": (
            "Ubuntu R3 stabil — Stack OK"
            if doc.get("stack_ok")
            else "Ubuntu R3 — Reparatur unvollständig"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out
