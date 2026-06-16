"""Stack-Integrität — Hub und R3 getrennt prüfen, fail-closed reparieren.

Kein Champion-Wechsel, keine Orders, kein H1-Backtest.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

from analytics.hub_runtime import DEFAULT_PORT, build_health_report as hub_health
from analytics.hub_runtime import ensure_running, is_healthy
from analytics.r3_runtime import (
    build_health_report as r3_health,
    clear_stale_cockpit_pid,
    default_surface_path,
    is_mirror_api_ready,
    is_surface_page_ready,
    launch_cockpit,
    prepare_session,
    warm_surface_cache,
)

_EVIDENCE_REL = Path("evidence/stack_integrity_latest.json")
_HUB_ATTEMPTS = 2
_MIRROR_RETRY_SEC = 18.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _exec_mirror_primary(root: Path) -> bool:
    """EXEC_MIRROR_ONLY: Hub /r3 ist die operative Oberfläche — Qt-Cockpit optional."""
    try:
        from analytics.local_apps_registry import is_exec_mirror_only

        return bool(is_exec_mirror_only(Path(root)))
    except Exception:
        return False


def _checks_from_reports(
    hub: Dict[str, Any],
    r3: Dict[str, Any],
    *,
    desktop_session: bool,
    exec_mirror: bool = False,
) -> List[Dict[str, Any]]:
    """Desktop-Session: /r3 + Qt kritisch. Headless oder EXEC_MIRROR_ONLY: Hub + Mirror kritisch."""
    ui_optional = not desktop_session or bool(exec_mirror)
    return [
        {
            "id": "hub_online",
            "layer": "hub",
            "ok": bool(hub.get("online")),
            "detail_de": "HTTP /api/health" if hub.get("online") else "Hub offline",
        },
        {
            "id": "hub_login_route",
            "layer": "hub",
            "ok": bool(hub.get("route_login_ok")),
            "detail_de": str(hub.get("route_login_detail") or "—"),
        },
        {
            "id": "r3_mirror_api",
            "layer": "r3",
            "ok": bool(r3.get("mirror_api_ok")),
            "detail_de": "/api/r3/mirror",
        },
        {
            "id": "r3_mirror_state",
            "layer": "r3",
            "ok": bool(r3.get("mirror_state_ok")),
            "detail_de": "Evidence auf Platte",
        },
        {
            "id": "r3_surface_page",
            "layer": "r3",
            "ok": bool(r3.get("surface_page_ok")),
            "detail_de": str(r3.get("surface_path") or "/r3"),
            "warn_only": ui_optional,
        },
        {
            "id": "r3_cockpit",
            "layer": "r3",
            "ok": bool(r3.get("cockpit_running")),
            "detail_de": "Qt-Fenster" if desktop_session else "Qt-Fenster (headless)",
            "warn_only": ui_optional,
        },
    ]


def build_integrity_report(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    desktop_session: Optional[bool] = None,
) -> Dict[str, Any]:
    """Fail-closed: Desktop = alle 6 Checks kritisch; Headless = nur Hub + Mirror."""
    root = Path(root)
    desktop = _has_display() if desktop_session is None else bool(desktop_session)
    exec_mirror = _exec_mirror_primary(root)
    hub = hub_health(root, port=int(port))
    r3 = r3_health(root, port=int(port))
    checks = _checks_from_reports(
        hub, r3, desktop_session=desktop, exec_mirror=exec_mirror
    )

    critical = [c for c in checks if not c.get("warn_only")]
    fail = [c for c in critical if not c.get("ok")]
    warn = [c for c in checks if c.get("warn_only") and not c.get("ok")]

    r3_core = bool(r3.get("mirror_api_ok") and r3.get("mirror_state_ok"))
    r3_ui = bool(r3.get("surface_page_ok") and r3.get("cockpit_running"))
    if desktop and exec_mirror:
        r3_ok = r3_core and bool(r3.get("surface_page_ok"))
    elif desktop:
        r3_ok = r3_core and r3_ui
    else:
        r3_ok = r3_core
    stack_ok = len(fail) == 0
    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "stack_ok": stack_ok,
        "desktop_session": desktop,
        "hub_ok": bool(hub.get("ok")),
        "r3_ok": r3_ok,
        "exec_mirror_only": exec_mirror,
        "port": int(port),
        "checks": checks,
        "failures_de": [f"{c['id']}: {c.get('detail_de')}" for c in fail],
        "warnings_de": [f"{c['id']}: {c.get('detail_de')}" for c in warn],
        "hub": hub,
        "r3": r3,
        "repair_cmd_de": "bash tools/stack_integrity.sh --repair --launch",
    }


def persist_integrity_report(root: Path, doc: Dict[str, Any]) -> Path:
    path = Path(root) / _EVIDENCE_REL
    atomic_write_json(path, doc)
    return path


def ensure_hub_reliable(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    attempts: int = _HUB_ATTEMPTS,
) -> int:
    """Hub mit Retry — zweiter Versuch mit --restart."""
    root = Path(root)
    last_exc: Optional[Exception] = None
    for i in range(max(1, int(attempts))):
        try:
            p = ensure_running(root, port=int(port), restart=(i > 0))
            if is_healthy(int(p)):
                return int(p)
        except Exception as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Hub nicht gesund auf Port {port}")


def ensure_mirror_ready(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    warm: bool = True,
) -> bool:
    """Mirror-API erreichbar — optional Cache-Warmup."""
    root = Path(root)
    if is_mirror_api_ready(int(port)):
        return True
    if not warm:
        return False
    try:
        warm_surface_cache(root, port=int(port), fast=True, block=True, live_prep=False)
    except Exception:
        pass
    deadline = time.monotonic() + _MIRROR_RETRY_SEC
    while time.monotonic() < deadline:
        if is_mirror_api_ready(int(port)):
            return True
        time.sleep(0.25)
    live_prep = True
    try:
        from analytics.r3_hw_software_bond import resolve_r3_runtime_tuning

        live_prep = bool((resolve_r3_runtime_tuning(root).get("cache") or {}).get("warm_live_prep", True))
    except Exception:
        live_prep = True
    try:
        warm_surface_cache(root, port=int(port), fast=True, block=True, live_prep=live_prep)
    except Exception:
        pass
    return is_mirror_api_ready(int(port))


def ensure_surface_ready(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    path: Optional[str] = None,
    warm: bool = True,
) -> bool:
    """GET /r3 liefert HTML — nach Mirror-Cache."""
    root = Path(root)
    surface = path or default_surface_path(root)
    if is_surface_page_ready(int(port), path=surface):
        return True
    if not warm:
        return False
    try:
        warm_surface_cache(root, port=int(port), fast=True, block=True, live_prep=False)
    except Exception:
        pass
    deadline = time.monotonic() + _MIRROR_RETRY_SEC
    while time.monotonic() < deadline:
        if is_surface_page_ready(int(port), path=surface):
            return True
        time.sleep(0.25)
    return is_surface_page_ready(int(port), path=surface)


def repair_stack(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    surface_path: Optional[str] = None,
    launch_cockpit_window: bool = False,
    block: bool = False,
    persist: bool = True,
) -> Dict[str, Any]:
    """Selbstheilung: PID → Hub → Mirror → optional Qt. Fail-closed bei Hub-Ausfall."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    clear_stale_cockpit_pid()
    steps.append({"step": "clear_stale_pid", "ok": True})

    prepare_session(root)
    steps.append({"step": "prepare_session", "ok": True})

    hw_doc: Dict[str, Any] = {}
    try:
        from analytics.r3_hw_software_bond import sync_r3_hw_software_bond

        hw_doc = sync_r3_hw_software_bond(root, persist=True)
        steps.append(
            {
                "step": "hw_software_bond",
                "ok": True,
                "pressure_class": hw_doc.get("pressure_class"),
                "headline_de": hw_doc.get("headline_de"),
            }
        )
    except Exception as exc:
        steps.append({"step": "hw_software_bond", "ok": False, "error_de": str(exc)[:120]})

    hub_port = 0
    try:
        hub_port = ensure_hub_reliable(root, port=int(port))
        steps.append({"step": "ensure_hub", "ok": True, "port": hub_port})
    except Exception as exc:
        steps.append({"step": "ensure_hub", "ok": False, "error_de": str(exc)[:120]})
        doc = build_integrity_report(root, port=int(port))
        doc["repaired"] = False
        doc["steps"] = steps
        if persist:
            persist_integrity_report(root, doc)
        return doc

    align_doc: Dict[str, Any] = {}
    try:
        from analytics.r3_runtime_upgrade import align_r3_surface

        align_doc = align_r3_surface(
            root,
            scan_upgrades=True,
            warm_cache=True,
            sync_flow=False,
            persist=True,
            port=int(hub_port),
        )
        steps.append(
            {
                "step": "align_r3_surface",
                "ok": bool(align_doc.get("ok")),
                "upgrade_pending": bool(align_doc.get("upgrade_pending")),
                "profile_id": align_doc.get("runtime_profile_id"),
            }
        )
    except Exception as exc:
        steps.append({"step": "align_r3_surface", "ok": False, "error_de": str(exc)[:120]})

    path = surface_path or default_surface_path(root)
    mirror_ok = ensure_mirror_ready(root, port=int(hub_port), warm=not bool(align_doc.get("ok")))
    steps.append({"step": "ensure_mirror", "ok": mirror_ok})

    surface_ok = ensure_surface_ready(
        root,
        port=int(hub_port),
        path=path,
        warm=not mirror_ok,
    )
    steps.append({"step": "ensure_surface", "ok": surface_ok})

    launch_doc: Dict[str, Any] = {}
    has_display = _has_display()
    if launch_cockpit_window and has_display and (mirror_ok or surface_ok):
        try:
            from analytics.desktop_shell_cache import warm_desktop_cache

            warm_desktop_cache(root, port=int(hub_port), fast=True, block=True, live_prep=False)
            steps.append({"step": "warm_surface_cache", "ok": True})
        except Exception as exc:
            steps.append({"step": "warm_surface_cache", "ok": False, "error_de": str(exc)[:80]})
    if launch_cockpit_window and has_display and (mirror_ok or surface_ok):
        launch_doc = launch_cockpit(
            root,
            surface_path=path,
            port=int(hub_port),
            block=bool(block),
            require_hub=True,
        )
        steps.append({"step": "launch_cockpit", "ok": bool(launch_doc.get("ok"))})

    doc = build_integrity_report(root, port=int(hub_port), desktop_session=has_display)
    doc["repaired"] = bool(doc.get("stack_ok"))
    doc["steps"] = steps
    if launch_doc:
        doc["launch"] = launch_doc
    if persist:
        persist_integrity_report(root, doc)
    return doc


def verify_or_repair(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    auto_repair: bool = True,
    launch_cockpit_window: bool = False,
    persist: bool = True,
) -> Dict[str, Any]:
    has_display = _has_display()
    doc = build_integrity_report(root, port=int(port), desktop_session=has_display)
    if doc.get("stack_ok"):
        if persist:
            persist_integrity_report(root, doc)
        return doc
    if not auto_repair:
        if persist:
            persist_integrity_report(root, doc)
        return doc
    return repair_stack(
        root,
        port=int(port),
        launch_cockpit_window=bool(launch_cockpit_window),
        persist=bool(persist),
    )
