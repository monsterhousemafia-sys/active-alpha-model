"""R3 lokales Wachstum — alles unter 127.0.0.1, Fähigkeiten wachsen mit der Zeit."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_SCAN_COOLDOWN_SEC = 120.0

_POLICY_REL = Path("control/r3_local_growth.json")
_EVIDENCE_REL = Path("evidence/r3_local_growth_latest.json")
_HISTORY_REL = Path("evidence/r3_local_growth_history.jsonl")


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


def load_growth_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def local_primary_url(root: Path, *, path: str = "/r3") -> str:
    root = Path(root)
    try:
        from analytics.r3_local_first import local_hub_authoritative_url

        return local_hub_authoritative_url(root, path=path)
    except Exception:
        return f"http://127.0.0.1:17890{path}"


def local_confirmation_de(root: Path) -> str:
    """Primäre UI-Zeile — lokal first, Spiegel optional."""
    root = Path(root)
    hub = local_primary_url(root, path="/r3")
    try:
        from analytics.r3_local_first import https_mirror_base_url

        mirror = https_mirror_base_url(root)
    except Exception:
        mirror = None
    base = f"Alles lokal · {hub} — wächst mit der Zeit"
    if mirror:
        return f"{base} · Spiegel optional"
    return base


def _evidence_fresh(path: Path, max_age_sec: float = _SCAN_COOLDOWN_SEC) -> bool:
    if not path.is_file():
        return False
    try:
        return (time.time() - path.stat().st_mtime) < float(max_age_sec)
    except OSError:
        return False


def _stack_surface_ok(stack: Dict[str, Any], cache: Dict[str, Any]) -> bool:
    r3 = stack.get("r3") or {}
    return bool(r3.get("surface_page_ok") or int(cache.get("bytes") or 0) >= 120)


def _check_capability(root: Path, cap_id: str, *, fast: bool = False) -> Dict[str, Any]:
    root = Path(root)
    ok = False
    detail = "—"
    stack = _load_json(root / "evidence/stack_integrity_latest.json")
    cache = _load_json(root / "evidence/desktop_shell_cache_meta.json")
    stack_ok = bool(stack.get("stack_ok"))

    if cap_id == "hub_local":
        if fast or stack_ok:
            ok = bool(stack.get("hub_ok") or stack.get("stack_ok"))
            detail = "127.0.0.1:17890 (stack)" if stack_ok else "127.0.0.1:17890 (cache)"
        if not ok:
            try:
                from analytics.hub_runtime import DEFAULT_PORT, is_healthy

                ok = bool(is_healthy(DEFAULT_PORT, timeout=0.6))
                detail = "127.0.0.1:17890"
            except Exception as exc:
                detail = str(exc)[:60]
    elif cap_id == "mirror_api":
        if fast or stack_ok:
            r3 = stack.get("r3") or {}
            ok = bool(r3.get("mirror_api_ok") or stack.get("stack_ok"))
            detail = "/api/r3/mirror (stack)" if stack_ok else "/api/r3/mirror (cache)"
        if not ok:
            try:
                from analytics.r3_runtime import is_mirror_api_ready

                ok = bool(is_mirror_api_ready())
                detail = "/api/r3/mirror"
            except Exception:
                ok = False
    elif cap_id == "surface_r3":
        if fast or stack_ok:
            ok = _stack_surface_ok(stack, cache)
            detail = "/r3 (stack)" if stack_ok else "/r3 (cache)"
        if not ok:
            try:
                from analytics.r3_runtime import is_surface_page_ready

                ok = bool(is_surface_page_ready())
                detail = "/r3"
            except Exception:
                ok = False
    elif cap_id == "plan_evidence":
        p = root / "evidence/pilot_investment_plan_latest.json"
        ok = p.is_file() and p.stat().st_size > 40
        detail = str(p) if ok else "fehlt"
    elif cap_id == "trading_functions":
        doc = _load_json(root / "evidence/r3_trading_functions_latest.json")
        ok = len(doc.get("functions") or []) >= 3
        detail = f"{len(doc.get('functions') or [])} Funktionen"
    elif cap_id == "runtime_profile":
        try:
            from analytics.r3_runtime_upgrade import load_runtime_profile

            prof = load_runtime_profile(root)
            ok = bool(prof.get("profile_id"))
            detail = str(prof.get("label_de") or prof.get("profile_id"))
        except Exception:
            ok = False
    elif cap_id == "upgrade_gate":
        doc = _load_json(root / "evidence/r3_runtime_upgrade_latest.json")
        catalog = _load_json(root / "control/r3_runtime_upgrade_catalog.json")
        ok = catalog.get("upgrades") and doc.get("schema_version")
        pending = doc.get("pending")
        detail = (
            f"Vorschlag: {(pending or {}).get('label_de')}"
            if pending
            else "Gate aktiv"
        )
    elif cap_id == "stack_integrity":
        stack = _load_json(root / "evidence/stack_integrity_latest.json")
        ok = bool(stack.get("stack_ok"))
        detail = "OK" if ok else "prüfen"
    elif cap_id == "king_local":
        ok = False
        detail = "Ollama 127.0.0.1:11434"
        try:
            import socket
            from urllib.parse import urlparse

            runtime = _load_json(root / "control/alpha_model_local_runtime.json")
            base = str(runtime.get("ollama_base_url") or "http://127.0.0.1:11434")
            parsed = urlparse(base)
            host = parsed.hostname or "127.0.0.1"
            port = int(parsed.port or 11434)
            with socket.create_connection((host, port), timeout=0.5):
                ok = True
        except Exception:
            ok = False
    return {"id": cap_id, "ok": ok, "detail_de": detail[:80]}


def scan_local_growth(
    root: Path,
    *,
    persist: bool = True,
    force: bool = False,
    fast: bool = False,
) -> Dict[str, Any]:
    """Lokale Fähigkeiten + Meilensteine — R3-Reifegrad."""
    root = Path(root)
    evidence_path = root / _EVIDENCE_REL
    if persist and not force and _evidence_fresh(evidence_path):
        cached = _load_json(evidence_path)
        if cached.get("schema_version"):
            return cached

    policy = load_growth_policy(root)
    prev = _load_json(evidence_path)
    caps_def = list(policy.get("capabilities") or [])
    cap_states: List[Dict[str, Any]] = []
    weight_ok = 0
    weight_total = 0
    for cap in caps_def:
        if not isinstance(cap, dict):
            continue
        cid = str(cap.get("id") or "")
        w = int(cap.get("weight") or 10)
        weight_total += w
        st = _check_capability(root, cid, fast=fast)
        st["label_de"] = str(cap.get("label_de") or cid)
        st["weight"] = w
        if st.get("ok"):
            weight_ok += w
        cap_states.append(st)

    pct = int(round(100 * weight_ok / weight_total)) if weight_total else 0
    milestones_out: List[Dict[str, Any]] = []
    for ms in policy.get("milestones") or []:
        if not isinstance(ms, dict):
            continue
        ids = list(ms.get("capability_ids") or [])
        states = {c["id"]: c for c in cap_states}
        ms_ok = all(states.get(i, {}).get("ok") for i in ids) if ids else False
        milestones_out.append(
            {
                "id": ms.get("id"),
                "label_de": ms.get("label_de"),
                "ok": ms_ok,
                "capabilities": ids,
            }
        )
    ms_ok_n = sum(1 for m in milestones_out if m.get("ok"))
    ms_total = len(milestones_out) or 1

    try:
        from analytics.r3_runtime_upgrade import build_upgrade_status

        upgrade = build_upgrade_status(root)
    except Exception:
        upgrade = {}

    profile_id = ""
    try:
        from analytics.r3_runtime_upgrade import load_runtime_profile

        profile_id = str(load_runtime_profile(root).get("profile_id") or "")
    except Exception:
        pass

    linux_doc: Dict[str, Any] = {}
    try:
        from analytics.linux_potential import scan_linux_potential

        linux_doc = scan_linux_potential(root, persist=False)
    except Exception:
        pass

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "local_only": True,
        "local_primary_url": local_primary_url(root),
        "confirmation_de": local_confirmation_de(root),
        "linux_potential_pct": int(linux_doc.get("potential_pct") or 0),
        "linux_potential_headline_de": str(linux_doc.get("headline_de") or ""),
        "growth_pct": pct,
        "capabilities_ok": sum(1 for c in cap_states if c.get("ok")),
        "capabilities_total": len(cap_states),
        "milestones_ok": ms_ok_n,
        "milestones_total": len(milestones_out),
        "milestones": milestones_out,
        "capabilities": cap_states,
        "runtime_profile_id": profile_id,
        "upgrade_pending": bool(upgrade.get("has_pending")),
        "headline_de": f"R3 lokal {pct}% — {ms_ok_n}/{len(milestones_out)} Meilensteine",
        "next_growth_de": _next_growth_hint(cap_states, milestones_out, upgrade),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
        prev_pct = int(prev.get("growth_pct") or 0)
        if pct != prev_pct or ms_ok_n != int(prev.get("milestones_ok") or 0):
            _append_history(
                root,
                {
                    "at_utc": doc["updated_at_utc"],
                    "growth_pct": pct,
                    "milestones_ok": ms_ok_n,
                    "profile_id": profile_id,
                    "event_de": doc["headline_de"],
                },
            )
    return doc


def _next_growth_hint(
    caps: List[Dict[str, Any]],
    milestones: List[Dict[str, Any]],
    upgrade: Dict[str, Any],
) -> str:
    if upgrade.get("has_pending"):
        pend = upgrade.get("pending") or {}
        return f"Nächster Schritt: {pend.get('label_de')} in /r3 bestätigen"
    open_caps = [c for c in caps if not c.get("ok")]
    if open_caps:
        return f"Lokal ausbauen: {open_caps[0].get('label_de')}"
    open_ms = [m for m in milestones if not m.get("ok")]
    if open_ms:
        return f"Meilenstein: {open_ms[0].get('label_de')}"
    return "R3 lokal vollständig — neue Upgrades erscheinen im Katalog mit Bestätigung"


def _append_history(root: Path, entry: Dict[str, Any]) -> None:
    path = Path(root) / _HISTORY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def verify_local_operational(root: Path) -> Dict[str, Any]:
    """Fail-closed: Kern lokal ohne Internet."""
    root = Path(root)
    doc = scan_local_growth(root, persist=False)
    required = {"hub_local", "mirror_api", "surface_r3", "plan_evidence"}
    caps = {c["id"]: c for c in doc.get("capabilities") or []}
    missing = [caps[r]["label_de"] for r in required if not caps.get(r, {}).get("ok")]
    ok = not missing
    return {
        "ok": ok,
        "local_only": True,
        "growth_pct": doc.get("growth_pct"),
        "missing_de": missing,
        "confirmation_de": doc.get("confirmation_de"),
        "headline_de": "R3 lokal betriebsbereit" if ok else f"R3 lokal — fehlt: {', '.join(missing)}",
    }
