"""R3 Quote-Keepalive — Kurse/Preise dauerhaft frisch (Ingest + Live-Quotes)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_quote_keepalive_policy.json")
_EVIDENCE_REL = Path("evidence/r3_quote_keepalive_latest.json")
_STATE_REL = Path("control/r3_quote_keepalive_state.json")


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


def load_quote_keepalive_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "enabled": True,
            "min_interval_s": 120,
            "max_stale_ingest_s": 300,
            "max_stale_quotes_s": 600,
            "max_stale_quotes_s_us_open": 120,
            "refresh_on_mirror_poll": True,
            "refresh_on_hub_open": True,
        }
    return doc


def _parse_utc(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _age_seconds(raw: Optional[str]) -> Optional[float]:
    dt = _parse_utc(str(raw or ""))
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _us_session_open() -> bool:
    try:
        from analytics.pilot_portfolio_reevaluation import _us_session_open as _open

        return bool(_open())
    except Exception:
        return False


def assess_quote_freshness(root: Path) -> Dict[str, Any]:
    """Read-only — Ingest + Live-Quote-Snapshot."""
    root = Path(root)
    policy = load_quote_keepalive_policy(root)
    ingest = _load_json(root / Path("evidence/r3_browser_ingest_latest.json"))
    reeval = _load_json(root / Path("evidence/pilot_portfolio_reevaluation_latest.json"))
    ingest_age = _age_seconds(str(ingest.get("updated_at_utc") or ""))
    max_ingest = int(policy.get("max_stale_ingest_s") or 300)

    quote_snap: Dict[str, Any] = {}
    quote_status = "MISSING"
    quote_age_s: Optional[float] = None
    try:
        from market.live_quote_engine import classify_freshness, load_live_quote_snapshot

        quote_snap = load_live_quote_snapshot(root) or {}
        if quote_snap:
            us_open = _us_session_open()
            max_q = int(
                policy.get("max_stale_quotes_s_us_open" if us_open else "max_stale_quotes_s")
                or (120 if us_open else 600)
            )
            fresh = classify_freshness(quote_snap, max_age_s=max_q)
            quote_status = str(fresh.get("status") or "UNKNOWN")
            quote_age_s = fresh.get("age_s")
    except Exception:
        pass

    reasons: List[str] = []
    if not ingest.get("ok"):
        reasons.append("ingest_fail")
    if ingest_age is None or ingest_age > max_ingest:
        reasons.append("ingest_stale")
    if not bool(ingest.get("price_current")):
        reasons.append("price_not_current")
    if quote_status != "FRESH":
        reasons.append(f"quotes_{quote_status.lower()}")
    if reeval.get("quote_fresh") is False:
        reasons.append("reeval_not_fresh")

    needs = bool(reasons)
    us_open = _us_session_open()
    return {
        "needs_refresh": needs,
        "reasons": reasons,
        "us_session_open": us_open,
        "ingest_ok": bool(ingest.get("ok")),
        "ingest_age_s": round(ingest_age, 1) if ingest_age is not None else None,
        "price_latest": ingest.get("price_latest"),
        "price_current": bool(ingest.get("price_current")),
        "quote_status": quote_status,
        "quote_age_s": quote_age_s,
        "quote_fresh_reeval": reeval.get("quote_fresh"),
        "headline_de": (
            "Kurse frisch"
            if not needs
            else f"Kurse aktualisieren — {', '.join(reasons[:3])}"
        ),
    }


def _coalesce_ok(root: Path, *, force: bool, min_interval_s: int) -> Tuple[bool, Optional[float]]:
    if force:
        return True, None
    state = _load_json(root / _STATE_REL)
    age = _age_seconds(str(state.get("last_tick_utc") or ""))
    if age is None:
        return True, None
    if age < float(min_interval_s):
        return False, age
    return True, age


def tick_quote_keepalive(
    root: Path,
    *,
    force: bool = False,
    owner: str = "keepalive",
    persist: bool = True,
) -> Dict[str, Any]:
    """Ingest + Live-Quotes wenn stale — coalesced, fail-closed ohne Internet."""
    root = Path(root)
    policy = load_quote_keepalive_policy(root)
    if not policy.get("enabled", True):
        return {"ok": True, "skipped": True, "reason_de": "keepalive_disabled"}

    assess = assess_quote_freshness(root)
    min_s = int(policy.get("min_interval_s") or 120)
    if _us_session_open() and policy.get("us_session_aggressive", True):
        min_s = min(min_s, int(policy.get("max_stale_quotes_s_us_open") or 120))

    allowed, since = _coalesce_ok(root, force=force, min_interval_s=min_s)
    if not allowed and not assess.get("needs_refresh"):
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": True,
            "skipped": True,
            "reason_de": "interval",
            "age_s": since,
            "assess": assess,
            "owner": owner,
        }
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    if not force and not assess.get("needs_refresh"):
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": True,
            "skipped": True,
            "reason_de": "fresh",
            "assess": assess,
            "owner": owner,
        }
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    steps: List[Dict[str, Any]] = []
    try:
        from analytics.r3_internet_requirement import require_internet_for

        net = require_internet_for(root, consumer="r3")
        if not net.get("allowed"):
            doc = {
                "schema_version": 1,
                "updated_at_utc": _utc_now(),
                "ok": False,
                "skipped": True,
                "reason_de": "internet_required",
                "assess": assess,
                "owner": owner,
            }
            if persist:
                atomic_write_json(root / _EVIDENCE_REL, doc)
            return doc
    except Exception as exc:
        steps.append({"step": "internet", "ok": False, "error": str(exc)[:80]})

    ingest_doc: Dict[str, Any] = {}
    try:
        from analytics.r3_browser_data import ingest_prognosis_data_from_internet

        ingest_doc = ingest_prognosis_data_from_internet(
            root, force=bool(force), fast=not bool(force), persist=True
        )
        steps.append(
            {
                "step": "ingest",
                "ok": bool(ingest_doc.get("ok")),
                "price_latest": ingest_doc.get("price_latest"),
            }
        )
    except Exception as exc:
        steps.append({"step": "ingest", "ok": False, "error": str(exc)[:80]})

    quote_doc: Dict[str, Any] = {}
    try:
        from market.live_quote_engine import ensure_live_quotes_fresh

        quote_doc = ensure_live_quotes_fresh(root, force=True, owner=owner)
        fresh = (quote_doc.get("freshness") or {}).get("status")
        steps.append({"step": "live_quotes", "ok": fresh == "FRESH", "status": fresh})
    except Exception as exc:
        steps.append({"step": "live_quotes", "ok": False, "error": str(exc)[:80]})

    live_quotes_ok = any(s.get("step") == "live_quotes" and s.get("ok") for s in steps)
    if live_quotes_ok:
        try:
            from analytics.pilot_portfolio_reevaluation import run_periodic_reevaluation

            reeval_doc = run_periodic_reevaluation(root, force=False)
            steps.append({"step": "reeval", "ok": bool(reeval_doc.get("ok"))})
        except Exception as exc:
            steps.append({"step": "reeval", "ok": False, "error": str(exc)[:80]})

    after = assess_quote_freshness(root)
    ok = bool(ingest_doc.get("ok")) and not after.get("needs_refresh")
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok,
        "skipped": False,
        "owner": owner,
        "assess_before": assess,
        "assess_after": after,
        "steps": steps,
        "price_latest": after.get("price_latest") or ingest_doc.get("price_latest"),
        "quote_status": after.get("quote_status"),
        "headline_de": (
            f"✓ Kurse aktuell — {after.get('price_latest') or '—'}"
            if ok
            else str(after.get("headline_de") or "Kurse noch nicht frisch")
        ),
        "message_de": (
            f"R3 kursaktuell — {after.get('price_latest') or '—'} · {after.get('quote_status')}"
            if ok
            else after.get("headline_de")
        ),
    }
    atomic_write_json(
        root / _STATE_REL,
        {"last_tick_utc": _utc_now(), "updated_at_utc": _utc_now(), "owner": owner},
    )
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def ensure_r3_quotes_fresh(root: Path, *, force: bool = False, owner: str = "ensure") -> Dict[str, Any]:
    return tick_quote_keepalive(root, force=force, owner=owner, persist=True)
