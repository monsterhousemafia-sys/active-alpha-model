"""Autonome Spread-Freigabe — Verbreitung ohne manuelle Taktung; Aktien-Veto beim Operator."""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/spread_autonomous.json")
_EVIDENCE_REL = Path("evidence/spread_autonomous_latest.json")
_AUDIT_REL = Path("evidence/spread_autonomous_audit.jsonl")


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


def load_spread_autonomous_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL)


def is_autonomous_spread_enabled(root: Path) -> bool:
    pol = load_spread_autonomous_policy(root)
    return bool(pol.get("autonomous_spread_enabled"))


def is_autonomous_spread_paused(root: Path) -> bool:
    pol = load_spread_autonomous_policy(root)
    return bool(pol.get("paused"))


def operator_stock_veto_active(root: Path) -> bool:
    """Operator behält letztes Wort bei Aktien — immer true wenn autonom aktiv."""
    if not is_autonomous_spread_enabled(root):
        return True
    pol = load_spread_autonomous_policy(root)
    return bool(pol.get("operator_stock_veto", True))


def _append_audit(root: Path, event: Dict[str, Any]) -> None:
    root = Path(root)
    path = root / _AUDIT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {**event, "at_utc": _utc_now()}
    with path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def pause_autonomous_spread(root: Path, *, reason_de: str = "Operator") -> Dict[str, Any]:
    root = Path(root)
    pol = load_spread_autonomous_policy(root)
    pol["paused"] = True
    pol["paused_at_utc"] = _utc_now()
    pol["paused_by_de"] = reason_de
    atomic_write_json(root / _CONFIG_REL, pol)
    _append_audit(root, {"event": "pause", "reason_de": reason_de})
    return {"ok": True, "paused": True, "detail_de": "Spread autonom pausiert"}


def resume_autonomous_spread(root: Path) -> Dict[str, Any]:
    root = Path(root)
    pol = load_spread_autonomous_policy(root)
    pol["paused"] = False
    pol.pop("paused_at_utc", None)
    pol.pop("paused_by_de", None)
    atomic_write_json(root / _CONFIG_REL, pol)
    _append_audit(root, {"event": "resume"})
    return {"ok": True, "paused": False, "detail_de": "Spread autonom fortgesetzt"}


def _assert_stock_veto_invariants(root: Path) -> Dict[str, Any]:
    from analytics.spread_secure_ops import _check_safety_flags

    safety = _check_safety_flags(root)
    stock_ok = bool(safety.get("ok"))
    try:
        from execution.confirmed_live.live_trading_enablement import live_submission_allowed

        orders_auto = bool(live_submission_allowed(root))
    except Exception:
        orders_auto = False
    ok = stock_ok and not orders_auto
    return {
        "id": "operator_stock_veto",
        "ok": ok,
        "detail_de": (
            "Aktien-Veto aktiv — keine autonomen Orders"
            if ok
            else "BLOCK: Safety-Flags oder Live-Submission verletzt Aktien-Veto"
        ),
        "orders_auto": orders_auto,
        "safety_ok": stock_ok,
    }


