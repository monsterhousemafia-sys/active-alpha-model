"""Welt-Verteilung — Tunnel, Worker-ZIP, H1-Queue für globale Teilnehmer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/world_spread_latest.json")
_HAUS_WELT_REL = Path("evidence/haus_zur_welt_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def activate_house_to_world(
    root: Path,
    *,
    remote_mode: str = "auto",
    force_export: bool = True,
) -> Dict[str, Any]:
    """Haus (LAN/USB) bleibt — zusätzlich Welt über Tunnel-URL + neues ZIP."""
    import shutil

    root = Path(root)
    log: List[str] = []

    from analytics.preview_federation import detect_lan_ip, federation_config, hub_bind_host

    lan = detect_lan_ip()
    port = int(federation_config(root).get("hub_port") or 17890)
    lan_url = f"http://{lan}:{port}" if lan else ""

    try:
        from analytics.alpha_model_local_runtime import enable_world_runtime

        wr = enable_world_runtime(root)
        log.extend(wr.get("changed") or [])
    except Exception as exc:
        out = {"ok": False, "message_de": f"world_runtime: {exc}"[:200], "log": log}
        atomic_write_json(root / _HAUS_WELT_REL, {**out, "updated_at_utc": _utc_now()})
        return out

    from aa_safe_io import atomic_write_json as _aw

    fed_path = root / "control/preview_federation.json"
    fed = federation_config(root)
    fed_updates = {
        "lan_bind": True,
        "bind_host": "0.0.0.0",
        "remote_workers_expected": True,
        "remote_access_mode": "cloudflared",
        "note_de": (
            f"Haus+Welt — LAN {lan or '—'} für USB/LAN, Tunnel-URL für weltweite Worker"
        ),
    }
    for key, value in fed_updates.items():
        if fed.get(key) != value:
            fed[key] = value
            log.append(f"preview_federation:{key}")
    _aw(fed_path, fed)

    try:
        from tools.preview_hub import ensure_hub_running

        ensure_hub_running(root, restart=True)
        log.append(f"hub_bind:{hub_bind_host(root)}")
    except Exception as exc:
        log.append(f"hub: {exc}"[:60])

    remote: Dict[str, Any] = {}
    try:
        from analytics.remote_hub_access import ensure_remote_hub_url, remote_access_status

        remote = ensure_remote_hub_url(root, mode=remote_mode)
        if not remote.get("ok"):
            status = remote_access_status(root)
            out = {
                "ok": False,
                "message_de": str(remote.get("message_de") or "Tunnel fehlgeschlagen"),
                "lan_url": lan_url,
                "remote": remote,
                "status": status,
                "log": log,
            }
            atomic_write_json(root / _HAUS_WELT_REL, {**out, "updated_at_utc": _utc_now()})
            return out
        log.extend(remote.get("changed") or [])
    except Exception as exc:
        out = {"ok": False, "message_de": str(exc)[:200], "lan_url": lan_url, "log": log}
        atomic_write_json(root / _HAUS_WELT_REL, {**out, "updated_at_utc": _utc_now()})
        return out

    export: Dict[str, Any] = {}
    world_zip = ""
    try:
        from analytics.worker_export_sync import ensure_lite_export

        export = ensure_lite_export(root, force=force_export)
        world_zip = str(export.get("lite_zip") or "")
        zip_path = Path(world_zip)
        if world_zip and not zip_path.is_absolute():
            for base in (Path.home(), root.parent):
                cand = base / world_zip
                if cand.is_file():
                    zip_path = cand
                    break
        if world_zip and zip_path.is_file():
            world_copy = root / "evidence/world_worker_LITE.zip"
            world_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(zip_path, world_copy)
            export["world_zip"] = str(world_copy)
            log.append(f"world_zip:{world_copy.name}")
            try:
                home_copy = Path.home() / "world_worker_LITE.zip"
                shutil.copy2(zip_path, home_copy)
                export["home_world_zip"] = str(home_copy)
            except OSError:
                pass
    except Exception as exc:
        export = {"ok": False, "error_de": str(exc)[:120]}

    broadcast: Dict[str, Any] = {}
    try:
        from analytics.community_spread_plan import broadcast_spread

        broadcast = broadcast_spread(root)
        log.append("broadcast")
    except Exception as exc:
        broadcast = {"ok": False, "error_de": str(exc)[:120]}

    from analytics.preview_federation import build_share_package, prepare_worker_bundle_config
    from analytics.remote_hub_access import remote_access_status

    share = build_share_package(root)
    bundle = prepare_worker_bundle_config(root)
    status = remote_access_status(root)
    public_url = str(remote.get("public_base_url") or share.get("share_url") or "").rstrip("/")
    join_url = str(share.get("join_url") or f"{public_url}/join")

    out: Dict[str, Any] = {
        "ok": bool(remote.get("ok") and export.get("ok")),
        "schema_version": 1,
        "activated_at_utc": _utc_now(),
        "headline_de": (
            f"Vom Haus in die Welt — LAN {lan_url or '—'} + {join_url}"
            if remote.get("ok")
            else "Haus→Welt unvollständig"
        ),
        "lan_url": lan_url,
        "lan_join": f"{lan_url}/join" if lan_url else "",
        "public_base_url": public_url,
        "join_url": join_url,
        "bundle_join_url": bundle.get("hub_join_url"),
        "house_zip": str(Path.home() / "glasfaser_NOTFALL_worker_LITE.zip"),
        "world_zip": export.get("world_zip") or world_zip,
        "home_world_zip": export.get("home_world_zip"),
        "tunnel_stable": bool(remote.get("stable")),
        "remote": remote,
        "remote_status": status,
        "export": export,
        "broadcast": broadcast,
        "operator_de": [
            f"Haus (USB/LAN): ~/glasfaser_NOTFALL_worker_LITE.zip → gleiches WLAN",
            f"Welt (Internet): {export.get('home_world_zip') or export.get('world_zip') or world_zip} → WhatsApp/Forum",
            f"Join Welt: {join_url}",
            "Forum: evidence/community_spread_forum_de.txt",
            "WhatsApp: evidence/spread_whatsapp_de.txt",
            (
                "Stabile URL: bash tools/setup_cloudflare_tunnel_token.sh"
                if not remote.get("stable")
                else "Welt-ZIP teilen — /join testen von außen"
            ),
        ],
        "log": log,
    }
    atomic_write_json(root / _HAUS_WELT_REL, out)
    atomic_write_json(root / _EVIDENCE_REL, {**out, "mode": "haus_zur_welt"})
    return out


def activate_world_spread(
    root: Path,
    *,
    remote_mode: str = "auto",
    force_export: bool = True,
) -> Dict[str, Any]:
    """König: gesamte Welt erreichen — Tunnel + Join + H1-Verteilung."""
    root = Path(root)
    log: List[str] = []

    try:
        from analytics.alpha_model_local_runtime import enable_world_runtime

        wr = enable_world_runtime(root)
        log.extend(wr.get("changed") or [])
    except Exception as exc:
        return {"ok": False, "message_de": f"world_runtime: {exc}"[:200], "log": log}

    try:
        from tools.preview_hub import ensure_hub_running

        ensure_hub_running(root, restart=False)
        log.append("hub_online")
    except Exception as exc:
        log.append(f"hub: {exc}"[:60])

    remote: Dict[str, Any] = {}
    try:
        from analytics.remote_hub_access import ensure_remote_hub_url, remote_access_status

        remote = ensure_remote_hub_url(root, mode=remote_mode)
        if not remote.get("ok"):
            status = remote_access_status(root)
            out = {
                "ok": False,
                "message_de": str(remote.get("message_de") or "Tunnel fehlgeschlagen"),
                "remote": remote,
                "status": status,
                "log": log,
            }
            atomic_write_json(root / _EVIDENCE_REL, {**out, "updated_at_utc": _utc_now()})
            return out
        log.extend(remote.get("changed") or [])
        log.append(f"tunnel:{remote.get('mode')}")
    except Exception as exc:
        out = {"ok": False, "message_de": str(exc)[:200], "log": log}
        atomic_write_json(root / _EVIDENCE_REL, {**out, "updated_at_utc": _utc_now()})
        return out

    export: Dict[str, Any] = {}
    try:
        from analytics.worker_export_sync import ensure_lite_export

        export = ensure_lite_export(root, force=force_export)
        log.append("lite_export" if export.get("ok") else f"export_rc={export.get('export_rc')}")
    except Exception as exc:
        export = {"ok": False, "error_de": str(exc)[:120]}

    distribute: Dict[str, Any] = {}
    try:
        from analytics.h1_distribute import activate_h1_distribution

        distribute = activate_h1_distribution(root)
        log.append("h1_distribute")
    except Exception as exc:
        distribute = {"ok": False, "error_de": str(exc)[:120]}

    assignments: Dict[str, Any] = {}
    try:
        from analytics.federation_assignments import build_assignment_status

        assignments = build_assignment_status(root)
    except Exception as exc:
        assignments = {"error_de": str(exc)[:120]}

    try:
        from analytics.preview_federation import build_share_package
        from analytics.remote_hub_access import remote_access_status

        share = build_share_package(root)
        status = remote_access_status(root)
    except Exception as exc:
        share = {}
        status = {"error_de": str(exc)[:120]}

    public_url = str(remote.get("public_base_url") or share.get("share_url") or "").rstrip("/")
    join_url = str(share.get("join_url") or f"{public_url}/join")
    stable = bool(remote.get("stable"))

    out: Dict[str, Any] = {
        "ok": bool(remote.get("ok") and export.get("ok")),
        "schema_version": 1,
        "activated_at_utc": _utc_now(),
        "headline_de": (
            f"Welt aktiv — {join_url}"
            if remote.get("ok")
            else "Welt-Verteilung unvollständig"
        ),
        "public_base_url": public_url,
        "join_url": join_url,
        "share_url": share.get("share_url"),
        "tunnel_stable": stable,
        "remote": remote,
        "remote_status": status,
        "export": export,
        "lite_zip": export.get("lite_zip"),
        "distribute": {
            "headline_de": distribute.get("headline_de"),
            "queue_pending_total": distribute.get("queue_pending_total"),
        },
        "assignments": {
            "headline_de": assignments.get("headline_de"),
            "workers_online": len(assignments.get("workers") or []),
        },
        "world_join_de": [
            f"1. ZIP holen: König sendet active_alpha_worker_LITE.zip",
            f"2. Entpacken → Windows_START.bat / Linux_START.sh",
            f"3. Oder Full-Bundle für H1: preview-export + Worker-Start",
            f"4. Join-URL: {join_url}",
            f"5. Health: {public_url}/api/health",
        ],
        "h1_world_de": (
            "H1-Prep weltweit: Full-Worker lädt features.parquet vom König, "
            "liefert Prep-Chunks per /api/h1/artifact/upload zurück"
        ),
        "next_step_de": (
            "Stabile URL: spread-tunnel-token — sonst ZIP nach jedem Tunnel-Neustart neu senden"
            if not stable
            else "Lite-ZIP weltweit teilen · /h1-workers prüfen"
        ),
        "log": log,
    }
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out


def format_world_spread_de(root: Path) -> str:
    doc = activate_world_spread(root)
    lines = [f"**{doc.get('headline_de')}**", f"Join: {doc.get('join_url')}"]
    if doc.get("lite_zip"):
        lines.append(f"ZIP: {doc.get('lite_zip')}")
    for step in doc.get("world_join_de") or []:
        lines.append(step)
    lines.append(str(doc.get("h1_world_de") or ""))
    lines.append(str(doc.get("next_step_de") or ""))
    return "\n".join(lines)
