"""R3 Laufzeit — Qt-Cockpit + Exec-Spiegel (Client des Preview-Hub).

Primitives only — Orchestrierung: analytics.stack_integrity
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from analytics.hub_runtime import DEFAULT_PORT, is_healthy, probe_route

DEFAULT_SURFACE_PATH = "/r3"
_MIRROR_PROBE = "/api/r3/mirror"
_MIRROR_PROBE_TIMEOUT = 15.0
_SURFACE_PROBE_TIMEOUT = 2.0
_SURFACE_PAGE_TIMEOUT = 8.0


def default_surface_path(root: Path) -> str:
    root = Path(root)
    try:
        from analytics.r3_surface import canonical_surface_path

        return canonical_surface_path(root)
    except Exception:
        pass
    try:
        from analytics.r3_os_supremacy import load_supremacy

        cfg = load_supremacy(root)
        return str((cfg.get("session") or {}).get("hub_path_kernel_ok") or DEFAULT_SURFACE_PATH)
    except Exception:
        return DEFAULT_SURFACE_PATH


def prepare_session(root: Path) -> None:
    try:
        from analytics.r3_session_manager import ensure_native_session

        ensure_native_session(Path(root))
    except Exception:
        pass
    if os.environ.get("R3_SESSION") == "1":
        try:
            from analytics.r3_os_supremacy import decommission_foreign_autostart, remove_legacy_desktops

            decommission_foreign_autostart(Path(root))
            remove_legacy_desktops(Path(root))
        except Exception:
            pass


def clear_stale_cockpit_pid() -> None:
    from analytics.r3_cockpit_lock import clear_cockpit_pid, read_cockpit_pid

    pid = read_cockpit_pid()
    if pid is None or pid <= 0:
        return
    try:
        os.kill(int(pid), 0)
    except OSError:
        clear_cockpit_pid()


def warm_surface_cache(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    fast: bool = True,
    block: bool = True,
    live_prep: bool = True,
) -> int:
    from analytics.desktop_shell_cache import warm_desktop_cache

    return int(
        warm_desktop_cache(
            Path(root),
            port=int(port),
            fast=bool(fast),
            block=bool(block),
            live_prep=bool(live_prep),
        )
    )


def is_mirror_api_ready(port: int = DEFAULT_PORT) -> bool:
    ok, _ = probe_route(port, _MIRROR_PROBE, timeout=_MIRROR_PROBE_TIMEOUT)
    return ok


def is_surface_page_ready(
    port: int = DEFAULT_PORT,
    path: str = DEFAULT_SURFACE_PATH,
) -> bool:
    ok, _ = probe_route(port, path, timeout=_SURFACE_PAGE_TIMEOUT)
    return ok


def is_cockpit_running() -> bool:
    from analytics.r3_cockpit_lock import is_cockpit_running as _running

    return bool(_running())


def launch_cockpit(
    root: Path,
    *,
    surface_path: Optional[str] = None,
    block: bool = False,
    port: int = DEFAULT_PORT,
    require_hub: bool = True,
) -> Dict[str, Any]:
    """Qt-Cockpit — Hub optional vorab via stack_integrity.ensure_hub_reliable."""
    root = Path(root)
    clear_stale_cockpit_pid()
    path = surface_path or default_surface_path(root)
    if require_hub and not is_healthy(int(port)):
        from analytics.stack_integrity import ensure_hub_reliable

        try:
            ensure_hub_reliable(root, port=int(port))
        except Exception as exc:
            return {
                "ok": False,
                "layer": "r3",
                "surface_path": path,
                "error_de": f"Hub nicht bereit: {exc}"[:200],
            }
    from analytics.r3_cockpit_lock import launch_cockpit_once

    doc = launch_cockpit_once(root, surface_path=path, block=bool(block))
    return {**doc, "layer": "r3", "surface_path": path}


def build_health_report(root: Path, *, port: int = DEFAULT_PORT) -> Dict[str, Any]:
    root = Path(root)
    hub_up = is_healthy(port)
    mirror_ok = is_mirror_api_ready(port) if hub_up else False
    surface_ok = is_surface_page_ready(port) if hub_up else False
    cockpit_ok = is_cockpit_running()
    try:
        from analytics.r3_exec_mirror import build_exec_mirror_state

        state_ok = bool(build_exec_mirror_state(root).get("schema_version"))
    except Exception:
        state_ok = False
    return {
        "ok": hub_up and mirror_ok and state_ok,
        "layer": "r3",
        "port": int(port),
        "hub_online": hub_up,
        "mirror_api_ok": mirror_ok,
        "surface_page_ok": surface_ok,
        "cockpit_running": cockpit_ok,
        "mirror_state_ok": state_ok,
        "surface_path": default_surface_path(root),
        "start_cmd_de": "bash tools/r3_autonomous.sh",
    }
