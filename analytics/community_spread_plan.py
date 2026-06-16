"""Community spread timeline — gates, tick, auto-prep."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from aa_safe_io import atomic_write_json

_PLAN_REL = Path("control/COMMUNITY_SPREAD_PLAN.json")
_EVIDENCE_REL = Path("evidence/community_spread_tick_latest.json")
_SUSTAIN_EVIDENCE_REL = Path("evidence/community_spread_sustain_latest.json")
_FORUM_REL = Path("evidence/community_spread_forum_de.txt")
_FORUM_ANONYM_REL = Path("evidence/community_spread_forum_anonym_en.txt")
_REDDIT_BODY_REL = Path("evidence/reddit_post_body_ready.txt")
_BROADCAST_REL = Path("evidence/spread_broadcast_de.txt")
_WHATSAPP_REL = Path("evidence/spread_whatsapp_de.txt")
_BROADCAST_EVIDENCE_REL = Path("evidence/spread_broadcast_latest.json")
_EXPORT_MARKER_REL = Path("evidence/community_spread_export.json")
_SOFT_LAUNCH_ACK_REL = Path("evidence/soft_launch_complete.json")
_FORUM_POST_ACK_REL = Path("evidence/forum_post_ack.json")
_PRELAUNCH_REL = Path("evidence/spread_prelaunch_latest.json")

_BERLIN = ZoneInfo("Europe/Berlin")


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


def load_spread_plan(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _PLAN_REL)


def _save_plan(root: Path, plan: Dict[str, Any]) -> None:
    path = Path(root) / _PLAN_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    plan["updated_at_utc"] = _utc_now()
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _hub_healthy(root: Path) -> Tuple[bool, str]:
    try:
        from tools.preview_hub import ensure_hub_running, _hub_healthy, DEFAULT_PORT

        ensure_hub_running(root, restart=False)
        if _hub_healthy(DEFAULT_PORT):
            return True, f"Hub :{DEFAULT_PORT} OK"
    except Exception as exc:
        return False, f"Hub Fehler: {exc}"[:120]
    return False, "Hub antwortet nicht gesund"


def _gate_manifest_present(root: Path) -> Tuple[bool, str]:
    p = root / "control/PREVIEW_MANIFEST_DE.json"
    if p.is_file():
        return True, "Manifest vorhanden"
    return False, "PREVIEW_MANIFEST_DE.json fehlt"


def _gate_join_token_active(root: Path) -> Tuple[bool, str]:
    from analytics.preview_federation import federation_config

    token = str(federation_config(root).get("join_token") or "").strip()
    if len(token) >= 16:
        return True, "join_token aktiv"
    return False, "join_token fehlt — secure spread / preview-export"


def _gate_public_base_url_set(root: Path) -> Tuple[bool, str]:
    from analytics.preview_federation import federation_config
    from analytics.remote_hub_access import is_remote_reachable_url, is_private_lan_host
    from urllib.parse import urlparse

    cfg = federation_config(root)
    url = str(cfg.get("public_base_url") or "").strip()
    remote_expected = bool(cfg.get("remote_workers_expected"))
    if not url.startswith(("http://", "https://")) or "127.0.0.1" in url:
        return False, "public_base_url fehlt — ai_kernel spread-remote"
    if remote_expected:
        if is_remote_reachable_url(url):
            mode = str(cfg.get("remote_access_mode") or "remote")
            return True, f"Remote ({mode}): {url}"
        host = urlparse(url).hostname or url
        if is_private_lan_host(host):
            return False, f"Nur LAN ({url}) — ai_kernel spread-remote für Internet-Worker"
    if url.startswith(("http://", "https://")):
        return True, url
    return False, "public_base_url ungültig"


def _gate_spread_text_ready(root: Path) -> Tuple[bool, str]:
    p = root / "docs/LINUX_COMMUNITY_DE.md"
    if p.is_file() and p.stat().st_size > 200:
        return True, "LINUX_COMMUNITY_DE.md bereit"
    return False, "Community-Text fehlt"


def _bundle_join_path(bundle_dir: Path) -> Optional[Path]:
    root_join = bundle_dir / "preview_worker_join.json"
    if root_join.is_file():
        return root_join
    ctrl_join = bundle_dir / "control/preview_worker_join.json"
    if ctrl_join.is_file():
        return ctrl_join
    return None


def _is_lite_worker_bundle(bundle_dir: Path) -> bool:
    return (
        (bundle_dir / "preview_worker_join.json").is_file()
        and (bundle_dir / "worker.py").is_file()
        and (bundle_dir / "Windows_START.bat").is_file()
    )


def _is_full_worker_bundle(bundle_dir: Path) -> bool:
    return (
        (bundle_dir / "control/preview_worker_join.json").is_file()
        and (bundle_dir / "ACTIVE_ALPHA_WORKER_START.sh").is_file()
    )


def _bundle_has_valid_token(root: Path, bundle_dir: Path) -> bool:
    from analytics.preview_federation import federation_config

    join_path = _bundle_join_path(bundle_dir)
    if not join_path:
        return False
    join_doc = _load_json(join_path)
    king_token = str(federation_config(root).get("join_token") or "").strip()
    bundle_token = str(join_doc.get("join_token") or "").strip()
    return bool(king_token) and king_token == bundle_token


def _bundle_export_ok(root: Path, bundle_dir: Path) -> bool:
    if not bundle_dir.is_dir():
        return False
    if _is_lite_worker_bundle(bundle_dir) and _bundle_has_valid_token(root, bundle_dir):
        return True
    if _is_full_worker_bundle(bundle_dir) and _bundle_has_valid_token(root, bundle_dir):
        return True
    return False


def _resolve_export_path(root: Path, raw: str) -> Optional[Path]:
    p = Path(str(raw or "").strip())
    if not str(raw or "").strip():
        return None
    if p.is_absolute():
        return p
    for base in (Path.home(), Path(root).parent, Path(root)):
        cand = (base / p).resolve()
        if cand.exists():
            return cand
    return (Path(root).parent / p).resolve()


def _gate_worker_export_ready(root: Path) -> Tuple[bool, str]:
    marker = _load_json(root / _EXPORT_MARKER_REL)
    for key in ("lite_dest", "dest"):
        dest = str(marker.get(key) or "").strip()
        resolved = _resolve_export_path(root, dest) if dest else None
        if resolved and _bundle_export_ok(root, resolved):
            kind = "Lite" if key == "lite_dest" else "Voll"
            return True, f"{kind}+Token: {resolved}"
    lite_zip = str(marker.get("lite_zip") or "").strip()
    zip_path = _resolve_export_path(root, lite_zip) if lite_zip else None
    if zip_path and zip_path.is_file():
        return True, f"Lite-ZIP: {zip_path}"
    parent = root.parent
    for pattern in ("active_alpha_worker_LITE*", "active_alpha_model_worker_*"):
        candidates = sorted(
            parent.glob(pattern),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        for cand in candidates[:3]:
            if _bundle_export_ok(root, cand):
                kind = "Lite" if "LITE" in cand.name else "Voll"
                return True, f"{kind}+Token: {cand}"
    return False, "Kein Worker-Paket mit Token — ai_kernel preview-export-lite"


def _gate_h1_sealed(root: Path) -> Tuple[bool, str]:
    from analytics.live_profile_governance import is_h1_backtest_sealed, h1_backtest_status

    try:
        from analytics.h1_seal_policy import is_h1_seal_required

        if not is_h1_seal_required(root):
            bt = h1_backtest_status(root)
            st = str(bt.get("status") or "—")
            if st == "COMPLETE":
                return True, "H1 COMPLETE — Seal optional (Policy)"
            return True, f"H1 — Seal optional ({st})"
    except Exception:
        pass
    bt = h1_backtest_status(root)
    sealed = is_h1_backtest_sealed(root)
    st = str(bt.get("status") or "—")
    if sealed:
        return True, f"H1 SEALED ({st})"
    if st == "COMPLETE":
        return False, "H1 COMPLETE — Evaluate/Seal ausstehend (h1-watch)"
    if st == "RUNNING":
        return False, "H1 RUNNING — noch nicht sealed"
    return False, f"H1 {st}"


def _gate_gui_preview_fresh(root: Path) -> Tuple[bool, str]:
    p = root / "evidence/gui_preview_latest.json"
    if not p.is_file():
        return False, "gui_preview_latest.json fehlt"
    doc = _load_json(p)
    passed = int(doc.get("passed") or 0)
    total = int(doc.get("total") or 0)
    age_h = (datetime.now().timestamp() - p.stat().st_mtime) / 3600.0
    if passed >= 8 and total >= 9 and age_h < 6.0:
        return True, f"Preview {passed}/{total} · {age_h:.1f}h frisch"
    return False, f"Preview {passed}/{total} oder veraltet ({age_h:.1f}h)"


def _gate_federation_visible(root: Path) -> Tuple[bool, str]:
    from analytics.preview_federation import build_federation_summary

    s = build_federation_summary(root)
    n = int(s.get("workers_online") or 0)
    cpus = int(s.get("total_cpus") or 0)
    if n >= 1 and cpus > 0:
        return True, s.get("headline_de") or f"{n} Knoten"
    return False, "Federation leer"


def _gate_federation_min_two_nodes(root: Path) -> Tuple[bool, str]:
    ack = _load_json(root / _SOFT_LAUNCH_ACK_REL)
    if ack.get("ok"):
        return True, str(ack.get("detail_de") or "Soft Launch bestätigt — Worker getestet")

    from analytics.preview_federation import build_federation_summary, count_federation_participants

    s = build_federation_summary(root)
    workers = list(s.get("workers") or [])
    parts = count_federation_participants(workers)
    king_hosts = {
        str(w.get("hostname") or "").strip().lower()
        for w in workers
        if str(w.get("role") or "").lower() == "king" and w.get("hostname")
    }
    remote_compute = [
        w
        for w in workers
        if str(w.get("role") or "").lower() == "compute"
        and (
            str(w.get("hostname") or "").strip().lower() not in king_hosts
            or bool(w.get("remote_join"))
        )
    ]
    if parts["king"] >= 1 and remote_compute:
        n_remote = sum(1 for w in remote_compute if w.get("remote_join"))
        detail = f"König + {len(remote_compute)} Worker"
        if n_remote:
            detail += f" ({n_remote} via Remote-URL)"
        return True, f"{detail} · {parts['hosts']} Host(s)"
    if parts["king"] >= 1 and parts["compute"] >= 1:
        return False, "Compute nur lokal — Remote-ZIP auf externem PC starten"
    return False, f"König={parts['king']} Worker={parts['compute']} — echter Worker fehlt"


def _gate_real_worker_joined(root: Path) -> Tuple[bool, str]:
    ok, msg = _gate_federation_min_two_nodes(root)
    return ok, msg


def _gate_hub_stable(root: Path) -> Tuple[bool, str]:
    ok, msg = _hub_healthy(root)
    if not ok:
        return False, msg
    uptime_path = root / "evidence/preview_hub_uptime.json"
    if uptime_path.is_file():
        doc = _load_json(uptime_path)
        raw = str(doc.get("first_started_utc") or "")
        try:
            started = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - started).total_seconds() / 3600.0
            if age_h >= 2.0:
                return True, f"Hub uptime {age_h:.1f}h"
            return False, f"Hub uptime {age_h:.1f}h — 2h abwarten"
        except (TypeError, ValueError):
            pass
    meta = root / "evidence/preview_hub.json"
    if meta.is_file():
        age_h = (datetime.now().timestamp() - meta.stat().st_mtime) / 3600.0
        if age_h >= 2.0:
            return True, f"Hub meta {age_h:.1f}h"
        return False, f"Hub erst {age_h:.1f}h aktiv — Stabilität abwarten"
    return False, "preview_hub_uptime.json fehlt"


def collect_spread_urls(root: Path) -> Dict[str, Any]:
    """LAN + Internet-URLs für Verbreitung (Forum, WhatsApp, E-Mail)."""
    from analytics.preview_federation import build_share_package, detect_lan_ip, federation_config
    from analytics.remote_hub_access import load_tunnel_state

    root = Path(root)
    cfg = federation_config(root)
    pkg = build_share_package(root)
    port = int(cfg.get("hub_port") or 17890)
    lan_url = ""
    if cfg.get("lan_bind"):
        explicit = str(cfg.get("public_base_url") or "").strip().rstrip("/")
        if explicit.startswith("http://") and "127.0.0.1" not in explicit:
            lan_url = explicit
        else:
            lan = detect_lan_ip()
            if lan:
                lan_url = f"http://{lan}:{port}"

    remote_url = ""
    tunnel = load_tunnel_state(root)
    tunnel_live = str(tunnel.get("public_url") or "").strip().rstrip("/")
    if tunnel.get("running") and tunnel_live.startswith("https://"):
        remote_url = tunnel_live
        fed_url = str(cfg.get("public_base_url") or "").strip().rstrip("/")
        if fed_url != remote_url:
            from analytics.remote_hub_access import _sync_public_urls

            _sync_public_urls(
                root,
                remote_url,
                mode=str(tunnel.get("mode") or "cloudflared"),
                stable=bool(tunnel.get("stable")),
            )
    elif tunnel.get("ok") and tunnel_live.startswith("https://"):
        remote_url = tunnel_live
    if not remote_url:
        mirror = _load_json(root / Path("control/r3_https_mirror.json"))
        candidate = str(mirror.get("public_base_url") or "").strip().rstrip("/")
        if candidate.startswith("https://"):
            remote_url = candidate
    if not remote_url:
        explicit = str(cfg.get("public_base_url") or "").strip().rstrip("/")
        if explicit.startswith("https://") and cfg.get("public_base_url_locked"):
            remote_url = explicit

    primary = lan_url or remote_url or str(pkg.get("share_url") or "").strip().rstrip("/").rstrip("/")
    marker = _load_json(root / _EXPORT_MARKER_REL)
    return {
        "lan_url": lan_url,
        "remote_url": remote_url,
        "primary_url": primary,
        "join_lan": f"{lan_url}/join" if lan_url else "",
        "join_remote": f"{remote_url}/join" if remote_url else "",
        "lite_zip": str(marker.get("lite_zip") or ""),
        "home_zip": str(Path.home() / "glasfaser_NOTFALL_worker_LITE.zip"),
        "world_zip": str(Path.home() / "world_worker_LITE.zip"),
    }


def _community_share_url(root: Path) -> str:
    """URL für Verbreitung — gesperrte Remote-URL hat Vorrang vor lokal-first."""
    urls = collect_spread_urls(root)
    if urls.get("remote_url"):
        return str(urls["remote_url"])
    return str(urls.get("primary_url") or "")


def _gate_forum_draft_ready(root: Path) -> Tuple[bool, str]:
    p = root / _FORUM_REL
    if p.is_file() and p.stat().st_size > 400:
        return True, "Forum-Entwurf bereit"
    return False, "Forum-Entwurf wird bei public-Tick erzeugt"


def _gate_forum_draft_synced(root: Path) -> Tuple[bool, str]:
    urls = collect_spread_urls(root)
    required = [u for u in (urls.get("lan_url"), urls.get("remote_url")) if u]
    if not required:
        url = _community_share_url(root)
        if not url.startswith(("http://", "https://")):
            return False, "public_base_url fehlt — ai_kernel spread-remote"
        required = [url]
    p = root / _FORUM_REL
    if not p.is_file():
        return False, "Forum-Entwurf fehlt — community-spread --repair"
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return False, str(exc)[:80]
    missing = [u for u in required if u not in text]
    if missing:
        return False, f"Forum veraltet — fehlt {missing[0][:56]}"
    return True, f"Forum synchron ({len(required)} Kanäle)"


def _gate_prep_done(root: Path, plan: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    plan = plan or load_spread_plan(root)
    for ph in plan.get("phases") or []:
        if ph.get("id") == "prep" and ph.get("status") == "done":
            return True, "Phase 1 erledigt"
    prep = next((p for p in (plan.get("phases") or []) if p.get("id") == "prep"), None)
    if prep:
        gates = [evaluate_gate(root, str(g)) for g in (prep.get("gates") or [])]
        if all(g["ok"] for g in gates):
            return True, "Phase 1 Gates grün"
    return False, "Phase 1 noch offen"


def _gate_soft_launch_ack(root: Path) -> Tuple[bool, str]:
    ack = _load_json(root / _SOFT_LAUNCH_ACK_REL)
    if ack.get("ok"):
        return True, str(ack.get("detail_de") or "Soft Launch bestätigt")
    return False, "Soft Launch noch nicht bestätigt — ai_kernel spread-soft-launch-done"


def _gate_soft_launch_done(root: Path, plan: Dict[str, Any]) -> Tuple[bool, str]:
    ack_ok, ack_msg = _gate_soft_launch_ack(root)
    if ack_ok:
        return True, ack_msg
    for ph in plan.get("phases") or []:
        if ph.get("id") == "soft_launch" and ph.get("status") == "done":
            return True, "Phase 2 erledigt"
    return False, "Phase 2 noch offen"


def ack_soft_launch(root: Path, *, detail_de: str = "Soft Launch OK — Remote-Worker getestet") -> Dict[str, Any]:
    """Phase 2 manuell abschließen (Freund/ZIP-Test erfolgreich)."""
    root = Path(root)
    plan = load_spread_plan(root)
    doc = {
        "schema_version": 1,
        "ok": True,
        "detail_de": detail_de,
        "ack_at_utc": _utc_now(),
    }
    path = root / _SOFT_LAUNCH_ACK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, doc)
    for ph in plan.get("phases") or []:
        if ph.get("id") == "soft_launch":
            ph["status"] = "done"
    _save_plan(root, plan)
    return doc


def ack_forum_post(
    root: Path,
    *,
    detail_de: str = "Forum-Post live — r/selfhosted + r/linux",
    subreddits: Optional[List[str]] = None,
    post_url: str = "",
) -> Dict[str, Any]:
    """Öffentlich-Gate abschließen — nach manuellem Reddit-Post."""
    root = Path(root)
    targets = subreddits or ["r/selfhosted", "r/linux"]
    doc = {
        "schema_version": 1,
        "ok": True,
        "detail_de": detail_de,
        "subreddits": targets,
        "post_url": str(post_url or "").strip(),
        "forum_ref": _FORUM_REL.as_posix(),
        "ack_at_utc": _utc_now(),
    }
    atomic_write_json(root / _FORUM_POST_ACK_REL, doc)
    try:
        from analytics.spread_secure_ops import build_spread_progress

        doc["progress"] = build_spread_progress(root)
    except Exception:
        pass
    return doc


_GATE_FNS = {
    "hub_healthy": _hub_healthy,
    "manifest_present": _gate_manifest_present,
    "join_token_active": _gate_join_token_active,
    "public_base_url_set": _gate_public_base_url_set,
    "worker_export_ready": _gate_worker_export_ready,
    "spread_text_ready": _gate_spread_text_ready,
    "h1_sealed": _gate_h1_sealed,
    "gui_preview_fresh": _gate_gui_preview_fresh,
    "federation_visible": _gate_federation_visible,
    "real_worker_joined": _gate_real_worker_joined,
    "federation_min_two_nodes": _gate_federation_min_two_nodes,
    "hub_stable": _gate_hub_stable,
    "forum_draft_ready": _gate_forum_draft_ready,
    "forum_draft_synced": _gate_forum_draft_synced,
    "prep_done": lambda r: _gate_prep_done(r),
    "soft_launch_done": lambda r: _gate_soft_launch_done(r, load_spread_plan(r)),
    "soft_launch_ack": _gate_soft_launch_ack,
}


def run_spread_prelaunch(root: Path) -> Dict[str, Any]:
    """Alles Automatisierbare vor öffentlichem Launch (H1 sealed ausgenommen)."""
    root = Path(root)
    log: Dict[str, Any] = {"steps": [], "ok": False, "remaining_de": []}

    try:
        from analytics.stable_server import ensure_stable_server

        boot = ensure_stable_server(root)
        log["server_bootstrap"] = boot
        log["steps"].append(f"server-bootstrap: {boot.get('message_de')}")
    except Exception as exc:
        log["steps"].append(f"server-bootstrap: {exc}")

    ack = ack_soft_launch(root)
    log["soft_launch_ack"] = ack
    log["steps"].append("soft_launch_ack: OK")

    try:
        sec = ensure_federation_spread_security(root)
        log["spread_security"] = sec
        log["steps"].append("spread-security: OK")
    except Exception as exc:
        log["steps"].append(f"spread-security: {exc}")

    try:
        from analytics.worker_export_sync import ensure_lite_export

        exp = ensure_lite_export(root, force=False)
        log["worker_export"] = exp
        log["steps"].append(f"worker-export: {exp.get('detail_de')}")
    except Exception as exc:
        log["steps"].append(f"worker-export: {exc}")

    tick = run_spread_tick(root, execute=True)
    log["spread_tick"] = {
        "next_phase_id": tick.get("next_phase_id"),
        "public_launch_ready": tick.get("public_launch_ready"),
        "blockers_de": tick.get("blockers_de"),
    }
    log["steps"].append(f"spread-tick: next={tick.get('next_phase_id')}")

    from analytics.remote_hub_access import remote_access_status
    from analytics.live_profile_governance import is_h1_backtest_sealed

    remote = remote_access_status(root)
    remaining: List[str] = []
    if not is_h1_backtest_sealed(root):
        remaining.append("H1 sealed abwarten — ai_kernel h1-watch")
    if not remote.get("tunnel_token_set"):
        remaining.append(
            "Tunnel-Token für Neustart-Stabilität: bash tools/setup_cloudflare_tunnel_token.sh"
        )
    log["remaining_de"] = remaining
    log["remote"] = remote
    log["public_launch_ready"] = bool(tick.get("public_launch_ready"))
    log["ok"] = bool(log.get("server_bootstrap", {}).get("ok")) and not [
        s for s in log["steps"] if "fehl" in s.lower() or "Fehler" in s
    ]
    log["updated_at_utc"] = _utc_now()
    log["headline_de"] = (
        "Pre-Launch bereit — nur noch H1 sealed, dann öffentlich posten"
        if len(remaining) == 1 and "H1" in remaining[0]
        else (
            "Pre-Launch teilweise — siehe remaining_de"
            if remaining
            else "Pre-Launch komplett — öffentlicher Post freigegeben"
        )
    )
    atomic_write_json(root / _PRELAUNCH_REL, log)
    return log


def evaluate_gate(root: Path, gate_id: str) -> Dict[str, Any]:
    fn = _GATE_FNS.get(gate_id)
    if fn is None:
        return {"id": gate_id, "ok": False, "detail_de": "unbekanntes Gate"}
    ok, detail = fn(root)
    return {"id": gate_id, "ok": bool(ok), "detail_de": detail}


def evaluate_phase(root: Path, phase: Dict[str, Any]) -> Dict[str, Any]:
    gates = [evaluate_gate(root, str(g)) for g in (phase.get("gates") or [])]
    optional = [evaluate_gate(root, str(g)) for g in (phase.get("optional_gates") or [])]
    done = all(g["ok"] for g in gates)
    optional_pending = [g for g in optional if not g["ok"]]
    return {
        "id": phase.get("id"),
        "label_de": phase.get("label_de"),
        "target_local": phase.get("target_local"),
        "done": done,
        "gates": gates,
        "optional_gates": optional,
        "optional_pending": optional_pending,
        "launch_policy_de": phase.get("launch_policy_de") or load_spread_plan(root).get("launch_policy_de"),
    }


def ensure_federation_spread_security(root: Path) -> Dict[str, Any]:
    """Remote/LAN-URL + join_token vor Export/Verbreitung."""
    from analytics.preview_federation import detect_lan_ip, ensure_join_token, federation_config
    from analytics.remote_hub_access import is_remote_reachable_url

    root = Path(root)
    cfg = federation_config(root)
    changed: List[str] = []
    url = str(cfg.get("public_base_url") or "").strip()
    remote_expected = bool(cfg.get("remote_workers_expected"))
    if remote_expected and not is_remote_reachable_url(url):
        from analytics.remote_hub_access import ensure_remote_hub_url

        remote = ensure_remote_hub_url(root, mode=str(cfg.get("remote_access_mode") or "auto"))
        if remote.get("ok"):
            changed.extend(remote.get("changed") or [f"public_base_url={remote.get('public_base_url')}"])
        cfg = federation_config(root)
    elif not url:
        from aa_safe_io import atomic_write_json

        cfg_path = root / "control/preview_federation.json"
        cfg = dict(federation_config(root))
        lan = detect_lan_ip()
        if lan:
            cfg["public_base_url"] = f"http://{lan}:{int(cfg.get('hub_port') or 17890)}"
            changed.append(f"public_base_url={cfg['public_base_url']}")
            atomic_write_json(cfg_path, cfg)
    token = ensure_join_token(root)
    cfg = federation_config(root)
    changed.append("join_token=ok")
    return {
        "ok": True,
        "public_base_url": cfg.get("public_base_url"),
        "remote_access_mode": cfg.get("remote_access_mode"),
        "join_token_set": bool(token),
        "changed": changed,
    }


def sync_spread_timers(root: Path) -> List[str]:
    """systemd user timers aus COMMUNITY_SPREAD_PLAN.json (Ticks + Sustain)."""
    import os
    import subprocess

    root = Path(root)
    plan = load_spread_plan(root)
    schedule = [str(x) for x in (plan.get("tick_schedule_local") or []) if str(x).strip()]
    sustain = [str(x) for x in (plan.get("sustain_schedule_local") or []) if str(x).strip()]
    schedule = schedule + sustain
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(os.environ.get("PYTHON", "python3"))
    unit_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    installed: List[str] = []
    for i, when in enumerate(schedule, start=1):
        sid = f"spread-tick-{i}"
        (unit_dir / f"active-alpha-{sid}.service").write_text(
            f"""[Unit]
