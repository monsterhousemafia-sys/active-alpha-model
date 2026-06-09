"""R3 vollständig aktuell — Hub, visuelle GUI, Mirror, Daytrading-Daten."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_full_refresh_policy.json")
_EVIDENCE_REL = Path("evidence/r3_full_refresh_latest.json")
_HUB_PORT = 17890


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_r3_full_refresh(
    root: Path,
    *,
    force: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Hub + GUI-Cache + Mirror + Daytrading-Datenpflege."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    # 1) Hub
    try:
        from tools.preview_hub import ensure_hub_running
        from analytics.hub_runtime import build_health_report

        port = ensure_hub_running(root, port=_HUB_PORT, restart=False)
        rep = build_health_report(root, port=int(port or _HUB_PORT))
        steps.append(
            {
                "id": "hub",
                "ok": bool(rep.get("online")),
                "port": rep.get("port"),
                "detail_de": f"Hub :{rep.get('port')} {'ONLINE' if rep.get('online') else 'OFFLINE'}",
            }
        )
    except Exception as exc:
        steps.append({"id": "hub", "ok": False, "detail_de": str(exc)[:160]})

    # 2) Align + Mirror-HTML + Flow-Kanäle
    try:
        from analytics.r3_runtime_upgrade import align_r3_surface

        align = align_r3_surface(
            root,
            scan_upgrades=True,
            warm_cache=True,
            sync_flow=True,
            persist=True,
            port=_HUB_PORT,
        )
        warm = next((s for s in (align.get("steps") or []) if s.get("step") == "warm_cache"), {})
        flow = next((s for s in (align.get("steps") or []) if s.get("step") == "sync_flow"), {})
        steps.append(
            {
                "id": "align_gui",
                "ok": bool(align.get("ok")),
                "cache_bytes": warm.get("bytes"),
                "fluidity_pct": flow.get("fluidity_pct"),
                "detail_de": str(align.get("confirmation_de") or align.get("headline_de") or "Align OK")[:160],
            }
        )
    except Exception as exc:
        steps.append({"id": "align_gui", "ok": False, "detail_de": str(exc)[:160]})

    # 3) Vollständiger Desktop-Shell-Render (visuell, nicht nur fast)
    try:
        from analytics.desktop_shell_cache import cache_paths, warm_desktop_cache

        nbytes = warm_desktop_cache(
            root, port=_HUB_PORT, fast=False, block=True, live_prep=True
        )
        _, meta_path = cache_paths(root)
        steps.append(
            {
                "id": "desktop_shell",
                "ok": nbytes >= 120,
                "cache_bytes": nbytes,
                "detail_de": f"Desktop-GUI-Cache {nbytes} B" if nbytes else "Desktop-Cache leer",
            }
        )
    except Exception as exc:
        steps.append({"id": "desktop_shell", "ok": False, "detail_de": str(exc)[:160]})

    # 4) Mirror-State für Live-Poll /api/r3/mirror
    try:
        from analytics.r3_mirror_state import build_exec_mirror_state

        mirror = build_exec_mirror_state(root, refresh_scans=True)
        steps.append(
            {
                "id": "mirror_state",
                "ok": bool(mirror.get("ok", True)),
                "headline_de": str(mirror.get("headline_de") or "")[:120],
                "detail_de": str(mirror.get("message_de") or mirror.get("headline_de") or "Mirror OK")[:160],
            }
        )
    except Exception as exc:
        steps.append({"id": "mirror_state", "ok": False, "detail_de": str(exc)[:160]})

    # 5) Leichte Datenpflege (Kernel surface_data — kein Kreislauf-Doppelung)
    try:
        from analytics.r3_ops_kernel import run_ops_pipeline

        surface = run_ops_pipeline(root, phase="surface_data", force=force, persist=False, source="r3_full_refresh")
        surf_ok = sum(1 for s in (surface.get("steps") or []) if s.get("ok"))
        steps.append(
            {
                "id": "daytrading_data",
                "ok": surf_ok >= 1,
                "steps_ok": surf_ok,
                "detail_de": str(surface.get("headline_de") or "Kurse+Snapshot")[:160],
            }
        )
    except Exception as exc:
        steps.append({"id": "daytrading_data", "ok": False, "detail_de": str(exc)[:160]})

    ok_n = sum(1 for s in steps if s.get("ok"))
    gui_ok = all(s.get("ok") for s in steps if s.get("id") in ("hub", "align_gui", "desktop_shell", "mirror_state"))
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": gui_ok and ok_n >= 4,
        "gui_ok": gui_ok,
        "steps_ok": ok_n,
        "steps_total": len(steps),
        "steps": steps,
        "hub_url_de": f"http://127.0.0.1:{_HUB_PORT}/r3",
        "desktop_url_de": f"http://127.0.0.1:{_HUB_PORT}/desktop",
        "headline_de": (
            f"R3 aktuell — GUI + Daten {ok_n}/{len(steps)} OK"
            if gui_ok
            else f"R3 Refresh — GUI oder Daten unvollständig ({ok_n}/{len(steps)})"
        ),
        "command_de": "bash tools/king_ops.sh r3-aktuell",
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
