"""R3 System Plane — Netzwerk, Display, Sitzung (Ton/Bluetooth: Ubuntu GNOME).

Kein eigener Audio-/Bluetooth-Stack — gnome-control-center auf dem System.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CONFIG_REL = Path("control/r3_system_plane.json")
_FUTURE_REL = Path("evidence/r3_linux_future_stack_de.md")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_plane_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {"title_de": "R3 System Plane"}


def _run(cmd: List[str], *, timeout: float = 6.0) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode, out
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _which(*names: str) -> Optional[str]:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _parse_nmcli_wifi(raw: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (raw or "").splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        active, ssid, signal = parts[0], parts[1], parts[2]
        if not ssid:
            continue
        rows.append(
            {
                "active": active == "yes",
                "ssid": ssid,
                "signal_pct": int(signal) if signal.isdigit() else 0,
            }
        )
    return rows


def _parse_nmcli_devices(raw: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (raw or "").splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        rows.append(
            {
                "device": parts[0],
                "type": parts[1],
                "state": parts[2],
                "connected": "connected" in parts[2].lower(),
            }
        )
    return rows


def get_network_state() -> Dict[str, Any]:
    if not _which("nmcli"):
        return {"ok": False, "error_de": "nmcli nicht verfügbar", "backend": "none"}
    _, wifi_on = _run(["nmcli", "radio", "wifi"], timeout=3)
    wifi_enabled = (wifi_on or "").strip().lower() == "enabled"
    _, wifi_raw = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"], timeout=5)
    _, dev_raw = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "dev", "status"], timeout=5)
    _, conn_raw = _run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"], timeout=4)
    active_ssid = ""
    for row in _parse_nmcli_wifi(wifi_raw):
        if row.get("active"):
            active_ssid = str(row.get("ssid") or "")
            break
    connections: List[Dict[str, str]] = []
    for line in (conn_raw or "").splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0]:
            connections.append({"name": parts[0], "type": parts[1] if len(parts) > 1 else "", "device": parts[2] if len(parts) > 2 else ""})
    return {
        "ok": True,
        "backend": "networkmanager",
        "api_de": "D-Bus (asynchron) — nmcli als R3-Adapter",
        "future_de": "libnm/D-Bus bleibt; synchrone API deprecated",
        "wifi_enabled": wifi_enabled,
        "active_ssid": active_ssid or "—",
        "wifi_networks": _parse_nmcli_wifi(wifi_raw)[:12],
        "devices": _parse_nmcli_devices(dev_raw),
        "connections": connections[:6],
        "headline_de": f"Netzwerk · {'WLAN an' if wifi_enabled else 'WLAN aus'}" + (f" · {active_ssid}" if active_ssid and active_ssid != "—" else ""),
    }


def set_wifi_radio(enabled: bool) -> Dict[str, Any]:
    if not _which("nmcli"):
        return {"ok": False, "error_de": "nmcli nicht verfügbar"}
    state = "on" if enabled else "off"
    code, _ = _run(["nmcli", "radio", "wifi", state], timeout=5)
    net = get_network_state()
    return {
        "ok": code == 0,
        "message_de": f"WLAN {'ein' if enabled else 'aus'}",
        "network": net,
    }


def connect_wifi(ssid: str) -> Dict[str, Any]:
    ssid = str(ssid or "").strip()
    if not ssid or not _which("nmcli"):
        return {"ok": False, "error_de": "SSID oder nmcli fehlt"}
    code, out = _run(["nmcli", "dev", "wifi", "connect", ssid], timeout=25)
    net = get_network_state()
    if code != 0 and "secrets" in (out or "").lower():
        return {
            "ok": False,
            "error_de": "Netzwerk braucht Passwort — in Schritt B oder nmcli manuell",
            "network": net,
        }
    return {
        "ok": code == 0,
        "message_de": f"Verbunden mit {ssid}" if code == 0 else (out or "Verbindung fehlgeschlagen")[:120],
        "network": net,
    }


def _parse_xrandr_outputs(raw: str) -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for line in (raw or "").splitlines():
        if " connected" in line or " disconnected" in line:
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            connected = "connected" in line and "disconnected" not in line.split()[1:2]
            res = ""
            if connected:
                for p in parts[1:]:
                    if "x" in p and "+" in p:
                        res = p.split("+")[0]
                        break
            current = {"name": name, "connected": connected, "resolution": res or "—"}
            outputs.append(current)
        elif current and line.strip().startswith("current"):
            m = re.search(r"(\d+)\s*x\s*(\d+)", line)
            if m:
                current["resolution"] = f"{m.group(1)}x{m.group(2)}"
    return outputs


def get_display_state() -> Dict[str, Any]:
    raw = ""
    backend = "unknown"
    if _which("xrandr"):
        _, raw = _run(["xrandr", "--query"], timeout=5)
        backend = "xrandr"
    elif _which("wlr-randr"):
        _, raw = _run(["wlr-randr"], timeout=5)
        backend = "wlr-randr"
    outputs = _parse_xrandr_outputs(raw) if raw else []
    primary = next((o for o in outputs if o.get("connected")), None)
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    headline = "Bildschirm"
    if primary:
        headline = f"Bildschirm · {primary.get('name')} · {primary.get('resolution')}"
    elif wayland:
        headline = "Bildschirm · Wayland"
    return {
        "ok": True,
        "backend": backend,
        "api_de": "xrandr / wlr-randr",
        "future_de": "Wayland compositor APIs — R3 zeigt strukturiert",
        "wayland": wayland,
        "outputs": outputs,
        "primary": primary,
        "headline_de": headline,
    }


def get_session_state() -> Dict[str, Any]:
    if not _which("loginctl"):
        return {"ok": False, "error_de": "loginctl nicht verfügbar", "backend": "none"}
    user = os.environ.get("USER") or ""
    _, self_sess = _run(["loginctl", "show-session", "self", "-p", "Id", "-p", "State", "-p", "Type", "-p", "Remote", "-p", "Name"], timeout=4)
    props: Dict[str, str] = {}
    for line in (self_sess or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    _, list_out = _run(["loginctl", "list-sessions", "--no-legend"], timeout=4)
    sessions: List[Dict[str, str]] = []
    for line in (list_out or "").splitlines()[:8]:
        cols = line.split()
        if len(cols) >= 4:
            sessions.append({"id": cols[0], "uid": cols[1], "user": cols[2], "seat": cols[3]})
    display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return {
        "ok": True,
        "backend": "systemd-logind",
        "api_de": "D-Bus → Varlink (Migration systemd v258+)",
        "future_de": "loginctl wechselt auf Varlink — R3 bleibt kompatibel",
        "user": user,
        "session_id": props.get("Id") or "self",
        "session_state": props.get("State") or "—",
        "session_type": props.get("Type") or "—",
        "graphical": display,
        "sessions": sessions,
        "headline_de": f"Sitzung · {user} · {props.get('State') or 'aktiv'}",
    }


def session_lock() -> Dict[str, Any]:
    if not _which("loginctl"):
        return {"ok": False, "error_de": "loginctl nicht verfügbar"}
    code, _ = _run(["loginctl", "lock-session"], timeout=5)
    return {"ok": code == 0, "message_de": "Sitzung gesperrt" if code == 0 else "Sperren fehlgeschlagen"}


def session_logout() -> Dict[str, Any]:
    user = os.environ.get("USER") or ""
    if _which("loginctl") and user:
        code, _ = _run(["loginctl", "terminate-user", user], timeout=8)
        if code == 0:
            return {"ok": True, "message_de": f"{user} wird abgemeldet (loginctl)"}
    if _which("gnome-session-quit"):
        try:
            subprocess.Popen(
                ["gnome-session-quit", "--logout", "--no-prompt"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {"ok": True, "message_de": "Abmelden (GNOME-Fallback)"}
        except OSError:
            pass
    return {"ok": False, "error_de": "Abmelden nicht verfügbar"}


def get_kernel_stack() -> Dict[str, Any]:
    _, uname = _run(["uname", "-sr"], timeout=2)
    _, arch = _run(["uname", "-m"], timeout=2)
    features: List[str] = []
    if Path("/proc/sys/kernel/unprivileged_bpf_disabled").is_file():
        features.append("eBPF")
    if Path("/proc/sys/fs/nr_open").is_file():
        features.append("io_uring-ready")
    return {
        "ok": True,
        "kernel": uname or "Linux",
        "arch": arch or "—",
        "features": features,
        "future_de": "Rust permanent im Kernel · io_uring+eBPF · sichere I/O-Schicht",
        "headline_de": uname or "Linux",
    }


def get_power_state() -> Dict[str, Any]:
    raw = ""
    if _which("upower"):
        _, raw = _run(["upower", "-i", "/org/freedesktop/UPower/devices/BAT0"], timeout=4)
    if not raw and _which("acpi"):
        _, raw = _run(["acpi", "-b"], timeout=4)
    pct = None
    m = re.search(r"(\d+)%", raw or "")
    if m:
        pct = int(m.group(1))
    status = "Netzteil"
    if "charging" in (raw or "").lower():
        status = "Lädt"
    elif "discharging" in (raw or "").lower():
        status = "Entlädt"
    elif pct is not None:
        status = f"Akku {pct}%"
    return {
        "ok": True,
        "battery_pct": pct,
        "status_de": status,
        "raw_short": (raw or "Keine Akku-Info")[:400],
        "headline_de": f"Energie · {status}",
    }


def plane_status(root: Path, *, domain: Optional[str] = None) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_plane_config(root)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "title_de": cfg.get("title_de"),
        "subtitle_de": cfg.get("subtitle_de"),
        "interaction_de": "Maus · Tastatur · Scroll · Slider — ohne CLI-Kenntnisse",
    }
    dom = str(domain or "").strip().lower()
    if dom in ("", "all", "stack"):
        doc["stack"] = get_kernel_stack()
    if dom in ("", "all", "network"):
        doc["network"] = get_network_state()
    if dom in ("", "all", "session"):
        doc["session"] = get_session_state()
    if dom in ("", "all", "power"):
        doc["power"] = get_power_state()
    if dom in ("", "all", "display"):
        doc["display"] = get_display_state()
    doc["ok"] = True
    doc["plane_ui"] = True
    return doc


def plane_action(root: Path, body: Dict[str, Any]) -> Dict[str, Any]:
    _ = Path(root)
    action = str(body.get("action") or "").strip().lower()
    if action in ("volume", "mute_toggle", "bt_radio", "bluetooth_radio"):
        return {
            "ok": False,
            "error_de": "Ton/Bluetooth — Ubuntu Einstellungen (gnome-control-center)",
            "delegate_exec": ["gnome-control-center", "sound" if "volume" in action or action == "mute_toggle" else "bluetooth"],
        }
    if action == "wifi_radio":
        return set_wifi_radio(bool(body.get("enabled", True)))
    if action == "wifi_connect":
        return connect_wifi(str(body.get("ssid") or ""))
    if action == "lock":
        return session_lock()
    if action == "logout":
        return session_logout()
    return {"ok": False, "error_de": f"Unbekannte Plane-Aktion: {action}"}


# --- R3-native panel adapters (ersetzen rohe CLI-Dumps) ---


def network_panel(root: Path) -> Dict[str, Any]:
    net = get_network_state()
    return {"ok": net.get("ok", True), "panel": "network", "plane_ui": True, **net}


def power_panel(root: Path) -> Dict[str, Any]:
    pwr = get_power_state()
    return {"ok": True, "panel": "power", "plane_ui": True, **pwr}


def lock_session() -> Dict[str, Any]:
    return session_lock()


def display_panel(root: Path) -> Dict[str, Any]:
    _ = root
    disp = get_display_state()
    return {"ok": True, "panel": "display", "plane_ui": True, **disp}


def session_panel(root: Path) -> Dict[str, Any]:
    _ = root
    sess = get_session_state()
    return {"ok": True, "panel": "session", "plane_ui": True, **sess}
