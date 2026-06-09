"""T212-Sync + Lernen — Active Alpha liest Broker-Daten in die Observation-Ledger."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/t212_learning_sync_latest.json")
_ANCHOR_REL = Path("control/t212_learning_anchor.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _broker_dict(status: Any) -> Dict[str, Any]:
    if hasattr(status, "to_dict"):
        return dict(status.to_dict())
    return dict(status or {})


def sync_t212_with_learning(root: Path, *, force: bool = True, capture_learning: bool = True) -> Dict[str, Any]:
    """
    1) T212 readonly sync (force)
    2) R3-Bond aktualisieren
    3) Broker-Snapshot → Learning-Ledger (täglich + bei Positionswechsel/Liquidation)
    4) Live-Fill-Outcomes (observe-only)
    """
    root = Path(root)
    steps: list[Dict[str, Any]] = []
    broker: Dict[str, Any] = {}

    try:
        from integrations.trading212.t212_readonly_connection_service import sync_readonly_account
        from integrations.trading212.t212_sync_throttle import should_sync_now
        from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

        cached = load_cached_broker_status(root)
        cached_sync = cached.last_successful_sync_utc if cached else None
        allow, throttle_de = should_sync_now(root, force=force, last_successful_sync_utc=cached_sync)
        if allow or force:
            st = sync_readonly_account(root, force=force)
            broker = _broker_dict(st)
            api_ok = bool(broker.get("last_successful_sync_utc")) and str(broker.get("status") or "") not in {
                "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA",
                "CONNECTION_FAILED_RETRY_AVAILABLE",
            }
            steps.append(
                {
                    "step": "t212_api",
                    "ok": api_ok,
                    "status": broker.get("status"),
                    "positions_count": broker.get("positions_count"),
                    "cash_eur": broker.get("cash_eur"),
                    "sync_utc": broker.get("last_successful_sync_utc"),
                    "last_error": (broker.get("last_error") or "")[:120] or None,
                }
            )
        else:
            broker = _broker_dict(cached) if cached else {}
            steps.append({"step": "t212_api", "ok": bool(broker), "throttled": True, "detail_de": throttle_de})
    except Exception as exc:
        steps.append({"step": "t212_api", "ok": False, "error": str(exc)[:120]})
        return _finish(root, steps, broker, ok=False)

    try:
        from analytics.r3_t212_api_bond import build_r3_t212_api_bond

        bond = build_r3_t212_api_bond(root, persist=True)
        steps.append({"step": "r3_bond", "ok": bool(bond.get("connected")), "confirmation_de": bond.get("confirmation_de")})
        if not broker.get("last_successful_sync_utc") and bond.get("last_sync_utc"):
            broker = {
                **broker,
                "positions_count": bond.get("positions_count"),
                "cash_eur": bond.get("cash_eur"),
                "cash_breakdown": bond.get("cash_breakdown") or {},
                "positions": bond.get("positions") or [],
                "last_successful_sync_utc": bond.get("last_sync_utc"),
                "credentials_configured": bond.get("credentials_configured"),
            }
    except Exception as exc:
        steps.append({"step": "r3_bond", "ok": False, "error": str(exc)[:120]})

    if capture_learning and broker.get("credentials_configured"):
        try:
            from market.learning_pipeline import append_broker_event_snapshot, run_learning_capture_cycle

            anchor_path = root / _ANCHOR_REL
            prev_n = 0
            if anchor_path.is_file():
                try:
                    import json

                    prev_n = int(json.loads(anchor_path.read_text()).get("positions_count") or 0)
                except Exception:
                    prev_n = 0
            cur_n = int(broker.get("positions_count") or 0)
            event = None
            if cur_n == 0 and prev_n > 0:
                event = "liquidation_complete"
            elif cur_n != prev_n:
                event = "position_change"

            learn = run_learning_capture_cycle(root, broker=broker, cash=broker.get("cash_breakdown") or {})
            if event:
                learn["broker_event"] = append_broker_event_snapshot(
                    root,
                    broker=broker,
                    event=event,
                    previous_positions_count=prev_n,
                )
            atomic_write_json(
                anchor_path,
                {
                    "schema_version": 1,
                    "updated_at_utc": _utc_now(),
                    "positions_count": cur_n,
                    "cash_eur": broker.get("cash_eur"),
                    "last_sync_utc": broker.get("last_successful_sync_utc"),
                    "last_event": event,
                },
            )
            readiness = learn.get("readiness") or {}
            steps.append(
                {
                    "step": "learning_capture",
                    "ok": bool(readiness.get("learning_healthy", True)),
                    "event": event,
                    "broker_daily_rows": readiness.get("broker_daily_snapshots"),
                }
            )
        except Exception as exc:
            steps.append({"step": "learning_capture", "ok": False, "error": str(exc)[:120]})

        try:
            from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

            outcomes = sync_live_execution_outcomes(root)
            steps.append({"step": "live_outcomes", "ok": bool(outcomes.get("ok", True)), "message_de": outcomes.get("message_de")})
        except Exception as exc:
            steps.append({"step": "live_outcomes", "ok": False, "error": str(exc)[:120]})

    trust: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust

        trust = assess_t212_trust(broker, root=root)
    except Exception:
        trust = {"trusted": False, "message_de": "T212 Trust Gate Fehler"}

    ok = bool(trust.get("trusted"))
    auth_stale = not ok
    return _finish(root, steps, broker, ok=ok, auth_stale=auth_stale, trust=trust)


def t212_learning_status(root: Path) -> Dict[str, Any]:
    """Letzter Sync+Lernen-Stand (Evidence + Anchor + Manifest)."""
    root = Path(root)
    import json

    out: Dict[str, Any] = {"schema_version": 1, "updated_at_utc": _utc_now()}
    ev_path = root / _EVIDENCE_REL
    if ev_path.is_file():
        try:
            out["last_sync"] = json.loads(ev_path.read_text(encoding="utf-8"))
        except Exception:
            out["last_sync"] = {}
    anchor_path = root / _ANCHOR_REL
    if anchor_path.is_file():
        try:
            out["anchor"] = json.loads(anchor_path.read_text(encoding="utf-8"))
        except Exception:
            out["anchor"] = {}
    try:
        from market.learning_pipeline import learning_readiness_report

        out["learning"] = learning_readiness_report(root)
    except Exception as exc:
        out["learning"] = {"error": str(exc)[:80]}
    return out


def _finish(
    root: Path,
    steps: list,
    broker: Dict[str, Any],
    *,
    ok: bool,
    auth_stale: bool = False,
    trust: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sync_at = str(broker.get("last_successful_sync_utc") or "")[:19].replace("T", " ")
    trust = trust or {}
    headline = (
        f"T212+Lernen OK — {int(broker.get('positions_count') or 0)} Positionen, "
        f"{float(broker.get('cash_eur') or 0):.0f} €"
        if ok
        else str(trust.get("message_de") or "T212+Lernen — Sync oder Bond prüfen (siehe steps)")
    )
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok,
        "stale_cache": auth_stale,
        "t212_trusted": bool(trust.get("trusted")),
        "t212_trust_reason": trust.get("reason_code"),
        "positions_count": broker.get("positions_count"),
        "cash_eur": broker.get("cash_eur"),
        "last_sync_utc": broker.get("last_successful_sync_utc"),
        "steps": steps,
        "headline_de": headline,
        "learning_ref": "market_data/live_learning/",
        "policy_ref": "control/learning_collection_policy.json",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
