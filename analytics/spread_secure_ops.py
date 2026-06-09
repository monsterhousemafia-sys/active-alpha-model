"""Spread — maximal effizient, fail-closed abgesichert."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/spread_secure_ops_latest.json")
_PROGRESS_REL = Path("evidence/spread_progress_latest.json")
_PUBLIC_POST_REL = Path("evidence/spread_public_post_ready.json")
_ADOPTION_GATE_REL = Path("evidence/spread_adoption_gate.json")
_FACTS_REL = Path("evidence/spread_facts_latest.json")

_SAFETY_FLAGS = (
    "auto_execute_real_money_enabled: false",
    "auto_promote_paper_enabled: false",
    "auto_promote_signal_enabled: false",
    "auto_research_enabled: false",
)


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


def _http_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/health", timeout=timeout) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _join_page_ok(base_url: str, timeout: float = 10.0) -> bool:
    base = str(base_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        return False
    try:
        with urllib.request.urlopen(f"{base}/join", timeout=timeout) as resp:
            body = resp.read()
            return int(getattr(resp, "status", 0) or 0) == 200 and len(body) > 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _check_safety_flags(root: Path) -> Dict[str, Any]:
    pg = root / "promotion_gate_config.yaml"
    kernel = _load_json(root / "control/AI_KERNEL.json")
    ok_flags = True
    missing: List[str] = []
    if pg.is_file():
        text = pg.read_text(encoding="utf-8", errors="ignore")
        compact = re.sub(r"\s+", "", text)
        for flag in _SAFETY_FLAGS:
            if re.sub(r"\s+", "", flag) not in compact:
                ok_flags = False
                missing.append(flag.split(":")[0])
    gov = kernel.get("governance") or {}
    if gov.get("auto_execute_real_money") is True:
        ok_flags = False
        missing.append("AI_KERNEL.auto_execute_real_money")
    return {
        "id": "safety_flags",
        "ok": ok_flags,
        "detail_de": "Kein Echtgeld, keine Auto-Promotion" if ok_flags else f"BLOCK: {', '.join(missing)}",
    }


def _check_join_token(root: Path) -> Dict[str, Any]:
    from analytics.preview_federation import federation_config

    cfg = federation_config(root)
    token = str(cfg.get("join_token") or "").strip()
    ok = len(token) >= 16
    return {
        "id": "join_token",
        "ok": ok,
        "detail_de": "join_token aktiv" if ok else "join_token fehlt — Export blockiert",
    }


def _check_bind_policy(root: Path) -> Dict[str, Any]:
    from analytics.preview_federation import federation_config, hub_bind_host

    cfg = federation_config(root)
    bind = hub_bind_host(root)
    lan = bool(cfg.get("lan_bind"))
    if bind == "0.0.0.0" and not lan:
        return {"id": "bind_policy", "ok": False, "detail_de": "0.0.0.0 ohne lan_bind — blockiert"}
    if bind == "0.0.0.0":
        return {"id": "bind_policy", "ok": True, "detail_de": "LAN-Bind 0.0.0.0 (bewusst)"}
    return {"id": "bind_policy", "ok": True, "detail_de": f"Bind {bind}"}


def _check_hub_health(root: Path) -> Dict[str, Any]:
    from analytics.preview_federation import detect_lan_ip, federation_config

    cfg = federation_config(root)
    port = int(cfg.get("hub_port") or 17890)
    local_ok = _http_ok(f"http://127.0.0.1:{port}")
    lan = detect_lan_ip()
    lan_bind = bool(cfg.get("lan_bind"))
    lan_ok = _http_ok(f"http://{lan}:{port}") if lan else False
    ok = local_ok and (lan_ok or not lan_bind or not lan)
    return {
        "id": "hub_health",
        "ok": ok,
        "detail_de": f"local={'OK' if local_ok else 'FAIL'} lan={'OK' if lan_ok else '—'}",
    }


def _check_tunnel_world(root: Path) -> Dict[str, Any]:
    from analytics.remote_hub_access import load_tunnel_state, remote_access_status

    status = remote_access_status(root)
    if not status.get("remote_workers_expected"):
        return {"id": "tunnel_world", "ok": True, "detail_de": "Welt-Modus aus — optional"}
    url = str(status.get("public_base_url") or "").strip()
    tunnel = load_tunnel_state(root)
    alive = bool(status.get("tunnel_pid_alive") and tunnel.get("ok"))
    ok = bool(status.get("remote_ready")) or (
        url.startswith("https://") and alive and _http_ok(f"http://127.0.0.1:{17890}")
    )
    remote_verified = _http_ok(url) if url.startswith("https://") else False
    return {
        "id": "tunnel_world",
        "ok": ok,
        "detail_de": (
            f"OK {url[:48]} pid=alive"
            if ok and remote_verified
            else (
                f"OK {url[:48]} pid=alive (lokal verifiziert)"
                if ok
                else f"FAIL {url[:48]} pid={'alive' if alive else 'down'}"
            )
        ),
    }


def _check_zip_separation(root: Path) -> Dict[str, Any]:
    """Haus-ZIP = LAN-HTTP, Welt-ZIP = HTTPS — keine Verwechslung."""
    from analytics.preview_federation import federation_config

    cfg = federation_config(root)
    bundle = root.parent / "active_alpha_worker_LITE/preview_worker_join.json"
    join = str(_load_json(bundle).get("hub_join_url") or "") if bundle.is_file() else ""
    issues: List[str] = []
    if cfg.get("remote_workers_expected") and join and not join.startswith("https://"):
        issues.append("Welt-Bundle braucht HTTPS-Join")
    if cfg.get("lan_bind"):
        house_zip = Path.home() / "glasfaser_NOTFALL_worker_LITE.zip"
        if not house_zip.is_file():
            issues.append("Haus-ZIP fehlt (glasfaser_NOTFALL_worker_LITE.zip)")
    ok = not issues
    return {
        "id": "zip_separation",
        "ok": ok,
        "detail_de": "; ".join(issues) if issues else f"Bundle-Join {join[:40] or '—'}",
    }


def verify_spread_security(root: Path) -> Dict[str, Any]:
    """Fail-closed — alle Gates müssen grün sein vor Export/Verbreitung."""
    root = Path(root)
    checks = [
        _check_safety_flags(root),
        _check_join_token(root),
        _check_bind_policy(root),
        _check_hub_health(root),
        _check_tunnel_world(root),
        _check_zip_separation(root),
    ]
    passed = sum(1 for c in checks if c.get("ok"))
    ok = passed == len(checks)
    doc = {
        "schema_version": 1,
        "ok": ok,
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "headline_de": (
            f"Spread verify {passed}/{len(checks)} — Infrastruktur-Gates grün"
            if ok
            else f"Spread verify {passed}/{len(checks)} — BLOCKIERT"
        ),
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_spread_facts(
    root: Path,
    *,
    progress: Optional[Dict[str, Any]] = None,
    security: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Nur messbare Spread-Fakten — keine Behauptungen."""
    from analytics.remote_hub_access import remote_access_status

    root = Path(root)
    if security is None:
        security = verify_spread_security(root)
    if progress is None:
        progress = {"bars": {}, "detail_de": {}}
    remote = remote_access_status(root)
    detail = progress.get("detail_de") or {}
    bars = progress.get("bars") or {}
    ack = _load_json(root / "evidence/forum_post_ack.json")
    world_zip = Path.home() / "world_worker_LITE.zip"
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "verify_passed": security.get("checks_passed"),
        "verify_total": security.get("checks_total"),
        "verify_ok": security.get("ok"),
        "tunnel_pid_alive": remote.get("tunnel_pid_alive"),
        "tunnel_stable": remote.get("stable"),
        "remote_health_ok": remote.get("remote_ready"),
        "join_lan": detail.get("join_lan"),
        "join_remote": detail.get("join_remote"),
        "internet_join_ok": detail.get("internet_join_ok"),
        "workers_online": detail.get("workers_online"),
        "compute_workers": detail.get("compute_workers"),
        "remote_compute_workers": detail.get("remote_compute_workers"),
        "world_zip_exists": world_zip.is_file(),
        "forum_draft_exists": (root / "evidence/community_spread_forum_de.txt").is_file(),
        "forum_posted": bool(ack.get("ok")) and bool(str(ack.get("post_url") or "").strip()),
        "forum_post_url": str(ack.get("post_url") or "").strip() or None,
        "bars_pct": {k: v.get("pct") for k, v in bars.items()},
        "headline_de": (
            f"Spread-Fakten: verify {security.get('checks_passed')}/{security.get('checks_total')}, "
            f"adoption {bars.get('adoption', {}).get('pct')}%, "
            f"remote_compute {detail.get('remote_compute_workers')}"
        ),
    }
    atomic_write_json(root / _FACTS_REL, doc)
    return doc


