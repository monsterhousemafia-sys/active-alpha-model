#!/usr/bin/env python3
"""Aggregate competition readiness evidence (ops + gates + evolution)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_REL = Path("evidence/competition_readiness_latest.json")


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _price_stale_days(predict: dict) -> int | None:
    price = str(predict.get("price_latest") or "")[:10]
    if not price:
        return None
    try:
        from aa_data_freshness import last_expected_market_date

        ref = last_expected_market_date()
        latest = datetime.strptime(price, "%Y-%m-%d").date()
        return (ref - latest).days
    except Exception:
        return None


def build_competition_readiness(root: Path) -> dict:
    root = Path(root)
    from analytics.live_profile_governance import (
        daily_trading_fee_context,
        h1_backtest_status,
        is_h1_backtest_sealed,
    )
    from analytics.prediction_operations import evaluate_prediction_readiness_for_orders

    canonical = _load(root / "evidence/canonical_model_comparison.json")
    shadow = _load(root / "evidence/competition_shadow_latest.json")
    audit = _load(root / "evidence/learning_cycle_audit_latest.json")
    predict = _load(root / "control/prediction_readiness.json")
    daily_h1 = _load(root / "evidence/daily_alpha_h1_evaluation_latest.json")
    cost_gate = (canonical.get("cost_stress") or {}).get("gate") or {}
    headline = canonical.get("headline") or {}

    gate = evaluate_prediction_readiness_for_orders(root)
    blockers = sorted(set(gate.get("blockers") or []))

    try:
        from aa_config_env import load_aa_env
        from aa_data_freshness import assess_daily_data

        data = assess_daily_data(root, load_aa_env(root))
        price_latest = data.price_latest.isoformat() if data.price_latest else str(predict.get("price_latest") or "")[:10]
        price_current = bool(data.price_current or gate.get("price_current"))
    except Exception:
        price_latest = str(predict.get("price_latest") or "")[:10]
        price_current = bool(gate.get("price_current"))

    if not price_current and "PRICE_NOT_CURRENT" not in blockers:
        blockers.append("PRICE_NOT_CURRENT")
    elif price_current and "PRICE_NOT_CURRENT" in blockers:
        blockers = [b for b in blockers if b != "PRICE_NOT_CURRENT"]

    stale_days = None
    if price_latest:
        try:
            from aa_data_freshness import last_expected_market_date

            ref = last_expected_market_date()
            latest = datetime.strptime(price_latest[:10], "%Y-%m-%d").date()
            stale_days = (ref - latest).days
            if stale_days <= 0:
                stale_days = None
        except Exception:
            stale_days = _price_stale_days({"price_latest": price_latest})

    if not is_h1_backtest_sealed(root):
        try:
            from analytics.h1_seal_policy import is_h1_seal_required

            seal_required = is_h1_seal_required(root)
        except Exception:
            seal_required = True
        if seal_required:
            bt = h1_backtest_status(root)
            if bt.get("status") == "ZOMBIE" and "DAILY_ALPHA_H1_BACKTEST_ZOMBIE" not in blockers:
                blockers.append("DAILY_ALPHA_H1_BACKTEST_ZOMBIE")
            elif bt.get("status") == "FAILED" and "DAILY_ALPHA_H1_BACKTEST_FAILED" not in blockers:
                blockers.append("DAILY_ALPHA_H1_BACKTEST_FAILED")
            elif bt.get("status") != "COMPLETE" and "DAILY_ALPHA_H1_NOT_SEALED" not in blockers:
                blockers.append("DAILY_ALPHA_H1_NOT_SEALED")

    if int((audit.get("live_metrics") or {}).get("n_mature") or 0) < 3:
        blockers.append("LIVE_FILLS_BELOW_SPORT_PLUS")

    ready_for_live_session = bool(gate.get("ok")) and not blockers

    try:
        from analytics.strategic_governance import build_governance_manifest

        governance = build_governance_manifest(root)
    except Exception:
        governance = {}

    comp = shadow.get("comparison") or {}
    fee_ctx = daily_trading_fee_context(root)

    return {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "ready_for_live_session": ready_for_live_session,
        "blockers": sorted(set(blockers)),
        "cost_stress_gate_pass": bool(cost_gate.get("pass")),
        "cost_stress_scope_de": (
            "Research-only: MOM_63_TOP12 vs R0/M1 (+25 bps Turnover-Stress) — "
            "gilt NICHT für live Profil daily_alpha_h1."
        ),
        "cost_stress_detail": cost_gate.get("detail"),
        "live_profile_sealed": is_h1_backtest_sealed(root),
        "h1_backtest": h1_backtest_status(root),
        "daily_trading_fee_context": fee_ctx,
        "aligned_sharpe_leader": headline.get("aligned_intersection_sharpe_leader"),
        "matrix_sharpe_leader": headline.get("matrix_embedded_sharpe_leader"),
        "evolution_stage": (audit.get("stage") or {}).get("stage_id"),
        "live_mature_fills": (audit.get("live_metrics") or {}).get("n_mature"),
        "daily_alpha_h1": daily_h1,
        "shadow_overlap_model_vs_benchmark": (comp.get("model_vs_benchmark") or {}).get("jaccard"),
        "shadow_overlap_model_vs_live": (comp.get("model_vs_live") or {}).get("jaccard"),
        "shadow_informative_only": True,
        "signal_date": predict.get("signal_date") or gate.get("signal_date"),
        "price_latest": price_latest or predict.get("price_latest"),
        "price_current": price_current,
        "price_stale_days": stale_days,
        "strategic_governance": {
            "governance_champion": governance.get("governance_champion"),
            "active_signal_variant": governance.get("active_signal_variant"),
            "effective_orders_profile": governance.get("effective_orders_profile"),
            "coherence_ok": governance.get("coherence_ok"),
            "manifest_ref": "control/strategic_governance.json",
        },
        "prediction_readiness_ok": bool(gate.get("ok")),
        "order_gate_ok": bool(gate.get("ok")),
        "message_de": _format_message(blockers, stale_days, cost_gate.get("pass"), is_h1_backtest_sealed(root)),
    }


def _format_message(blockers: list[str], stale_days: int | None, cost_pass: bool, h1_sealed: bool) -> str:
    if not blockers and h1_sealed:
        return "Wettkampf-bereit: H1 sealed, Order-Gate offen."
    parts = []
    for b in sorted(set(blockers))[:5]:
        if b == "PRICE_NOT_CURRENT" and stale_days is not None:
            parts.append(f"PRICE_NOT_CURRENT ({stale_days}d)")
        elif b == "EXPERIMENTAL_PROFILE_UNSEALED_REAL_MONEY":
            parts.append("Echtgeld blockiert: H1 unsealed (Tages-Fees/turnover)")
        else:
            parts.append(b)
    suffix = ""
    if cost_pass:
        suffix = " | Cost-Stress PASS nur MOM_63 vs R0 (nicht Live-H1)."
    return f"Vorbereitung — Blocker: {', '.join(parts) or '—'}.{suffix}"


def main() -> int:
    import argparse

    from aa_safe_io import atomic_write_json

    parser = argparse.ArgumentParser(description="Competition readiness snapshot")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    doc = build_competition_readiness(Path(args.root))
    atomic_write_json(Path(args.root) / EVIDENCE_REL, doc)
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print(doc.get("message_de", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
