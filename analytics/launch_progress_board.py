"""Launch-Fortschritt — Status für Ubuntu-Anzeige."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_READINESS_REL = Path("evidence/launch_readiness_latest.json")


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


def _hub_healthy(root: Path) -> bool:
    try:
        from tools.preview_hub import _hub_healthy as probe

        from analytics.preview_federation import federation_config

        port = int(federation_config(root).get("hub_port") or 17890)
        return bool(probe(port))
    except Exception:
        return False


def build_launch_status(root: Path, *, refresh_h1: bool = False, persist: bool = False) -> Dict[str, Any]:
    """Launch-Status — Hub/UI nur lesen, H1 nicht anfassen (h1-watch ist Owner)."""
    root = Path(root)
    h1: Dict[str, Any] = {}
    if refresh_h1:
        try:
            from analytics.h1_governance_status import sync_h1_governance_status

            h1 = sync_h1_governance_status(root, write_readiness=False)
        except Exception:
            h1 = _load_json(root / "control/h1_governance_status.json")
    else:
        h1 = _load_json(root / "control/h1_governance_status.json")

    remote: Dict[str, Any] = {}
    try:
        from analytics.remote_hub_access import remote_access_status

        remote = remote_access_status(root)
    except Exception:
        remote = _load_json(root / "evidence/launch_readiness_latest.json").get("remote") or {}

    cached = _load_json(root / _READINESS_REL)
    blockers = list(cached.get("blockers_de") or [])
    step_b_released = False
    closure_pct = 0
    try:
        from analytics.r3_step_b import is_step_b_released
        from analytics.r3_ubuntu_closure import evaluate_ubuntu_closure

        step_b_released = is_step_b_released(root)
        closure_pct = int(evaluate_ubuntu_closure(root).get("closure_percent") or 0)
    except Exception:
        pass
    h1_pct = int(h1.get("progress_pct") or 0)
    sealed = bool(h1.get("sealed"))
    h1_status = str(h1.get("status") or "").strip()
    seal_optional = False
    try:
        from analytics.h1_seal_policy import is_h1_seal_required

        seal_optional = not is_h1_seal_required(root)
    except Exception:
        pass
    h1_complete = h1_status == "COMPLETE" or h1_pct >= 100
    effective_sealed = sealed or (seal_optional and h1_complete)

    if effective_sealed:
        blockers = [b for b in blockers if not str(b).startswith("h1_sealed:")]
    elif not blockers:
        if not (step_b_released and closure_pct >= 100):
            blockers = ["h1_sealed: H1 RUNNING — noch nicht sealed"]
    remote_ready = bool(remote.get("remote_ready"))
    public_url = str(remote.get("public_base_url") or "").strip()
    stable = bool(remote.get("stable"))

    preview_ok = False
    preview_detail = "Preview noch nicht erzeugt"
    preview_passed = 0
    preview_total = 0
    try:
        from analytics.community_spread_plan import _gate_gui_preview_fresh

        preview_ok, preview_detail = _gate_gui_preview_fresh(root)
        prev_doc = _load_json(root / "evidence/gui_preview_latest.json")
        preview_passed = int(prev_doc.get("passed") or 0)
        preview_total = int(prev_doc.get("total") or 0)
    except Exception:
        pass

    if effective_sealed and remote_ready:
        overall = 100
        phase = "ready"
        headline = "Bereit — öffentlicher Zugang freigegeben"
    elif effective_sealed:
        overall = 92
        phase = "h1_done"
        headline = (
            "Validierung abgeschlossen — Seal optional"
            if seal_optional and not sealed
            else "Validierung abgeschlossen — Remote-Check läuft"
        )
    else:
        overall = max(8, min(88, h1_pct))
        if step_b_released and closure_pct >= 100:
            overall = max(overall, 95)
        phase = "h1_running"
        headline = (
            f"Schritt B aktiv · H1 {h1_pct}% parallel"
            if step_b_released and closure_pct >= 100
            else f"Validierung läuft — {h1_pct}% bis Abschluss"
        )

    hub_ok = _hub_healthy(root)
    from analytics.r3_local_surface import filter_launch_tiles_for_king, is_king_cockpit_local

    king_local = is_king_cockpit_local(root)
    remote_detail = (
        "ULWO unter /download · Mitmachen unter /join"
        if king_local
        else (public_url or "—")
    )
    tiles: List[Dict[str, Any]] = [
        {
            "id": "hub",
            "label_de": "Cockpit",
            "value_de": "Online" if hub_ok else "Offline",
            "ok": hub_ok,
            "detail_de": "Lokal · :17890" if king_local else "R3 · :17890",
        },
        {
            "id": "remote",
            "label_de": "Worker-Einladung" if king_local else "Remote-Zugang",
            "value_de": ("Bereit" if remote_ready else "Aus") if king_local else ("Erreichbar" if remote_ready else "Wartet"),
            "ok": remote_ready,
            "detail_de": remote_detail,
        },
    ]
    if not king_local:
        tiles.append(
            {
                "id": "tunnel",
                "label_de": "Tunnel",
                "value_de": "Stabil" if stable else ("Quick-Tunnel" if remote_ready else "Aus"),
                "ok": remote_ready,
                "detail_de": "Token optional — URL kann nach Neustart wechseln" if not stable else "Stabile URL",
            }
        )
    tiles.extend(
        [
        {
            "id": "h1",
            "label_de": "Validierung",
            "value_de": f"{h1_pct}%" if not effective_sealed else "Abgeschlossen",
            "ok": effective_sealed,
            "detail_de": str(h1.get("detail_de") or h1.get("banner_de") or "—"),
        },
        {
            "id": "preview",
            "label_de": "Systemcheck",
            "value_de": (
                f"{preview_passed}/{preview_total} OK"
                if preview_total
                else ("Frisch" if preview_ok else "Aktualisieren")
            ),
            "ok": preview_ok,
            "detail_de": preview_detail,
        },
        ]
    )
    tiles = filter_launch_tiles_for_king(tiles, root)

    milestones: List[Dict[str, Any]] = [
        {"id": "setup", "label_de": "Grundstein", "done": True},
        {"id": "preview", "label_de": "Systemcheck", "done": preview_ok},
        {"id": "remote", "label_de": "Welt-Zugang", "done": remote_ready},
        {"id": "h1", "label_de": "Validierung", "done": effective_sealed},
        {"id": "launch", "label_de": "Welt-Start", "done": effective_sealed and remote_ready},
    ]

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "phase": phase,
        "headline_de": headline,
        "overall_pct": overall,
        "h1": h1,
        "remote": {
            "public_base_url": public_url or None,
            "remote_ready": remote_ready,
            "stable": stable,
            "tunnel_token_set": bool(remote.get("tunnel_token_set")),
        },
        "blockers_de": blockers,
        "public_launch_ready": effective_sealed and remote_ready,
        "tiles": tiles,
        "milestones": milestones,
        "hub_url": "http://127.0.0.1:17890/",
        "preview_url": "http://127.0.0.1:17890/",
        "king_local_surface": king_local,
        "preview": {
            "ok": preview_ok,
            "passed": preview_passed,
            "total": preview_total,
            "detail_de": preview_detail,
        },
        "join_url": (
            "http://127.0.0.1:17890/join"
            if king_local
            else (f"{public_url.rstrip('/')}/join" if public_url else None)
        ),
    }
    if king_local:
        doc["remote"] = {
            **(doc.get("remote") or {}),
            "public_base_url": "http://127.0.0.1:17890",
            "public_base_url_remote_de": public_url or None,
        }
    if persist:
        atomic_write_json(root / "evidence/launch_progress_latest.json", doc)
    return doc


def open_launch_progress(root: Path) -> Dict[str, Any]:
    """Hub sicherstellen und Fortschritts-URL zurückgeben."""
    root = Path(root)
    try:
        from tools.preview_hub import ensure_hub_running

        port = int(ensure_hub_running(root, restart=False))
    except Exception:
        port = 17890
    build_launch_status(root, persist=True)
    url = f"http://127.0.0.1:{port}/launch"  # Launch + vollständiges Preview-Abbild
    opened = False
    try:
        import subprocess

        subprocess.run(["xdg-open", url], check=False, timeout=4)
        opened = True
    except Exception:
        pass
    return {
        "ok": True,
        "url": url,
        "opened": opened,
        "message_de": "R3 Weltneuheit — Launch bereit",
        "world_novelty_de": "Weltneuheit",
    }