def build_spread_progress(root: Path) -> Dict[str, Any]:
    """Vier Balken: Vorbereitung · Infrastruktur · Adoption · Öffentlich."""
    from analytics.community_spread_plan import collect_spread_urls, scan_community_spread
    from analytics.preview_federation import build_federation_summary, federation_config
    from analytics.remote_hub_access import remote_access_status

    root = Path(root)
    sustain = scan_community_spread(root)
    urls = collect_spread_urls(root)
    remote = remote_access_status(root)
    fed = federation_config(root)
    summary = build_federation_summary(root)
    workers = list(summary.get("workers") or [])
    compute = [w for w in workers if str(w.get("role") or "").lower() == "compute"]
    glasfaser = _load_json(root / "control/glasfaser_offline_state.json")
    phase = str(glasfaser.get("active_phase_id") or "")

    phases = _load_json(root / "control/COMMUNITY_SPREAD_PLAN.json").get("phases") or []
    prep_done = bool(phases) and all(ph.get("status") == "done" for ph in phases)
    gates_ok = int(sustain.get("gates_ok") or 0)
    gates_total = int(sustain.get("gates_total") or 1)
    prep_items = [prep_done, gates_ok >= gates_total - 1, sustain.get("ok") or gates_ok >= gates_total]
    infra_items = [
        _http_ok(str(urls.get("lan_url") or "")),
        _http_ok(str(urls.get("remote_url") or ""), timeout=8.0),
        Path.home().joinpath("glasfaser_NOTFALL_worker_LITE.zip").is_file(),
        (root / "evidence/world_worker_LITE.zip").is_file()
        or Path.home().joinpath("world_worker_LITE.zip").is_file(),
        bool(fed.get("join_token")),
        fed.get("lan_bind") and str(fed.get("bind_host") or "") == "0.0.0.0",
        (root / "evidence/spread_whatsapp_de.txt").is_file(),
        (root / "evidence/community_spread_forum_de.txt").is_file(),
        remote.get("remote_ready"),
        remote.get("remote_workers_expected"),
    ]
    # Adoption: ehrlich — lokaler Compute allein zählt nicht als Sprung.
    from analytics.federation_dependency import assess_federation_dependency

    dep = assess_federation_dependency(root)
    adoption_pct = int(dep.get("adoption_pct_honest") or 0)
    join_remote_base = str(urls.get("remote_url") or remote.get("public_base_url") or "").rstrip("/")
    internet_join_ok = _join_page_ok(join_remote_base)
    public_items = [
        any(g.get("id") == "forum_draft_synced" and g.get("ok") for g in sustain.get("gates") or []),
        (root / "evidence/spread_broadcast_de.txt").is_file(),
        (root / _PUBLIC_POST_REL).is_file(),
        bool(remote.get("remote_ready")) and _http_ok(join_remote_base, timeout=8.0),
        internet_join_ok,
        phase in ("after_online", "before_offline") or bool(remote.get("remote_ready")),
        bool(_load_json(root / "evidence/forum_post_ack.json").get("ok"))
        and bool(str(_load_json(root / "evidence/forum_post_ack.json").get("post_url") or "").strip()),
    ]

    def _pct(items: List[bool]) -> int:
        if not items:
            return 0
        return int(round(100 * sum(1 for x in items if x) / len(items)))

    bars = {
        "vorbereitung": {"pct": _pct(prep_items), "label_de": "Phase 1–4 + Sustain"},
        "infrastruktur": {"pct": _pct(infra_items), "label_de": "Tunnel+LAN+ZIP+Texte"},
        "adoption": {"pct": adoption_pct, "label_de": "Rechenleistung-Spender (PC gestartet)"},
        "oeffentlich": {"pct": _pct(public_items), "label_de": "Forum+Launch"},
    }
    doc = {
        "schema_version": 1,
        "bars": bars,
        "detail_de": {
            "workers_online": len(workers),
            "compute_workers": len(compute),
            "remote_compute_workers": dep.get("remote_compute"),
            "dependency_risk": dep.get("risk_level"),
            "worker_definition_de": "Worker = jeder, der Rechenleistung bereitstellen kann (Win/Mac/Linux, Python 3)",
            "join_lan": urls.get("join_lan"),
            "join_remote": urls.get("join_remote"),
            "glasfaser_phase": phase or "—",
            "internet_join_ok": internet_join_ok,
        },
        "dependency": dep,
        "next_de": _next_spread_actions(
            root,
            bars,
            phase,
            compute_count=len(compute),
            remote_compute_count=int(dep.get("remote_compute") or 0),
        ),
        "adoption_gate": _write_adoption_gate(root, urls, compute, dep),
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _PROGRESS_REL, doc)
    return doc