def run_autonomous_preflight(root: Path) -> Dict[str, Any]:
    """Fail-closed vor autonomen Sends."""
    root = Path(root)
    pol = load_spread_autonomous_policy(root)
    checks: List[Dict[str, Any]] = []

    if not pol.get("autonomous_spread_enabled"):
        return {
            "ok": False,
            "skipped": True,
            "headline_de": "Spread autonom nicht freigegeben",
            "checks": checks,
        }

    checks.append(
        {
            "id": "autonomous_pause",
            "ok": not is_autonomous_spread_paused(root),
            "detail_de": "pausiert" if is_autonomous_spread_paused(root) else "aktiv",
        }
    )
    checks.append(_assert_stock_veto_invariants(root))

    if pol.get("preflight_required", True):
        from analytics.spread_secure_ops import verify_spread_security

        sec = verify_spread_security(root)
        checks.append(
            {
                "id": "spread_security",
                "ok": bool(sec.get("ok")),
                "detail_de": sec.get("headline_de") or "—",
            }
        )
        try:
            from analytics.secret_leak_scan import scan_for_leaks

            leak = scan_for_leaks(root)
            checks.append(
                {
                    "id": "leak_scan",
                    "ok": bool(leak.get("ok")),
                    "detail_de": leak.get("headline_de") or "—",
                    "leak_count": leak.get("leak_count"),
                }
            )
        except Exception as exc:
            checks.append({"id": "leak_scan", "ok": False, "detail_de": str(exc)[:80]})

        try:
            from analytics.community_spread_plan import collect_spread_urls
            from analytics.whatsapp_spread import verify_join_reachable

            urls = collect_spread_urls(root)
            candidates: List[tuple[str, str]] = []
            for key in ("join_lan", "join_remote"):
                url = str(urls.get(key) or "").strip()
                if url:
                    candidates.append((key, url))
            if not candidates:
                checks.append(
                    {
                        "id": "join_reachable",
                        "ok": True,
                        "detail_de": "skip — keine Join-URLs",
                    }
                )
            else:
                attempts: List[Dict[str, Any]] = []
                any_ok = False
                for key, url in candidates:
                    join_check = verify_join_reachable(url)
                    attempts.append({"url_key": key, "url": url, **join_check})
                    if join_check.get("ok"):
                        any_ok = True
                ok_detail = next(
                    (a.get("detail_de") for a in attempts if a.get("ok")),
                    attempts[-1].get("detail_de") if attempts else "—",
                )
                checks.append(
                    {
                        "id": "join_reachable",
                        "ok": any_ok,
                        "detail_de": ok_detail or "—",
                        "attempts": attempts,
                    }
                )
        except Exception as exc:
            checks.append({"id": "join_reachable", "ok": True, "detail_de": f"skip:{exc}"[:60]})

    ok = all(c.get("ok") for c in checks)
    doc = {
        "ok": ok,
        "headline_de": "Preflight OK — autonomer Spread erlaubt" if ok else "Preflight BLOCKIERT",
        "checks": checks,
        "updated_at_utc": _utc_now(),
    }
    _append_audit(root, {"event": "preflight", "ok": ok, "checks": [c.get("id") for c in checks]})
    return doc


