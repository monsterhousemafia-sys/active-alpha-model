"""Terminal-/Desktop-Laufzeit — DISPLAY, XAUTHORITY, DBus automatisch anbinden."""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _uid() -> int:
    return os.getuid()


def _run_user_dir() -> Path:
    return Path(f"/run/user/{_uid()}")


def find_xauthority() -> str:
    env = str(os.environ.get("XAUTHORITY") or "").strip()
    if env and Path(env).is_file():
        return env
    home = Path.home() / ".Xauthority"
    if home.is_file():
        return str(home)
    run_dir = _run_user_dir()
    if run_dir.is_dir():
        for pat in (".mutter-Xwaylandauth.*", ".Xauthority", "gdm/Xauthority"):
            for hit in sorted(glob.glob(str(run_dir / pat))):
                if Path(hit).is_file():
                    return hit
    return ""


def find_dbus_address() -> str:
    env = str(os.environ.get("DBUS_SESSION_BUS_ADDRESS") or "").strip()
    if env:
        return env
    bus = _run_user_dir() / "bus"
    if bus.exists():
        return f"unix:path={bus}"
    return ""


def bootstrap_graphical_env() -> Dict[str, Any]:
    """Hängt die aktive Benutzer-GUI-Session an (Wayland/X11)."""
    applied: List[str] = []
    run_dir = _run_user_dir()
    if run_dir.is_dir():
        os.environ.setdefault("XDG_RUNTIME_DIR", str(run_dir))
        applied.append(f"XDG_RUNTIME_DIR={run_dir}")
    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = ":0"
        applied.append("DISPLAY=:0")
    if not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
        applied.append("WAYLAND_DISPLAY=wayland-0")
    xauth = find_xauthority()
    if xauth:
        os.environ["XAUTHORITY"] = xauth
        applied.append(f"XAUTHORITY={xauth}")
    dbus = find_dbus_address()
    if dbus:
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = dbus
        applied.append("DBUS_SESSION_BUS_ADDRESS")
    return {
        "applied": applied,
        "display": os.environ.get("DISPLAY", ""),
        "xauthority": os.environ.get("XAUTHORITY", ""),
        "dbus": os.environ.get("DBUS_SESSION_BUS_ADDRESS", ""),
        "xdg_runtime_dir": os.environ.get("XDG_RUNTIME_DIR", ""),
    }


def graphical_env_dict() -> Dict[str, str]:
    bootstrap_graphical_env()
    keep = (
        "DISPLAY",
        "XAUTHORITY",
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_RUNTIME_DIR",
        "WAYLAND_DISPLAY",
        "HOME",
        "USER",
        "LOGNAME",
        "PATH",
    )
    env = os.environ.copy()
    return {k: str(env[k]) for k in keep if env.get(k)}


def detect_runtime_context() -> Dict[str, Any]:
    import sys

    bootstrap = bootstrap_graphical_env()
    tty = False
    try:
        tty = os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno())
    except (AttributeError, OSError, ValueError):
        tty = False
    has_x = bool(bootstrap.get("xauthority")) and bool(bootstrap.get("display"))
    has_xclip = shutil.which("xclip") is not None
    has_xdotool = shutil.which("xdotool") is not None
    has_xlib = False
    try:
        from analytics.x11_send import xlib_available

        has_xlib = xlib_available()
    except Exception:
        has_xlib = False
    can_auto = has_x and (has_xdotool or has_xlib or has_x)
    if tty and has_x and has_xdotool:
        source = "interactive_tty_graphical"
        headline = "Interaktives Terminal mit Desktop-Session"
    elif has_x:
        source = "graphical_bootstrap"
        headline = "Desktop-Session angehängt (DISPLAY/XAUTHORITY)"
    else:
        source = "headless"
        headline = "Keine Desktop-Session — nur Dry-run/Vorbereitung"
    return {
        "source": source,
        "headline_de": headline,
        "interactive_tty": tty,
        "graphical": has_x,
        "xclip": has_xclip,
        "xdotool": has_xdotool,
        "xlib": has_xlib,
        "can_auto_send": can_auto,
        "bootstrap": bootstrap,
    }


def shell_export_lines() -> str:
    ctx = detect_runtime_context()
    lines = [
        f'export DISPLAY="{os.environ.get("DISPLAY", "")}"',
    ]
    if os.environ.get("XAUTHORITY"):
        lines.append(f'export XAUTHORITY="{os.environ["XAUTHORITY"]}"')
    if os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        lines.append(f'export DBUS_SESSION_BUS_ADDRESS="{os.environ["DBUS_SESSION_BUS_ADDRESS"]}"')
    return "\n".join(lines)


def emit_runtime_json() -> None:
    import json

    print(json.dumps(detect_runtime_context(), ensure_ascii=False, indent=2))


def run_in_user_graphical_session(command: List[str], *, cwd: Optional[Path] = None, timeout_s: float = 120.0) -> Dict[str, Any]:
    """Führt Befehl in der aktiven User-GUI-Session aus (systemd-run --user)."""
    cwd = Path(cwd or Path.cwd())
    env = graphical_env_dict()
    if shutil.which("systemd-run"):
        unit = f"aa-whatsapp-{os.getpid()}"
        cmd = [
            "systemd-run",
            "--user",
            "--wait",
            "--collect",
            f"--unit={unit}",
            "--working-directory",
            str(cwd),
        ]
        for key, val in env.items():
            cmd.extend(["--setenv", f"{key}={val}"])
        cmd.extend(["--", *command])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
            return {
                "ok": proc.returncode == 0,
                "detail_de": "systemd-run --user" if proc.returncode == 0 else (proc.stderr or proc.stdout)[:200],
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "detail_de": str(exc)[:200]}
    try:
        proc = subprocess.run(command, cwd=str(cwd), env={**os.environ, **env}, capture_output=True, text=True, timeout=timeout_s, check=False)
        return {
            "ok": proc.returncode == 0,
            "detail_de": "direct" if proc.returncode == 0 else (proc.stderr or proc.stdout)[:200],
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail_de": str(exc)[:200]}
