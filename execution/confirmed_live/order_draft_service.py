"""Order draft queue and lifecycle."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json
from execution.confirmed_live.order_preflight_gate import run_preflight


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _draft_dir(root: Path) -> Path:
    d = root / "live_pilot/confirmed_execution/order_drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_draft(
    root: Path,
    *,
    instrument: str,
    side: str,
    max_notional_eur: float,
    limit_price: float,
    t212_id: str,
    quantity: float,
    execution_style: str = "limit",
    order_source: str = "",
    limit_time_validity: str | None = None,
) -> Dict[str, Any]:
    side_u = side.upper()
    is_market = str(execution_style or "limit").strip().lower() == "market"
    if is_market:
        order_type = "MARKET_BUY" if side_u == "BUY" else "MARKET_SELL_COVERED"
    else:
        order_type = "LIMIT_BUY" if side_u == "BUY" else "LIMIT_SELL_COVERED"
    draft = {
        "draft_id": str(uuid.uuid4()),
        "instrument": instrument.upper(),
        "t212_instrument_id": t212_id,
        "side": side_u,
        "order_type": order_type,
        "execution_style": "market" if is_market else "limit",
        "max_notional_eur": round(max_notional_eur, 4),
        "limit_price": limit_price,
        "reference_price_eur": round(float(limit_price), 4) if is_market else None,
        "quantity": quantity,
        "status": "DRAFT_PRECHECK_PENDING",
        "created_at_utc": _utc_now(),
        "expires_at_utc": (datetime.now(timezone.utc) + timedelta(minutes=15)).replace(microsecond=0).isoformat(),
        "strategy_class": "DAILY_OR_MULTI_DAY_MOMENTUM",
        "source": str(order_source or "MANAGED_CORE_LIVE_DRAFT"),
    }
    if limit_time_validity:
        draft["limit_time_validity"] = str(limit_time_validity).upper()
    elif not is_market:
        try:
            from analytics.live_trading_operations import load_policy

            draft["limit_time_validity"] = str(load_policy(root).get("limit_time_validity") or "DAY").upper()
        except Exception:
            draft["limit_time_validity"] = "DAY"
    atomic_write_json(_draft_dir(root) / f"{draft['draft_id']}.json", draft)
    return draft


def refresh_draft_status(root: Path, draft: Dict[str, Any], *, readonly_cash: float | None, account_currency: str | None) -> Dict[str, Any]:
    pf = run_preflight(root, draft, readonly_cash=readonly_cash, account_currency=account_currency)
    if pf.get("passed"):
        draft["status"] = "DRAFT_READY_FOR_REVIEW"
    else:
        draft["status"] = "DRAFT_BLOCKED"
    draft["blockers"] = pf.get("blockers") or []
    draft["updated_at_utc"] = _utc_now()
    atomic_write_json(_draft_dir(root) / f"{draft['draft_id']}.json", draft)
    return draft


def load_drafts(root: Path) -> List[Dict[str, Any]]:
    out = []
    for p in sorted(_draft_dir(root).glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def prune_superseded_drafts_for_instrument(
    root: Path,
    instrument: str,
    *,
    keep_draft_id: str | None = None,
) -> int:
    """Drop older local drafts for one symbol (auto-scale retries must not flood the queue)."""
    sym = str(instrument).upper()
    removed = 0
    for path in list(_draft_dir(root).glob("*.json")):
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            removed += 1
            continue
        if str(draft.get("instrument") or "").upper() != sym:
            continue
        if keep_draft_id and draft.get("draft_id") == keep_draft_id:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def prune_stale_order_drafts(root: Path, *, max_age_minutes: float = 10.0) -> int:
    """
    Remove old local draft files from failed attempts.
    They are not open T212 orders — only UI noise and must not trigger retry storms.
    """
    root = Path(root)
    now = datetime.now(timezone.utc)
    removed = 0
    for path in list(_draft_dir(root).glob("*.json")):
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            removed += 1
            continue
        created = _parse_utc(draft.get("created_at_utc"))
        age_min = ((now - created).total_seconds() / 60.0) if created else 999.0
        status = str(draft.get("status") or "")
        if status == "DRAFT_BLOCKED" and age_min > 2.0:
            path.unlink(missing_ok=True)
            removed += 1
        elif age_min > max_age_minutes:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def load_queue_summary(root: Path) -> Dict[str, Any]:
    prune_stale_order_drafts(root, max_age_minutes=10.0)
    drafts = load_drafts(root)
    return {
        "waiting_review": len([d for d in drafts if d.get("status") == "DRAFT_READY_FOR_REVIEW"]),
        "blocked": len([d for d in drafts if d.get("status") == "DRAFT_BLOCKED"]),
        "drafts": drafts,
    }
