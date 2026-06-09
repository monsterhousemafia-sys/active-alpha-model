"""R3 Laufzeit-Upgrades — Vorschlag, Erklärung, Bestätigung vor Apply."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_SCAN_COOLDOWN_SEC = 90.0

_PROFILE_REL = Path("control/r3_runtime_profile.json")
_CATALOG_REL = Path("control/r3_runtime_upgrade_catalog.json")
_EVIDENCE_REL = Path("evidence/r3_runtime_upgrade_latest.json")

_DEFAULT_PROFILE: Dict[str, Any] = {
    "schema_version": 1,
    "profile_id": "stable_v1",
    "label_de": "Stabil — Standard",
    "mirror_poll_ms": 45_000,
    "mirror_prep_every_n_polls": 4,
    "mirror_reload_on_evidence_change": True,
    "mirror_soft_update": False,
    "cache_stale_sec": 300,
}


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


def load_runtime_profile(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _PROFILE_REL)
    out = {**_DEFAULT_PROFILE, **{k: v for k, v in doc.items() if k in _DEFAULT_PROFILE or k.startswith("profile_")}}
    out.update({k: doc[k] for k in ("profile_id", "label_de", "applied_at_utc", "source_de", "status") if k in doc})
    try:
        out["mirror_poll_ms"] = max(15_000, min(120_000, int(out.get("mirror_poll_ms") or 45_000)))
    except (TypeError, ValueError):
        out["mirror_poll_ms"] = 45_000
    try:
        out["mirror_prep_every_n_polls"] = max(1, min(12, int(out.get("mirror_prep_every_n_polls") or 4)))
    except (TypeError, ValueError):
        out["mirror_prep_every_n_polls"] = 4
    try:
        out["cache_stale_sec"] = max(60, min(600, float(out.get("cache_stale_sec") or 300)))
    except (TypeError, ValueError):
        out["cache_stale_sec"] = 300.0
    out["mirror_reload_on_evidence_change"] = bool(out.get("mirror_reload_on_evidence_change", True))
    out["mirror_soft_update"] = bool(out.get("mirror_soft_update", False))
    return out


def load_upgrade_catalog(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CATALOG_REL)


def load_upgrade_evidence(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _EVIDENCE_REL)
    if not doc:
        profile = load_runtime_profile(root)
        return {
            "schema_version": 1,
            "applied_profile_id": str(profile.get("profile_id") or "stable_v1"),
            "pending": None,
            "dismissed_ids": [],
            "history": [],
        }
    return doc


def _evidence_fresh(path: Path, max_age_sec: float = _SCAN_COOLDOWN_SEC) -> bool:
    if not path.is_file():
        return False
    try:
        return (time.time() - path.stat().st_mtime) < float(max_age_sec)
    except OSError:
        return False


def _mirror_state_ready_light(root: Path) -> bool:
    """Leichtgewicht — kein build_exec_mirror_state (vermeidet Rekursion)."""
    root = Path(root)
    for rel in (
        "evidence/pilot_investment_plan_latest.json",
        "evidence/r3_freigabe_latest.json",
        "evidence/r3_stock_orders_latest.json",
    ):
        p = root / rel
        if not p.is_file():
            return False
        try:
            if p.stat().st_size < 20:
                return False
        except OSError:
            return False
    return True


def _detection_ok(root: Path, detection: Dict[str, Any]) -> bool:
    if not detection:
        return True
    if detection.get("requires_mirror_state_ok"):
        if not _mirror_state_ready_light(root):
            return False
    if detection.get("requires_stack_ok"):
        stack = _load_json(root / "evidence/stack_integrity_latest.json")
        if not stack.get("stack_ok"):
            return False
    return True


def _upgrade_row(catalog_entry: Dict[str, Any]) -> Dict[str, Any]:
    target = dict(catalog_entry.get("target_profile") or {})
    return {
        "proposal_id": str(catalog_entry.get("id") or ""),
        "label_de": str(catalog_entry.get("label_de") or "R3-Update"),
        "summary_de": str(catalog_entry.get("summary_de") or ""),
        "changes_de": list(catalog_entry.get("changes_de") or []),
        "target_profile_id": str(target.get("profile_id") or ""),
        "current_profile_id": str(catalog_entry.get("replaces_profile_id") or ""),
        "target_profile": target,
    }


def scan_runtime_upgrades(
    root: Path,
    *,
    persist: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """Erkennt bessere Laufzeitprofile — legt pending an, wendet nichts an."""
    root = Path(root)
    evidence_path = root / _EVIDENCE_REL
    if persist and not force and _evidence_fresh(evidence_path):
        cached = load_upgrade_evidence(root)
        if cached.get("schema_version"):
            return cached

    profile = load_runtime_profile(root)
    catalog = load_upgrade_catalog(root)
    evidence = load_upgrade_evidence(root)
    applied_id = str(profile.get("profile_id") or evidence.get("applied_profile_id") or "stable_v1")
    dismissed = {str(x) for x in (evidence.get("dismissed_ids") or [])}
    pending = evidence.get("pending")
    candidates: List[Dict[str, Any]] = []

    for entry in catalog.get("upgrades") or []:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("id") or "")
        if not pid or pid in dismissed:
            continue
        replaces = str(entry.get("replaces_profile_id") or "")
        target = entry.get("target_profile") or {}
        target_id = str(target.get("profile_id") or "")
        if not target_id or target_id == applied_id:
            continue
        if replaces and replaces != applied_id:
            continue
        if not _detection_ok(root, dict(entry.get("detection") or {})):
            continue
        candidates.append(_upgrade_row(entry))

    chosen: Optional[Dict[str, Any]] = candidates[0] if candidates else None
    if chosen:
        if not pending or pending.get("proposal_id") != chosen["proposal_id"]:
            pending = {
                **chosen,
                "status": "awaiting_confirmation",
                "proposed_at_utc": _utc_now(),
                "confirmation_de": "Bitte prüfen und bestätigen — R3 übernimmt erst danach die neue Funktionsweise.",
            }
    elif pending and pending.get("status") == "awaiting_confirmation":
        pending = None

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "applied_profile_id": applied_id,
        "applied_label_de": str(profile.get("label_de") or ""),
        "pending": pending,
        "dismissed_ids": sorted(dismissed),
        "history": list(evidence.get("history") or [])[-20:],
        "candidates_found": len(candidates),
        "headline_de": (
            f"R3-Update bereit: {pending.get('label_de')}"
            if pending
            else f"Laufzeitprofil aktiv: {profile.get('label_de') or applied_id}"
        ),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_upgrade_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    profile = load_runtime_profile(root)
    evidence = load_upgrade_evidence(root)
    pending = evidence.get("pending")
    return {
        "schema_version": 1,
        "updated_at_utc": evidence.get("updated_at_utc") or _utc_now(),
        "applied_profile": profile,
        "pending": pending,
        "has_pending": bool(pending and pending.get("status") == "awaiting_confirmation"),
        "headline_de": evidence.get("headline_de") or str(profile.get("label_de") or ""),
    }


def confirm_runtime_upgrade(root: Path, *, proposal_id: str) -> Dict[str, Any]:
    root = Path(root)
    evidence = load_upgrade_evidence(root)
    pending = evidence.get("pending") or {}
    pid = str(proposal_id or pending.get("proposal_id") or "").strip()
    if not pid or pending.get("proposal_id") != pid:
        return {"ok": False, "message_de": "Kein passender Update-Vorschlag — bitte Seite neu laden."}
    target = dict(pending.get("target_profile") or {})
    if not target.get("profile_id"):
        return {"ok": False, "message_de": "Zielprofil unvollständig — Update abgebrochen."}

    profile_doc = {
        "schema_version": 1,
        "status": "AUTHORITATIVE",
        **target,
        "applied_at_utc": _utc_now(),
        "source_de": f"Bestätigt: {pending.get('label_de') or pid}",
        "confirmed_proposal_id": pid,
    }
    atomic_write_json(root / _PROFILE_REL, profile_doc)

    history = list(evidence.get("history") or [])
    history.append(
        {
            "proposal_id": pid,
            "label_de": pending.get("label_de"),
            "applied_at_utc": profile_doc["applied_at_utc"],
            "from_profile_id": pending.get("current_profile_id"),
            "to_profile_id": target.get("profile_id"),
            "changes_de": list(pending.get("changes_de") or []),
        }
    )
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "applied_profile_id": str(target.get("profile_id")),
        "applied_label_de": str(target.get("label_de") or ""),
        "pending": None,
        "dismissed_ids": list(evidence.get("dismissed_ids") or []),
        "history": history[-20:],
        "last_confirm_de": f"Übernommen: {pending.get('label_de') or pid}",
        "headline_de": f"Laufzeitprofil aktiv: {target.get('label_de') or target.get('profile_id')}",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)

    try:
        from analytics.desktop_shell_cache import warm_desktop_cache

        warm_desktop_cache(root, fast=False, block=False)
    except Exception:
        pass

    return {
        "ok": True,
        "message_de": doc["last_confirm_de"],
        "applied_profile": load_runtime_profile(root),
        "changes_de": list(pending.get("changes_de") or []),
    }


def align_r3_surface(
    root: Path,
    *,
    scan_upgrades: bool = True,
    warm_cache: bool = True,
    sync_flow: bool = False,
    persist: bool = True,
    port: int = 17890,
) -> Dict[str, Any]:
    """Hub/Mirror/Cockpit — Laufzeitprofil, Upgrade-Scan und Cache aufeinander abstimmen."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    if scan_upgrades:
        try:
            upgrade_doc = scan_runtime_upgrades(root, persist=persist, force=not persist)
            pending = upgrade_doc.get("pending")
            steps.append(
                {
                    "step": "scan_upgrades",
                    "ok": True,
                    "pending": bool(pending),
                    "proposal_id": (pending or {}).get("proposal_id"),
                }
            )
        except Exception as exc:
            steps.append({"step": "scan_upgrades", "ok": False, "error_de": str(exc)[:120]})

    if sync_flow:
        try:
            from analytics.r3_flow_orchestrator import sync_r3_flow

            flow_doc = sync_r3_flow(root, source_node="align", warm_cache=False, persist=persist)
            steps.append(
                {
                    "step": "sync_flow",
                    "ok": bool(flow_doc.get("ok", True)),
                    "fluidity_pct": flow_doc.get("fluidity_pct"),
                }
            )
        except Exception as exc:
            steps.append({"step": "sync_flow", "ok": False, "error_de": str(exc)[:120]})

    if warm_cache:
        try:
            from analytics.desktop_shell_cache import write_desktop_cache
            from analytics.r3_exec_mirror import render_r3_exec_mirror_page

            body = render_r3_exec_mirror_page(root, port=int(port))
            write_desktop_cache(root, body, fast=False)
            steps.append({"step": "warm_cache", "ok": len(body) >= 120, "bytes": len(body)})
        except Exception as exc:
            steps.append({"step": "warm_cache", "ok": False, "error_de": str(exc)[:120]})

    try:
        from analytics.r3_local_growth import scan_local_growth

        stack_ok = bool(_load_json(root / Path("evidence/stack_integrity_latest.json")).get("stack_ok"))
        scan_local_growth(root, persist=True, force=True, fast=stack_ok)
    except Exception:
        pass

    try:
        from analytics.series_readiness import scan_series_readiness

        scan_series_readiness(root, persist=True, force=True, fast=True)
    except Exception:
        pass

    profile = load_runtime_profile(root)
    status = build_upgrade_status(root)
    pending = status.get("pending") or {}
    ok = all(s.get("ok", True) for s in steps) if steps else True
    confirm = (
        f"Update bereit: {pending.get('label_de')} — in R3 bestätigen (Übernehmen/Später)"
        if status.get("has_pending")
        else f"Laufzeitprofil aktiv: {profile.get('label_de') or profile.get('profile_id')}"
    )
    hub_base = "http://127.0.0.1:17890"
    surface = "/r3"
    try:
        from analytics.alpha_model_local_runtime import load_local_runtime
        from analytics.r3_runtime import default_surface_path

        hub_base = str(load_local_runtime(root).get("hub_url") or hub_base).rstrip("/")
        surface = str(default_surface_path(root) or surface)
    except Exception:
        pass
    return {
        "ok": ok,
        "updated_at_utc": _utc_now(),
        "steps": steps,
        "runtime_profile_id": str(profile.get("profile_id") or ""),
        "runtime_profile_label_de": str(profile.get("label_de") or ""),
        "upgrade_pending": bool(status.get("has_pending")),
        "upgrade_headline_de": str(status.get("headline_de") or ""),
        "pending": pending if status.get("has_pending") else None,
        "confirmation_de": confirm,
        "hub_url": f"{hub_base}{surface}",
    }


def dismiss_runtime_upgrade(root: Path, *, proposal_id: str) -> Dict[str, Any]:
    root = Path(root)
    evidence = load_upgrade_evidence(root)
    pending = evidence.get("pending") or {}
    pid = str(proposal_id or pending.get("proposal_id") or "").strip()
    if not pid:
        return {"ok": False, "message_de": "Kein Vorschlag zum Ablehnen."}
    dismissed = sorted({str(x) for x in (evidence.get("dismissed_ids") or [])} | {pid})
    doc = {
        **evidence,
        "updated_at_utc": _utc_now(),
        "pending": None,
        "dismissed_ids": dismissed,
        "headline_de": f"Vorschlag zurückgestellt — Profil: {evidence.get('applied_label_de') or evidence.get('applied_profile_id')}",
        "last_dismiss_de": f"Später: {pending.get('label_de') or pid}",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return {"ok": True, "message_de": doc["last_dismiss_de"], "dismissed_id": pid}