def release_autonomous_spread(
    root: Path,
    *,
    released_by_de: str = "Operator",
    whatsapp_auto: bool = True,
    worker_daemon: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    doc = {
        "schema_version": 1,
        "autonomous_spread_enabled": True,
        "operator_stock_veto": True,
        "paused": False,
        "preflight_required": True,
        "released_by_de": released_by_de,
        "released_at_utc": _utc_now(),
        "whatsapp_auto_on_tick": whatsapp_auto,
        "worker_daemon_ensure": worker_daemon,
        "reward_message_de": (
            "Jeder mit CPU verdient mit — kollektive Rechenleistung, offenes Research, kein Abo."
        ),
        "invariants_de": [
            "Kein Echtgeld · keine Auto-Orders ohne Operator-Bestätigung",
            "Spread nur eigene WhatsApp · join_token Pflicht",
            "Safety-Flags bleiben false",
        ],
    }
    atomic_write_json(root / _CONFIG_REL, doc)
    _append_audit(root, {"event": "release", "released_by_de": released_by_de})
    return doc


def _ensure_worker_daemon(root: Path) -> Dict[str, Any]:
    from analytics.spread_intensify import _ensure_local_worker_daemon

    return _ensure_local_worker_daemon(root)


def _try_whatsapp_autonomous(root: Path) -> Dict[str, Any]:
    from analytics.terminal_runtime import detect_runtime_context, run_in_user_graphical_session
    from analytics.whatsapp_spread import complete_self_send, load_whatsapp_config

    cfg = load_whatsapp_config(root)
    if str(cfg.get("auto_send_mode") or "auto").strip().lower() == "manual":
        return {"ok": False, "skipped": True, "detail_de": "auto_send_mode=manual"}
    ctx = detect_runtime_context()
    if ctx.get("interactive_tty") and ctx.get("can_auto_send"):
        return complete_self_send(root, dry_run=False)
    res = run_in_user_graphical_session(
        ["bash", "tools/whatsapp_spread.sh", "durch"],
        cwd=root,
        timeout_s=180.0,
    )
    return {
        "ok": bool(res.get("ok")),
        "session_run": res,
        "runtime": ctx,
        "detail_de": "WhatsApp via graphical session" if res.get("ok") else "WhatsApp-Session fehlgeschlagen",
    }


def run_autonomous_spread_sustain(
    root: Path,
    *,
    execute_whatsapp: Optional[bool] = None,
) -> Dict[str, Any]:
    """Leichter Sustain-Pfad — Worker + optional WhatsApp, ohne spread voll."""
    root = Path(root)
    pol = load_spread_autonomous_policy(root)
    if not pol.get("autonomous_spread_enabled"):
        return {"ok": False, "skipped": True, "headline_de": "Spread autonom nicht freigegeben"}

    preflight = run_autonomous_preflight(root)
    if not preflight.get("ok"):
        doc = {
            "ok": False,
            "headline_de": "Autonomer Sustain BLOCKIERT — Preflight",
            "preflight": preflight,
            "updated_at_utc": _utc_now(),
        }
        atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    steps: List[str] = []
    worker: Dict[str, Any] = {"skipped": True}
    if pol.get("worker_daemon_ensure", True):
        worker = _ensure_worker_daemon(root)
        steps.append(str(worker.get("detail_de") or "worker"))

    whatsapp: Dict[str, Any] = {"skipped": True}
    wa_sustain = bool(
        execute_whatsapp if execute_whatsapp is not None else pol.get("whatsapp_auto_on_tick", True)
    )
    if wa_sustain:
        try:
            whatsapp = _try_whatsapp_autonomous(root)
            steps.append(f"whatsapp:{whatsapp.get('ok')}")
            if whatsapp.get("ok"):
                from analytics.spread_shield import touch_rate_limit

                touch_rate_limit(root, autonomous=True)
        except Exception as exc:
            whatsapp = {"ok": False, "detail_de": str(exc)[:120]}
            steps.append(f"whatsapp:{exc}"[:60])

    doc = {
        "ok": True,
        "mode": "sustain",
        "headline_de": "Spread autonom sustain — Worker/WhatsApp; Aktien-Veto aktiv",
        "preflight": preflight,
        "worker_daemon": worker,
        "whatsapp": whatsapp,
        "steps": steps,
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    _append_audit(root, {"event": "sustain", "ok": True, "whatsapp_ok": whatsapp.get("ok")})
    return doc


def run_autonomous_spread_tick(
    root: Path,
    *,
    execute_whatsapp: Optional[bool] = None,
) -> Dict[str, Any]:
    root = Path(root)
    pol = load_spread_autonomous_policy(root)
    if not pol.get("autonomous_spread_enabled"):
        doc = {
            "ok": False,
            "skipped": True,
            "headline_de": "Spread autonom nicht freigegeben",
            "hint_de": "bash tools/king_ops.sh spread-autonom freigeben",
            "updated_at_utc": _utc_now(),
        }
        atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    preflight = run_autonomous_preflight(root)
    if not preflight.get("ok"):
        doc = {
            "ok": False,
            "headline_de": "Autonomer Spread BLOCKIERT — Preflight",
            "preflight": preflight,
            "updated_at_utc": _utc_now(),
        }
        atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    steps: List[str] = []
    prev = os.environ.get("AA_SPREAD_AUTONOMOUS_IN_PROGRESS", "")
    os.environ["AA_SPREAD_AUTONOMOUS_IN_PROGRESS"] = "1"
    try:
        from analytics.spread_secure_ops import run_spread_efficient

        spread = run_spread_efficient(root, "voll")
        steps.append(f"spread_voll:{spread.get('ok')}")
    finally:
        if prev:
            os.environ["AA_SPREAD_AUTONOMOUS_IN_PROGRESS"] = prev
        else:
            os.environ.pop("AA_SPREAD_AUTONOMOUS_IN_PROGRESS", None)

    worker: Dict[str, Any] = {"skipped": True}
    if pol.get("worker_daemon_ensure", True):
        worker = _ensure_worker_daemon(root)
        steps.append(str(worker.get("detail_de") or "worker"))

    try:
        from analytics.community_spread_plan import sync_spread_timers

        timers = sync_spread_timers(root)
        steps.append(f"timers:{len(timers)}")
    except Exception as exc:
        steps.append(f"timers:{exc}"[:60])

    wa_tick = bool(execute_whatsapp if execute_whatsapp is not None else pol.get("whatsapp_auto_on_tick", True))
    whatsapp: Dict[str, Any] = {"skipped": True}
    if wa_tick:
        try:
            whatsapp = _try_whatsapp_autonomous(root)
            steps.append(f"whatsapp:{whatsapp.get('ok')}")
            if whatsapp.get("ok"):
                from analytics.spread_shield import touch_rate_limit

                touch_rate_limit(root, autonomous=True)
        except Exception as exc:
            whatsapp = {"ok": False, "detail_de": str(exc)[:120]}
            steps.append(f"whatsapp:{exc}"[:60])

    ok = bool(spread.get("ok"))
    doc = {
        "schema_version": 1,
        "ok": ok,
        "headline_de": (
            "Spread autonom — Haus+Welt+Timer aktiv; Aktien-Veto beim Operator"
            if ok
            else "Spread autonom — unvollständig, Security prüfen"
        ),
        "preflight": preflight,
        "reward_message_de": pol.get("reward_message_de"),
        "spread": {"ok": spread.get("ok"), "headline_de": spread.get("headline_de")},
        "worker_daemon": worker,
        "whatsapp": whatsapp,
        "steps": steps,
        "policy": {
            "autonomous_spread_enabled": True,
            "operator_stock_veto": operator_stock_veto_active(root),
            "paused": is_autonomous_spread_paused(root),
        },
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    _append_audit(root, {"event": "tick", "ok": ok, "whatsapp_ok": whatsapp.get("ok")})
    return doc


def verify_autonomous_spread(root: Path) -> Dict[str, Any]:
    """Read-only — Preflight + Schott + Policy."""
    root = Path(root)
    from analytics.spread_shield import evaluate_spread_shield
    from analytics.whatsapp_spread import load_whatsapp_config, resolve_self_phone

    pol = load_spread_autonomous_policy(root)
    preflight = run_autonomous_preflight(root)
    shield_verify = evaluate_spread_shield(root, action="verify", dry_run=True)

    wa = load_whatsapp_config(root)
    phone = resolve_self_phone(wa)
    text_path = root / str(wa.get("text_ref") or "evidence/spread_whatsapp_de.txt")
    text = text_path.read_text(encoding="utf-8") if text_path.is_file() else ""
    shield_send = evaluate_spread_shield(
        root,
        action="auto_send",
        phone=phone,
        text=text,
        dry_run=False,
    )

    ok = bool(preflight.get("ok")) and bool(shield_verify.get("ok")) and bool(shield_send.get("ok"))
    doc = {
        "schema_version": 1,
        "ok": ok,
        "headline_de": (
            "Spread-Sicherheit OK — autonom + Schott geschlossen"
            if ok
            else "Spread-Sicherheit BLOCKIERT — siehe checks"
        ),
        "policy": pol,
        "preflight": preflight,
        "shield_verify": shield_verify,
        "shield_auto_send_sim": {
            **shield_send,
            "simulation": True,
            "note_de": "Gate-Prüfung ohne tatsächlichen Send",
        },
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / Path("evidence/spread_autonomous_verify_latest.json"), doc)
    _append_audit(root, {"event": "verify", "ok": ok})
    return doc