Description=Active Alpha — {sid}

[Service]
Type=oneshot
WorkingDirectory={root}
Environment=AA_LINUX_NATIVE_APP=1
Environment=AA_PROJECT_ROOT={root}
ExecStart={py} {root}/tools/ai_kernel.py spread-tick
""",
            encoding="utf-8",
        )
        (unit_dir / f"active-alpha-{sid}.timer").write_text(
            f"""[Unit]
Description=Active Alpha — {sid}

[Timer]
OnCalendar={when.replace("T", " ")}
Persistent=true

[Install]
WantedBy=timers.target
""",
            encoding="utf-8",
        )
        installed.append(f"{sid}@{when}")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    for i in range(1, len(schedule) + 1):
        sid = f"spread-tick-{i}"
        subprocess.run(["systemctl", "--user", "enable", f"active-alpha-{sid}.timer"], check=False)
        subprocess.run(["systemctl", "--user", "start", f"active-alpha-{sid}.timer"], check=False)
    return installed


def _write_broadcast_texts(root: Path) -> Dict[str, Any]:
    from analytics.preview_federation import build_share_package
    from analytics.preview_manifest import load_preview_manifest

    root = Path(root)
    mf = load_preview_manifest(root)
    pkg = build_share_package(root)
    urls = collect_spread_urls(root)
    lan = str(urls.get("lan_url") or "")
    remote = str(urls.get("remote_url") or "")
    lite_zip = str(urls.get("lite_zip") or "")
    home_zip = str(urls.get("home_zip") or "")

    join_line = f"{remote}/join" if remote else (f"{lan}/join" if lan else "")
    broadcast_lines = [
        "=== Active Alpha — Verbreitung (freundlicher Diktator) ===",
        "",
        "Leit-Statement: Die nächste KI-Revolution ist dezentral — nicht noch ein Chatbot-Abo.",
        "Active Alpha: offenes Research, viele CPUs, ein auditierbares Cockpit.",
        "ZIP entpacken, START klicken, mitmachen. Kein Broker. Kein Echtgeld. Pilot — trotzdem real.",
        "",
        "MITMACHEN (wähle dein Netz):",
    ]
    if lan:
        broadcast_lines.extend(
            [
                f"- Haus/LAN (Festnetz, gleicher Router): {lan}/join",
                f"  Health: curl -fsS {lan}/api/health",
            ]
        )
    if remote:
        broadcast_lines.extend(
            [
                f"- Internet (weltweit): {remote}/join",
                f"  Health: curl -fsS {remote}/api/health",
            ]
        )
    broadcast_lines.extend(
        [
            "",
            "ZIP (~100 KB, Win/Mac/Linux):",
            f"  {lite_zip or home_zip or 'active_alpha_worker_LITE.zip'}",
            "  Entpacken → Windows_START.bat / Mac_START.command / Linux_START.sh",
            "  Nur Python 3 nötig — kein Geld, kein Broker-Zugang.",
            "",
            "Kanäle:",
            "  1. WhatsApp/SMS: evidence/spread_whatsapp_de.txt",
            "  2. Forum: evidence/community_spread_forum_de.txt",
            "  3. USB/LAN-Kopie der ZIP im Haus",
            "",
            "Grenzen: Pilot-Research, kein Hedge-Fund-Produkt.",
        ]
    )
    broadcast_path = root / _BROADCAST_REL
    broadcast_path.parent.mkdir(parents=True, exist_ok=True)
    broadcast_path.write_text("\n".join(broadcast_lines) + "\n", encoding="utf-8")

    join = join_line or (f"{remote}/join" if remote else (f"{lan}/join" if lan else ""))
    wa_lines = [
        join,
        "",
        "Die nächste KI-Revolution ist dezentral — nicht noch ein Chatbot-Abo.",
        "Active Alpha: offenes Research, viele CPUs, ein auditierbares Cockpit.",
        "ZIP im Anhang. START klicken. Deine CPUs zählen. Willkommen in der Legion.",
        "",
    ]
    wa_lines = [line for line in wa_lines if line is not None]
    while wa_lines and not wa_lines[0].strip():
        wa_lines.pop(0)
    wa_path = root / _WHATSAPP_REL
    wa_path.write_text("\n".join(wa_lines) + "\n", encoding="utf-8")

    return {
        "broadcast_ref": _BROADCAST_REL.as_posix(),
        "whatsapp_ref": _WHATSAPP_REL.as_posix(),
        "urls": urls,
        "pkg": {
            "join_command_lite_de": pkg.get("join_command_lite_de"),
            "export_command_lite_de": pkg.get("export_command_lite_de"),
        },
    }


_FORUM_TITLE = (
    "We are the next AI revolution — decentralized, open, ~100 KB worker ZIP (no cloud lock-in)"
)


def _write_forum_draft_anonym(root: Path) -> Path:
    """Internet-only — kein LAN/192.168 für öffentliche Kanäle."""
    urls = collect_spread_urls(root)
    remote = str(urls.get("remote_url") or "").strip().rstrip("/")
    if not remote.startswith("https://"):
        remote = ""
    join_url = f"{remote}/join" if remote else ""
    health_cmd = f"curl -fsS {remote}/api/health" if remote else ""
    body_lines = [
        "Listen. The next AI revolution is not another chatbot subscription.",
        "",
        "It's thousands of machines thinking together — with a cockpit you can audit,",
        "and CPUs you voluntarily lend. No broker keys. No black box. No begging a cloud CEO for permission.",
        "",
        "Active Alpha is open quantitative research:",
        "- One command center (browser)",
        "- Many workers (Win / Mac / Linux)",
        "- ~100 KB ZIP — unzip, double-click START, Python 3, done",
        "- Join over the Internet",
        "",
        "Yes, it's pilot stage. We're not a hedge fund. We don't touch your money.",
        "But the architecture is real: federated compute, legion ranks, fail-closed gates.",
        "",
        "Your move:",
    ]
    if join_url:
        body_lines.extend(
            [
                f"1. Join: {join_url}",
                f"2. Health check: {health_cmd}",
                "3. Spare CPU cycles. Become Legion #N. Watch the federation grow.",
            ]
        )
    else:
        body_lines.append("1. Join URL folgt — spread voll ausführen")
    body_lines.extend(
        [
            "",
            "Self-hosters and Linux people — you're invited. Phones spread the link; PCs do the work.",
            "Welcome to the revolution. Start the ZIP.",
        ]
    )
    body = "\n".join(body_lines)
    forum_lines = [
        "=== r/selfhosted + r/linux — ANONYM (Internet only) ===",
        "",
        "Account: Wegwerf-Reddit + Inkognito. NICHT king_ops reddit-post.",
        f"**Title:** {_FORUM_TITLE}",
        "",
        *body.splitlines(),
        "",
        "--- DE (WhatsApp / Kommentar) ---",
        "Die nächste KI-Revolution ist dezentral — nicht noch ein Chatbot-Abo.",
        "Active Alpha: offenes Research, viele CPUs, ein auditierbares Cockpit.",
        f"ZIP entpacken, START klicken, mitmachen. {join_url or '—'}",
        "",
        "Limits: pilot research stack, not a hedge fund product.",
        "",
    ]
    root = Path(root)
    path = root / _FORUM_ANONYM_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(forum_lines) + "\n", encoding="utf-8")
    reddit_path = root / _REDDIT_BODY_REL
    reddit_path.write_text(f"{_FORUM_TITLE}\n\n{body}\n", encoding="utf-8")
    return path


def _write_broadcast_texts_anonym(root: Path) -> Dict[str, Any]:
    """Öffentliche Kanäle: nur HTTPS-Join; LAN nur intern in spread_broadcast_de."""
    from analytics.preview_federation import build_share_package

    root = Path(root)
    pkg = build_share_package(root)
    urls = collect_spread_urls(root)
    lan = str(urls.get("lan_url") or "")
    remote = str(urls.get("remote_url") or "").strip().rstrip("/")
    lite_zip = str(urls.get("lite_zip") or "")
    home_zip = str(urls.get("home_zip") or "")
    world_zip = str(urls.get("world_zip") or "")

    join_https = f"{remote}/join" if remote.startswith("https://") else ""
    broadcast_lines = [
        "=== Active Alpha — Verbreitung INTERN (nicht öffentlich posten) ===",
        "",
        "Leit-Statement: Die nächste KI-Revolution ist dezentral.",
        "",
        "Öffentlich (anonym): evidence/community_spread_forum_anonym_en.txt",
        f"Internet: {join_https or '—'}",
    ]
    if lan:
        broadcast_lines.extend(
            [
                f"LAN intern: {lan}/join",
                f"  Health: curl -fsS {lan}/api/health",
            ]
        )
    broadcast_lines.extend(
        [
            "",
            f"Welt-ZIP: {world_zip or lite_zip or home_zip}",
            "",
        ]
    )
    broadcast_path = root / _BROADCAST_REL
    broadcast_path.write_text("\n".join(broadcast_lines) + "\n", encoding="utf-8")

    wa_lines = [
        join_https or "",
        "",
        "Die nächste KI-Revolution ist dezentral — nicht noch ein Chatbot-Abo.",
        "Active Alpha: offenes Research, viele CPUs, ein auditierbares Cockpit.",
        "ZIP im Anhang. START klicken. Deine CPUs zählen. Willkommen in der Legion.",
        "",
    ]
    wa_lines = [line for line in wa_lines if line is not None]
    while wa_lines and not wa_lines[0].strip():
        wa_lines.pop(0)
    wa_path = root / _WHATSAPP_REL
    wa_path.write_text("\n".join(wa_lines) + "\n", encoding="utf-8")

    return {
        "broadcast_ref": _BROADCAST_REL.as_posix(),
        "whatsapp_ref": _WHATSAPP_REL.as_posix(),
        "forum_anonym_ref": _FORUM_ANONYM_REL.as_posix(),
        "reddit_body_ref": _REDDIT_BODY_REL.as_posix(),
        "urls": urls,
        "pkg": {
            "join_command_lite_de": pkg.get("join_command_lite_de"),
            "export_command_lite_de": pkg.get("export_command_lite_de"),
        },
    }


def broadcast_spread_anonym(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Anonyme Kanäle — Internet-only, kein Reddit-Profil."""
    root = Path(root)
    forum_path = _write_forum_draft_anonym(root)
    texts = _write_broadcast_texts_anonym(root)
    urls = collect_spread_urls(root)
    remote = str(urls.get("remote_url") or "")
    gate_ok = remote.startswith("https://")
    from analytics.spread_anonym_policy import redact_spread_urls

    doc = {
        "schema_version": 1,
        "ok": gate_ok,
        "anonym": True,
        "headline_de": (
            "Anonym-Spread bereit — Internet-Join + reddit_post_body_ready.txt"
            if gate_ok
            else "Anonym-Spread — HTTPS-Join fehlt (spread voll / Tunnel)"
        ),
        "forum_anonym_ref": _FORUM_ANONYM_REL.as_posix(),
        "reddit_body_ref": _REDDIT_BODY_REL.as_posix(),
        "broadcast_ref": texts.get("broadcast_ref"),
        "whatsapp_ref": texts.get("whatsapp_ref"),
        "urls": redact_spread_urls(urls),
        "channels_de": [
            "Reddit anonym: evidence/reddit_post_operator_anonym_de.txt",
            f"Internet: {remote or '—'}/join",
            "WhatsApp: evidence/spread_whatsapp_de.txt (nur HTTPS-Zeile)",
        ],
        "updated_at_utc": _utc_now(),
    }
    if persist:
        atomic_write_json(root / _BROADCAST_EVIDENCE_REL, doc)
    doc["forum_path"] = str(forum_path)
    return doc