def _write_adoption_gate(
    root: Path,
    urls: Dict[str, Any],
    compute: List[Dict[str, Any]],
    dep: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    world_zip = Path.home() / "world_worker_LITE.zip"
    if not world_zip.is_file():
        world_zip = Path(root) / "evidence/world_worker_LITE.zip"
    if dep is None:
        from analytics.federation_dependency import assess_federation_dependency

        dep = assess_federation_dependency(root)
    done = bool(dep.get("adoption_done"))
    doc = {
        "schema_version": 1,
        "ok": done,
        "next_real_jump_de": str(dep.get("next_action_de") or "Externer PC startet die Welt-ZIP"),
        "blocked_until_de": "mindestens 1 Compute-Worker auf fremdem Host (nicht nur König-PC)",
        "dependency_risk": dep.get("risk_level"),
        "dependency_headline_de": dep.get("headline_de"),
        "ready_to_share": world_zip.is_file() and bool(urls.get("join_remote")),
        "world_zip": str(world_zip) if world_zip.is_file() else str(Path.home() / "world_worker_LITE.zip"),
        "join_remote": urls.get("join_remote"),
        "whatsapp_ref": "evidence/spread_whatsapp_de.txt",
        "steps_de": [
            "1. ~/world_worker_LITE.zip + Join-Link per WhatsApp/E-Mail/USB senden",
            "2. Empfänger: PC mit Python 3 (Win/Mac/Linux)",
            "3. Entpacken → Windows_START.bat oder ./Linux_START.sh",
            f"4. Prüfen: Hub zeigt dann ≥2 Knoten — {urls.get('join_remote') or '—'}",
        ],
        "compute_workers": len(compute),
        "done": done,
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _ADOPTION_GATE_REL, doc)
    return doc


def _next_spread_actions(
    root: Path,
    bars: Dict[str, Any],
    phase: str,
    *,
    compute_count: int = 0,
    remote_compute_count: int = 0,
) -> List[str]:
    actions: List[str] = []
    if remote_compute_count < 1:
        actions.append(
            "Fakt: 0 remote Compute-Hosts — ~/world_worker_LITE.zip + Join-Link an externen PC"
        )
    elif remote_compute_count < 2:
        actions.append(f"Fakt: {remote_compute_count} remote Host — Ziel ≥2 für Adoption 100%")
    if compute_count < 1:
        actions.append("Fakt: 0 Compute-Worker — lokaler Worker-Dienst prüfen")
    if bars.get("infrastruktur", {}).get("pct", 0) < 100:
        actions.append("bash tools/king_ops.sh spread voll")
    if phase == "during_offline":
        actions.append("Glasfaser-Comeback: bash tools/king_ops.sh glasfaser --comeback --repair")
    ack = _load_json(root / "evidence/forum_post_ack.json")
    forum_posted = bool(ack.get("ok")) and bool(str(ack.get("post_url") or "").strip())
    if not forum_posted and bars.get("oeffentlich", {}).get("pct", 0) < 100:
        actions.append("Reddit/Forum: evidence/community_spread_forum_de.txt → Post → forum-ack mit URL")
    if not actions:
        actions.append("Keine offenen Spread-Schritte in den gemessenen Gates")
    return actions


def _write_public_post_ready(root: Path) -> Path:
    from analytics.community_spread_plan import collect_spread_urls

    root = Path(root)
    urls = collect_spread_urls(root)
    forum = root / "evidence/community_spread_forum_de.txt"
    body = forum.read_text(encoding="utf-8") if forum.is_file() else ""
    glasfaser = _load_json(root / "control/glasfaser_offline_state.json")
    ack = _load_json(root / "evidence/forum_post_ack.json")
    post_url = str(ack.get("post_url") or "").strip()
    forum_posted = bool(ack.get("ok")) and bool(post_url)
    draft_ready = forum.is_file() and len(body.strip()) > 80
    post_allowed = glasfaser.get("active_phase_id") != "during_offline"
    doc = {
        "schema_version": 1,
        "ok": forum_posted,
        "draft_ready": draft_ready,
        "forum_posted": forum_posted,
        "post_url": post_url or None,
        "forum_ref": "evidence/community_spread_forum_de.txt",
        "whatsapp_ref": "evidence/spread_whatsapp_de.txt",
        "join_remote": urls.get("join_remote"),
        "world_zip": str(Path.home() / "world_worker_LITE.zip"),
        "glasfaser_phase": glasfaser.get("active_phase_id"),
        "post_allowed": post_allowed,
        "targets_de": ["r/selfhosted", "r/linux"],
        "headline_de": (
            f"Forum live — {post_url}"
            if forum_posted
            else (
                "Forum-Entwurf bereit — Post + forum-ack fehlt"
                if draft_ready and post_allowed
                else "Forum blockiert (Glasfaser offline oder Entwurf fehlt)"
            )
        ),
        "body_preview_de": body[:1200],
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _PUBLIC_POST_REL, doc)
    return root / _PUBLIC_POST_REL


def _repair_export_artifacts(root: Path) -> Dict[str, Any]:
    """Marker-Pfade absolut + Welt-ZIP-Kopien."""
    import shutil

    root = Path(root)
    marker_path = root / "evidence/community_spread_export.json"
    marker = _load_json(marker_path)
    changed: List[str] = []
    for key in ("lite_dest", "lite_zip"):
        raw = str(marker.get(key) or "").strip()
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            for base in (Path.home(), root.parent):
                cand = (base / raw).resolve()
                if cand.exists() or key == "lite_dest":
                    p = cand
                    break
        if str(marker.get(key)) != str(p):
            marker[key] = str(p)
            changed.append(key)
    if changed:
        atomic_write_json(marker_path, marker)
    world_src = Path(str(marker.get("lite_zip") or ""))
    world_copies: List[str] = []
    if world_src.is_file():
        for dest in (root / "evidence/world_worker_LITE.zip", Path.home() / "world_worker_LITE.zip"):
            try:
                shutil.copy2(world_src, dest)
                world_copies.append(str(dest))
            except OSError:
                pass
    return {"changed": changed, "world_copies": world_copies}


def _dedupe_hub(root: Path) -> None:
    from tools.preview_hub import ensure_hub_running

    ensure_hub_running(root, restart=True)


def expand_internet_spread(root: Path) -> Dict[str, Any]:
    """Internet-Spread ausbauen — /join freigeben, Tunnel, Welt-ZIP, Öffentlichkeit."""
    root = Path(root)
    steps: List[str] = []
    result: Dict[str, Any] = {"mode": "internet", "steps": steps}

    try:
        _dedupe_hub(root)
        steps.append("hub:restart")
    except Exception as exc:
        steps.append(f"hub:{exc}"[:40])

    glasfaser = _load_json(root / "control/glasfaser_offline_state.json")
    if str(glasfaser.get("active_phase_id") or "") == "during_offline":
        try:
            from analytics.glasfaser_offline_plan import apply_glasfaser_repair, set_glasfaser_phase

            set_glasfaser_phase(root, phase_id="after_online", ack=True, persist=False)
            result["glasfaser"] = apply_glasfaser_repair(root, persist=True)
            steps.append("glasfaser:comeback")
        except Exception as exc:
            result["glasfaser"] = {"ok": False, "error_de": str(exc)[:120]}

    from analytics.world_spread import activate_house_to_world

    result["welt"] = activate_house_to_world(root, force_export=True)
    steps.append("welt:export")

    from analytics.community_spread_plan import broadcast_spread, ensure_community_spread

    result["broadcast"] = broadcast_spread(root)
    result["sustain"] = ensure_community_spread(root, repair=True, persist=True)
    result["public_post"] = str(_write_public_post_ready(root))
    result["export_repair"] = _repair_export_artifacts(root)
    steps.append("broadcast+sustain")

    from analytics.community_spread_plan import collect_spread_urls

    urls = collect_spread_urls(root)
    join_base = str(urls.get("remote_url") or "").rstrip("/")
    join_ok = _join_page_ok(join_base)
    health_ok = _http_ok(join_base, timeout=8.0)
    result["internet_checks"] = {
        "health_ok": health_ok,
        "join_ok": join_ok,
        "join_url": f"{join_base}/join" if join_base else "",
    }
    result["ok"] = bool(health_ok and join_ok and result.get("welt", {}).get("ok"))
    result["progress"] = build_spread_progress(root)
    bars = (result["progress"] or {}).get("bars") or {}
    result["headline_de"] = (
        f"Internet-Spread — join={join_ok} health={health_ok}, infra {bars.get('infrastruktur', {}).get('pct')}%"
        if result["ok"]
        else "Internet-Spread — join/health oder Tunnel rot (siehe internet_checks)"
    )
    result["facts"] = build_spread_facts(root, progress=result["progress"])
    result["operator_de"] = [
        f"WhatsApp: evidence/spread_whatsapp_de.txt",
        f"Forum: evidence/community_spread_forum_de.txt",
        f"Welt-ZIP: ~/world_worker_LITE.zip",
        f"Join: {join_base}/join" if join_base else "Join: —",
    ]
    result["updated_at_utc"] = _utc_now()
    atomic_write_json(root / _EVIDENCE_REL, result)
    atomic_write_json(root / Path("evidence/internet_spread_latest.json"), result)
    return result


def run_spread_efficient(root: Path, mode: str = "voll") -> Dict[str, Any]:
    """
    Ein Einstieg — maximal effizient:
      verify | haus | welt | voll
    """
    root = Path(root)
    mode = (mode or "voll").strip().lower()
    if mode not in {"verify", "haus", "welt", "voll", "internet"}:
        return {"ok": False, "message_de": f"Unbekannter Modus: {mode}"}

    if mode == "verify":
        return verify_spread_security(root)

    if mode == "internet":
        return expand_internet_spread(root)

    sec = verify_spread_security(root)
    blockers = [c for c in sec.get("checks") or [] if not c.get("ok")]
    if any(c.get("id") == "safety_flags" for c in blockers):
        return {**sec, "ok": False, "message_de": "Hard-Block — Echtgeld/Auto-Promotion", "mode": mode}

    result: Dict[str, Any] = {"mode": mode, "security_pre": sec, "steps": []}

    if mode == "voll":
        try:
            _dedupe_hub(root)
            result["steps"].append("hub:dedupe+restart")
        except Exception as exc:
            result["steps"].append(f"hub:dedupe:{exc}"[:40])

    if mode in {"haus", "voll"}:
        from analytics.preview_federation import apply_lan_spread

        result["haus"] = apply_lan_spread(root, export_lite=True, restart_hub=True)
        result["steps"].append("haus:lan+zip")

    if mode in {"welt", "voll"}:
        from analytics.world_spread import activate_house_to_world

        result["welt"] = activate_house_to_world(root, force_export=True)
        result["steps"].append("welt:tunnel+zip")

    if mode == "voll":
        from analytics.community_spread_plan import broadcast_spread, ensure_community_spread

        result["broadcast"] = broadcast_spread(root)
        result["sustain"] = ensure_community_spread(root, repair=True, persist=True)
        result["public_post"] = str(_write_public_post_ready(root))
        result["steps"].append("broadcast+sustain+public_post")
        result["export_repair"] = _repair_export_artifacts(root)

    sec2 = verify_spread_security(root)
    result["security_final"] = sec2
    result["ok"] = bool(sec2.get("ok"))
    result["progress"] = build_spread_progress(root)
    bars = (result["progress"] or {}).get("bars") or {}
    sec_passed = int(sec2.get("checks_passed") or 0)
    sec_total = int(sec2.get("checks_total") or 0)
    bar_line = ", ".join(f"{k} {v.get('pct')}%" for k, v in bars.items())
    result["headline_de"] = (
        f"Spread {mode} — verify {sec_passed}/{sec_total}, {bar_line}"
        if result["ok"]
        else f"Spread {mode} — verify {sec_passed}/{sec_total} BLOCKIERT"
    )
    result["facts"] = build_spread_facts(root, progress=result["progress"], security=sec2)
    result["operator_de"] = _operator_card(root, mode, result)
    result["updated_at_utc"] = _utc_now()
    atomic_write_json(root / _EVIDENCE_REL, result)
    return result


def _operator_card(root: Path, mode: str, result: Dict[str, Any]) -> List[str]:
    from analytics.community_spread_plan import collect_spread_urls

    urls = collect_spread_urls(root)
    lines = [
        "EFFIZIENT + SICHER:",
        f"  Haus USB: bash tools/king_ops.sh lan-usb --usb /media/…",
        f"  LAN: {urls.get('lan_url') or '—'}/join",
        f"  Welt: {urls.get('remote_url') or '—'}/join",
        f"  Haus-ZIP: ~/glasfaser_NOTFALL_worker_LITE.zip",
        f"  Welt-ZIP: ~/world_worker_LITE.zip",
        "  Kein Broker · kein Echtgeld · join_token Pflicht",
    ]
    if mode == "verify":
        lines = ["Nur Prüfung — evidence/spread_secure_ops_latest.json"]
    return lines
