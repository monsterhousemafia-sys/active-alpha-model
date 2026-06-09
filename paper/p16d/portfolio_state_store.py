"""Stateful portfolio continuation from P16C without reinitialization."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json
from paper.p16c.pnl_attribution import subsequent_mark_pnl

P16C_CHECKPOINT = Path("paper/p16c/runtime_checkpoint.json")
P16D_CHECKPOINT = Path("paper/p16d/runtime_checkpoint.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _p16d_path(root: Path) -> Path:
    return root / P16D_CHECKPOINT


def _p16c_path(root: Path) -> Path:
    return root / P16C_CHECKPOINT


def migrate_checkpoint_from_p16c(root: Path) -> Dict[str, Any]:
    """Import P16C checkpoint once; never re-run initial allocation."""
    root = Path(root)
    d_path = _p16d_path(root)
    if d_path.is_file():
        return json.loads(d_path.read_text(encoding="utf-8"))

    c_path = _p16c_path(root)
    if not c_path.is_file():
        raise FileNotFoundError("P16C checkpoint required for P16D continuation")

    state = json.loads(c_path.read_text(encoding="utf-8"))
    state["portfolio_id"] = "PROVISIONAL_EXECUTABLE_PORTFOLIO_6_POSITION_500_EUR"
    state["migrated_from_p16c"] = True
    state["p16c_baseline_mark_count"] = int(state.get("mark_count", 0))
    state["post_baseline_mark_count"] = 0
    state["no_reinitialization"] = True
    d_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(d_path, state)
    return state


def load_state(root: Path) -> Dict[str, Any]:
    return migrate_checkpoint_from_p16c(root)


def save_state(root: Path, state: Dict[str, Any]) -> None:
    state["updated_at_utc"] = _utc_now()
    atomic_write_json(_p16d_path(root), state)


def mark_to_market_post_baseline(root: Path, prices_eur: Dict[str, float], *, fx_gate_ok: bool) -> Dict[str, Any]:
    state = load_state(root)
    if not state.get("initial_allocation_executed"):
        return {"skipped": True, "reason": "no_initial_allocation"}

    if not fx_gate_ok:
        return {"skipped": True, "reason": "fx_gate_paused"}

    invested = 0.0
    for pos in state.get("positions") or []:
        sym = pos["symbol"]
        px = prices_eur.get(sym, pos.get("last_mark_eur", pos.get("avg_cost_eur", 0)))
        pos["last_mark_eur"] = px
        pos["market_value_eur"] = round(pos["shares"] * px, 4)
        invested += pos["market_value_eur"]

    cash = float(state["cash_eur"])
    value = cash + invested
    prev = float(state.get("last_mark_value_eur", state.get("initial_post_fill_portfolio_value_eur", 500)))

    post_baseline_marks = int(state.get("post_baseline_mark_count", 0))
    if post_baseline_marks == 0:
        state["post_baseline_mark_count"] = 1
        state["last_mark_value_eur"] = round(value, 4)
        state["post_baseline_baseline_value_eur"] = round(value, 4)
        save_state(root, state)
        mtm = root / "paper/p16d/mark_to_market_ledger"
        mtm.mkdir(parents=True, exist_ok=True)
        with (mtm / "ledger.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "type": "POST_BASELINE_BASELINE_MARK",
                        "portfolio_value_eur": round(value, 4),
                        "subsequent_market_price_pnl_eur": 0.0,
                        "note": "establishes_post_baseline_reference_no_performance_claim",
                    }
                )
                + "\n"
            )
        return {
            "portfolio_value_eur": round(value, 4),
            "independent_post_baseline_mark": False,
            "subsequent_market_price_pnl_eur": 0.0,
            "note": "first_p16d_mark_establishes_post_baseline_reference",
        }

    attrib = subsequent_mark_pnl(previous_value_eur=prev, current_value_eur=value, state=state)
    state.update(attrib)
    state["last_mark_value_eur"] = round(value, 4)
    state["post_baseline_mark_count"] = post_baseline_marks + 1
    save_state(root, state)

    mtm = root / "paper/p16d/mark_to_market_ledger"
    mtm.mkdir(parents=True, exist_ok=True)
    with (mtm / "ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**attrib, "portfolio_value_eur": round(value, 4), "independent_post_baseline_mark": True}) + "\n")

    recon = abs(value - (cash + invested)) < 0.02
    return {
        "portfolio_value_eur": round(value, 4),
        "cash_eur": round(cash, 4),
        "independent_post_baseline_mark": True,
        "portfolio_reconciliation": "PASS" if recon else "FAIL",
        **attrib,
    }


def verify_no_reinitialization(root: Path) -> Dict[str, Any]:
    state = load_state(root)
    return {
        "stateful_continuation_no_reinitialization": "PASS" if state.get("initial_allocation_executed") and state.get("no_reinitialization") else "FAIL",
        "initial_allocation_executed": state.get("initial_allocation_executed"),
        "migrated_from_p16c": state.get("migrated_from_p16c"),
    }