def _write_forum_draft(root: Path) -> Path:
    from analytics.spread_anonym_policy import is_anonym_enforced

    if is_anonym_enforced(root):
        return _write_forum_draft_anonym(root)
    from analytics.preview_manifest import load_preview_manifest

    mf = load_preview_manifest(root)
    urls = collect_spread_urls(root)
    lan = str(urls.get("lan_url") or "")
    remote = str(urls.get("remote_url") or "")
    join_base = remote or lan or _community_share_url(root).rstrip("/")
    join_url = f"{join_base}/join"
    health_cmd = f"curl -fsS {join_base}/api/health"
    lines = [
        "=== r/selfhosted + r/linux — Copy-Paste (freundlicher Diktator) ===",
        "",
        "**Title:** We are the next AI revolution — decentralized, open, ~100 KB worker ZIP (no cloud lock-in)",
        "",
        "Listen. The next AI revolution is not another chatbot subscription.",
        "",
        "It's thousands of machines thinking together — with a cockpit you can audit,",
        "and CPUs you voluntarily lend. No broker keys. No black box. No begging a cloud CEO for permission.",
        "",
        "Active Alpha is open quantitative research:",
        "- One command center (browser)",
        "- Many workers (Win / Mac / Linux)",
        "- ~100 KB ZIP — unzip, double-click START, Python 3, done",
        "- Join over the Internet or LAN",
        "",
        "Yes, it's pilot stage. We're not a hedge fund. We don't touch your money.",
        "But the architecture is real: federated compute, legion ranks, fail-closed gates.",
        "",
        "Your move:",
        f"1. Join: {join_url}",
        f"2. Health check: {health_cmd}",
        "3. Spare CPU cycles. Become Legion #N. Watch the federation grow.",
        "",
        "Self-hosters and Linux people — you're invited. Phones spread the link; PCs do the work.",
        "Welcome to the revolution. Start the ZIP.",
        "",
        "--- DE (WhatsApp / Kommentar) ---",
        "Die nächste KI-Revolution ist dezentral — nicht noch ein Chatbot-Abo.",
        "Active Alpha: offenes Research, viele CPUs, ein auditierbares Cockpit.",
        f"ZIP entpacken, START klicken, mitmachen. {join_url}",
        "",
    ]
    if lan:
        lines.extend(
            [
                "---",
                f"LAN (same house/WiFi): {lan}/join",
                f"Health (LAN): curl -fsS {lan}/api/health",
                "",
            ]
        )
    if remote and lan:
        lines.extend(
            [
                f"Internet: {remote}/join",
                f"Health (Internet): curl -fsS {remote}/api/health",
                "",
            ]
        )
    lines.extend(
        [
            "Limits: pilot research stack, not a hedge fund product.",
            f"DE one-liner: {mf.get('one_liner_de') or 'Offenes Research-Cockpit — kollektive CPU, kein Broker.'}",
            "Full DE copy: docs/LINUX_COMMUNITY_DE.md in the project.",
            "",
        ]
    )
    path = root / _FORUM_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        from analytics.federation_dependency import write_dependency_statement

        write_dependency_statement(root)
    except Exception:
        pass
    _write_broadcast_texts(root)
    return path


def broadcast_spread(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Alle Kanäle synchronisieren — Forum, WhatsApp, Broadcast-Text."""
    root = Path(root)
    from analytics.spread_anonym_policy import is_anonym_enforced

    if is_anonym_enforced(root):
        return broadcast_spread_anonym(root, persist=persist)
    forum_path = _write_forum_draft(root)
    texts = _write_broadcast_texts(root)
    urls = collect_spread_urls(root)
    gate = evaluate_gate(root, "forum_draft_synced")
    doc = {
        "schema_version": 1,
        "ok": bool(gate.get("ok")),
        "headline_de": (
            "Jeder kann mitmachen — LAN + Internet + WhatsApp-Text bereit"
            if gate.get("ok")
            else "Broadcast geschrieben — Forum-Gate prüfen"
        ),
        "forum_ref": _FORUM_REL.as_posix(),
        "broadcast_ref": texts.get("broadcast_ref"),
        "whatsapp_ref": texts.get("whatsapp_ref"),
        "urls": urls,
        "forum_draft_synced": gate,
        "channels_de": [
            "WhatsApp/SMS: evidence/spread_whatsapp_de.txt kopieren",
            "Forum: evidence/community_spread_forum_de.txt posten (r/selfhosted, r/linux)",
            "Haus: ZIP per USB oder LAN — gleiches WLAN wie König",
            f"Internet: {urls.get('remote_url') or '—'}/join",
        ],
        "updated_at_utc": _utc_now(),
    }
    if persist:
        atomic_write_json(root / _BROADCAST_EVIDENCE_REL, doc)
    doc["forum_path"] = str(forum_path)
    return doc


def _run_prep_actions(root: Path) -> List[str]:
    log: List[str] = []
    try:
        sec = ensure_federation_spread_security(root)
        log.append(f"federation security: {sec.get('changed')}")
    except Exception as exc:
        log.append(f"federation security: {exc}")
    try:
        from tools.preview_hub import ensure_hub_running

        ensure_hub_running(root, restart=False)
        log.append("Hub ensure OK")
    except Exception as exc:
        log.append(f"Hub ensure: {exc}")

    try:
        from analytics.worker_export_sync import ensure_lite_export

        exp = ensure_lite_export(root, force=False)
        log.append(f"worker-export: {exp.get('detail_de')}")
    except Exception as exc:
        log.append(f"worker-export: {exc}")

    try:
        import subprocess
        import sys

        py = root / ".venv/bin/python3"
        if not py.is_file():
            py = Path(sys.executable)
        proc = subprocess.run(
            [str(py), str(root / "tools/run_gui_preview.py"), "--backend-only", "--force"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        log.append(f"gui-preview rc={proc.returncode}")
    except Exception as exc:
        log.append(f"gui-preview: {exc}")

    _write_forum_draft(root)
    log.append("forum draft geschrieben")
    return log


def _run_sustain_actions(root: Path) -> List[str]:
    """Laufende Linux-Community-Ausbreitung — Tunnel, Export, Forum, Timer."""
    log: List[str] = []
    try:
        sec = ensure_federation_spread_security(root)
        log.append(f"federation security: {sec.get('changed')}")
    except Exception as exc:
        log.append(f"federation security: {exc}")
    try:
        from tools.preview_hub import ensure_hub_running

        ensure_hub_running(root, restart=False)
        log.append("Hub ensure OK")
    except Exception as exc:
        log.append(f"Hub ensure: {exc}")

    force_export = not _gate_forum_draft_synced(root)[0]
    try:
        from analytics.worker_export_sync import ensure_lite_export

        exp = ensure_lite_export(root, force=force_export)
        log.append(f"worker-export: {exp.get('detail_de')}")
    except Exception as exc:
        log.append(f"worker-export: {exc}")

    try:
        path = _write_forum_draft(root)
        log.append(f"forum draft: {path.name}")
    except Exception as exc:
        log.append(f"forum draft: {exc}")

    try:
        timers = sync_spread_timers(root)
        log.append(f"timers: {len(timers)}")
    except Exception as exc:
        log.append(f"timers: {exc}")

    import os

    if os.environ.get("AA_SPREAD_AUTONOMOUS_IN_PROGRESS", "").strip().lower() not in ("1", "true", "yes"):
        try:
            from analytics.spread_autonomous import is_autonomous_spread_enabled, run_autonomous_spread_sustain

            if is_autonomous_spread_enabled(root):
                # spread voll/repair: nur Worker — kein wa.me/ZIP/Firefox öffnen
                auto = run_autonomous_spread_sustain(root, execute_whatsapp=False)
                log.append(f"spread-autonom: {auto.get('headline_de')}")
        except Exception as exc:
            log.append(f"spread-autonom: {exc}")
    return log


def _run_soft_actions(root: Path) -> List[str]:
    log: List[str] = []
    try:
        from analytics.h1_watch import run_h1_watch

        rep = run_h1_watch(root)
        log.append(f"h1-watch: {rep.get('status')}")
    except Exception as exc:
        log.append(f"h1-watch: {exc}")
    try:
        import subprocess
        import sys

        py = root / ".venv/bin/python3"
        if not py.is_file():
            py = Path(sys.executable)
        proc = subprocess.run(
            [str(py), str(root / "tools/run_gui_preview.py"), "--backend-only", "--force"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        log.append(f"gui-preview rc={proc.returncode}")
    except Exception as exc:
        log.append(f"gui-preview: {exc}")
    return log


def run_spread_tick(
    root: Path,
    *,
    phase_id: Optional[str] = None,
    execute: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    plan = load_spread_plan(root)
    phases = list(plan.get("phases") or [])
    evaluated = [evaluate_phase(root, ph) for ph in phases]

    next_phase: Optional[Dict[str, Any]] = None
    for ev in evaluated:
        if not ev["done"]:
            next_phase = ev
            break

    actions_run: List[str] = []
    phase_skipped_de: Optional[str] = None
    if execute and next_phase:
        pid = str(next_phase.get("id") or "")
        if phase_id and phase_id != pid:
            phase_skipped_de = f"AA_SPREAD_PHASE={phase_id} ignoriert — aktiv ist {pid}"
        elif pid == "prep":
            actions_run = _run_prep_actions(root)
            evaluated = [evaluate_phase(root, ph) for ph in phases]
        elif pid == "soft_launch":
            actions_run = _run_soft_actions(root)
            evaluated = [evaluate_phase(root, ph) for ph in phases]
        elif pid == "public":
            _write_forum_draft(root)
            actions_run.append("forum draft aktualisiert")
            evaluated = [evaluate_phase(root, ph) for ph in phases]
        elif pid == "sustain":
            actions_run = _run_sustain_actions(root)
            evaluated = [evaluate_phase(root, ph) for ph in phases]
    elif execute and not next_phase:
        actions_run = _run_sustain_actions(root)
        evaluated = [evaluate_phase(root, ph) for ph in phases]

    next_phase = None
    for ev in evaluated:
        if not ev["done"]:
            next_phase = ev
            break

    active_id = (next_phase or {}).get("id")
    for i, ph in enumerate(phases):
        ev = evaluated[i]
        if ev["done"]:
            ph["status"] = "done"
        elif ev.get("id") == active_id:
            ph["status"] = "in_progress"
        else:
            ph["status"] = "pending"

    plan["phases"] = phases
    _save_plan(root, plan)

    now_local = datetime.now(_BERLIN).replace(microsecond=0).isoformat()
    report: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "now_local": now_local,
        "phases": evaluated,
        "next_phase_id": (next_phase or {}).get("id"),
        "next_phase_label_de": (next_phase or {}).get("label_de"),
        "actions_run": actions_run,
        "phase_skipped_de": phase_skipped_de,
        "forum_draft": str(root / _FORUM_REL) if (root / _FORUM_REL).is_file() else None,
    }
    public_ev = next((ev for ev in evaluated if ev.get("id") == "public"), None)
    if public_ev:
        report["public_launch_ready"] = bool(public_ev.get("done"))
        report["public_launch_policy_de"] = (
            public_ev.get("launch_policy_de")
            or plan.get("launch_policy_de")
            or "Öffentlicher Launch gestattet wenn H1 sealed"
        )
        if public_ev.get("optional_pending"):
            report["public_launch_recommended_de"] = [
                f"{g['id']}: {g['detail_de']}" for g in public_ev["optional_pending"]
            ]
    if next_phase:
        blockers = [g for g in next_phase.get("gates", []) if not g["ok"]]
        report["blockers_de"] = [f"{g['id']}: {g['detail_de']}" for g in blockers]
    sustain_ev = next((ev for ev in evaluated if ev.get("id") == "sustain"), None)
    if sustain_ev:
        report["sustain_ok"] = bool(sustain_ev.get("done"))
        report["sustain_gates"] = sustain_ev.get("gates")
    out = root / _EVIDENCE_REL
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def scan_community_spread(root: Path) -> Dict[str, Any]:
    """Read-only Status der Linux-Community-Ausbreitung."""
    root = Path(root)
    gate_ids = (
        "hub_healthy",
        "public_base_url_set",
        "join_token_active",
        "worker_export_ready",
        "forum_draft_synced",
        "spread_text_ready",
    )
    gates = [evaluate_gate(root, gid) for gid in gate_ids]
    ok_n = sum(1 for g in gates if g.get("ok"))
    blockers = [f"{g['id']}: {g['detail_de']}" for g in gates if not g.get("ok")]
    from analytics.preview_federation import build_share_package

    base = _community_share_url(root)
    pkg = build_share_package(root)
    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "gates": gates,
        "gates_ok": ok_n,
        "gates_total": len(gates),
        "blockers_de": blockers,
        "forum_draft": str(root / _FORUM_REL) if (root / _FORUM_REL).is_file() else None,
        "share_url": f"{base.rstrip('/')}/" if base else None,
        "join_url": f"{base.rstrip('/')}/join" if base else None,
        "export_command_de": pkg.get("export_command_de"),
        "headline_de": (
            "Linux-Community-Ausbreitung gesichert"
            if ok_n == len(gates)
            else f"Ausbreitung {int(100 * ok_n / len(gates))}% — {len(blockers)} Blocker"
        ),
        "ok": ok_n == len(gates),
    }


def ensure_community_spread(root: Path, *, repair: bool = True, persist: bool = True) -> Dict[str, Any]:
    """Linux-Community-Ausbreitung sichern — Tunnel, ZIP, Forum, Timer."""
    root = Path(root)
    actions: List[str] = []
    tick: Dict[str, Any] = {}
    if repair:
        actions = _run_sustain_actions(root)
        tick = run_spread_tick(root, execute=False)
    scan = scan_community_spread(root)
    doc: Dict[str, Any] = {
        **scan,
        "actions_run": actions,
        "spread_tick": {
            "next_phase_id": tick.get("next_phase_id"),
            "sustain_ok": tick.get("sustain_ok"),
        },
        "message_de": (
            "Forum + Export + Timer synchron — bereit für r/selfhosted + r/linux"
            if scan.get("ok")
            else "Repair ausgeführt — Blocker prüfen: " + "; ".join(scan.get("blockers_de") or [])[:200]
        ),
    }
    if persist:
        atomic_write_json(root / _SUSTAIN_EVIDENCE_REL, doc)
    return doc
