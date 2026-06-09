"""Institutional (Wall Street) performance audit + daily growth loop health."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

AUDIT_LATEST = Path("evidence/wallstreet_audit_latest.json")
AUDIT_HISTORY = Path("evidence/wallstreet_audit_history.jsonl")

# Variants that matter for live + governance narrative
_CORE_VARIANTS = (
    "R3_w075_q065_noexit",
    "R0_LEGACY_ENSEMBLE",
    "MOM_63_TOP12",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
    "DAILY_ALPHA_H1",
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


def _variant_metrics_from_canonical(doc: Dict[str, Any], variant_id: str) -> Dict[str, Any]:
    """Extract metrics for a variant from canonical comparison."""
    for row in doc.get("variants") or []:
        if str(row.get("variant_id") or "") == variant_id and row.get("metrics"):
            m = dict(row["metrics"])
            return {
                "variant_id": variant_id,
                "scenario": str(row.get("metrics_mode") or "aligned_recomputed"),
                **m,
            }
    scenarios = (doc.get("cost_stress") or {}).get("scenarios") or {}
    plus = scenarios.get("PLUS_25_BPS") or scenarios.get("+25_BPS") or []
    for row in plus:
        if str(row.get("variant_id") or "") == variant_id:
            m = dict(row.get("metrics") or {})
            return {
                "variant_id": variant_id,
                "scenario": "PLUS_25_BPS",
                "sharpe_0rf": m.get("sharpe_0rf"),
                "cagr": m.get("cagr"),
                "annual_vol": m.get("annual_vol"),
                "max_drawdown": m.get("max_drawdown"),
                "daily_hit_rate": m.get("daily_hit_rate"),
                "total_return": m.get("total_return"),
                "n_days": m.get("n_days"),
            }
    # fallback: BASELINE
    base = scenarios.get("BASELINE") or []
    for row in base:
        if str(row.get("variant_id") or "") == variant_id:
            m = dict(row.get("metrics") or {})
            return {
                "variant_id": variant_id,
                "scenario": "BASELINE",
                "sharpe_0rf": m.get("sharpe_0rf"),
                "cagr": m.get("cagr"),
                "annual_vol": m.get("annual_vol"),
                "max_drawdown": m.get("max_drawdown"),
                "daily_hit_rate": m.get("daily_hit_rate"),
                "total_return": m.get("total_return"),
                "n_days": m.get("n_days"),
            }
    return {"variant_id": variant_id, "missing": True}


def _wallstreet_scorecard(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Map raw metrics to institutional checklist fields."""
    sh = metrics.get("sharpe_0rf")
    mdd = metrics.get("max_drawdown")
    cagr = metrics.get("cagr")
    vol = metrics.get("annual_vol")
    hit = metrics.get("daily_hit_rate")
    calmar = None
    if cagr is not None and mdd is not None and float(mdd) < 0:
        calmar = float(cagr) / abs(float(mdd))
    return {
        "sharpe_0rf": sh,
        "cagr": cagr,
        "annual_vol": vol,
        "max_drawdown": mdd,
        "calmar_ratio": calmar,
        "daily_hit_rate": hit,
        "n_days": metrics.get("n_days"),
    }


def _assess_daily_growth_loop(root: Path) -> Dict[str, Any]:
    root = Path(root)
    policy = _load_json(root / "control/learning_collection_policy.json")
    pred = _load_json(root / "control/prediction_readiness.json")
    learn_eod = _load_json(root / "evidence/learning_eod_catchup_latest.json")
    learn_audit = _load_json(root / "evidence/learning_cycle_audit_latest.json")
    comp = _load_json(root / "evidence/competition_readiness_latest.json")
    manifest = _load_json(root / "market_data/live_learning/learning_manifest.json")

    signal_date = str(pred.get("signal_date") or comp.get("signal_date") or "")[:10]
    price_latest = str(pred.get("price_latest") or comp.get("price_latest") or "")[:10]
    today = datetime.now(timezone.utc).date().isoformat()

    components = [
        {
            "id": "eod_signal_refresh",
            "ok": bool(signal_date) and signal_date >= price_latest,
            "detail_de": f"Signal {signal_date or '—'} · Preise {price_latest or '—'}",
            "required_daily": True,
        },
        {
            "id": "outcome_feedback_ledger",
            "ok": int((learn_audit.get("backtest_metrics") or {}).get("n_mature") or 0) > 0,
            "detail_de": f"Backtest reif: {(learn_audit.get('backtest_metrics') or {}).get('n_mature', 0)}",
            "required_daily": True,
        },
        {
            "id": "live_fill_feedback",
            "ok": int((learn_audit.get("live_metrics") or {}).get("n_mature") or 0) >= 3,
            "detail_de": f"Live reif: {(learn_audit.get('live_metrics') or {}).get('n_mature', 0)} (Ziel ≥3)",
            "required_daily": True,
        },
        {
            "id": "eod_close_capture",
            "ok": bool(learn_eod.get("eod", {}).get("ok") or manifest.get("last_eod_date")),
            "detail_de": f"Letztes EOD: {learn_eod.get('eod', {}).get('date') or manifest.get('last_eod_date') or '—'}",
            "required_daily": True,
        },
        {
            "id": "intraday_learning_capture",
            "ok": bool(policy.get("intraday_quote_capture_enabled")),
            "detail_de": f"Intraday rows: {manifest.get('intraday_rows', 0)}",
            "required_daily": True,
        },
        {
            "id": "weekly_learning_audit",
            "ok": bool(learn_audit.get("generated_at_utc")),
            "detail_de": learn_audit.get("message_de", "—")[:120],
            "required_daily": False,
        },
        {
            "id": "h1_backtest_sealed",
            "ok": bool(comp.get("live_profile_sealed")) or str(comp.get("h1_backtest", {}).get("status")) == "PASS",
            "detail_de": str(comp.get("h1_backtest", {}).get("detail_de") or comp.get("message_de") or "")[:160],
            "required_daily": False,
        },
        {
            "id": "auto_model_retrain",
            "ok": bool(policy.get("auto_model_training_enabled")),
            "detail_de": "Aus (Governance) — Offline-Challenger nach Seal",
            "required_daily": False,
        },
    ]
    daily_ok = all(c["ok"] for c in components if c.get("required_daily"))
    improving = bool(learn_audit.get("learning_detected"))
    return {
        "daily_loop_ok": daily_ok,
        "learning_detected": improving,
        "auto_retrain_enabled": bool(policy.get("auto_model_training_enabled")),
        "observation_only": not policy.get("auto_model_training_enabled"),
        "components": components,
        "evolution_stage": str(comp.get("evolution_stage") or learn_audit.get("stage", {}).get("stage_id") or "sportwagen"),
        "next_evolution_stage": learn_audit.get("next_stage_id"),
    }


def _h1_objective_status(root: Path) -> Dict[str, Any]:
    ev = _load_json(root / "evidence/daily_alpha_h1_evaluation_latest.json")
    if ev:
        return ev
    comp = _load_json(root / "evidence/competition_readiness_latest.json")
    h1 = comp.get("h1_backtest") or {}
    return {
        "ok": False,
        "pass_full_seal": False,
        "reason": h1.get("status") or "NOT_RUN",
        "message_de": h1.get("detail_de") or "DAILY_ALPHA_H1 Backtest nicht sealed",
    }


def run_wallstreet_audit(root: Path) -> Dict[str, Any]:
    root = Path(root)
    canonical = _load_json(root / "evidence/canonical_model_comparison.json")
    cost_stress = _load_json(root / "control/evidence/cost_stress_status.json")
    learn_audit = _load_json(root / "evidence/learning_cycle_audit_latest.json")
    comp = _load_json(root / "evidence/competition_readiness_latest.json")
    objective = _load_json(root / "control/r0_migration/alpha_objective.json")

    prev = _load_json(root / AUDIT_LATEST)
    scorecards: Dict[str, Any] = {}
    for vid in _CORE_VARIANTS:
        raw = _variant_metrics_from_canonical(canonical, vid)
        scorecards[vid] = _wallstreet_scorecard(raw)

    headline = canonical.get("headline") or {}
    gate = (cost_stress.get("COST_STRESS_GATE") or canonical.get("cost_stress", {}).get("gate") or {})
    bt = learn_audit.get("backtest_metrics") or {}
    live = learn_audit.get("live_metrics") or {}

    champion_live = "R3_w075_q065_noexit"
    governance = "R0_LEGACY_ENSEMBLE"
    bench = "MOM_63_TOP12"

    ch = scorecards.get(champion_live) or {}
    gov = scorecards.get(governance) or {}
    bm = scorecards.get(bench) or {}

    blockers: List[str] = []
    if not gate.get("pass"):
        blockers.append("COST_STRESS_GATE_FAIL")
    h1 = _h1_objective_status(root)
    seal_required = True
    try:
        from analytics.h1_seal_policy import is_h1_seal_required

        seal_required = is_h1_seal_required(root)
    except Exception:
        pass
    if seal_required and not h1.get("pass_full_seal"):
        blockers.extend(["DAILY_ALPHA_H1_NOT_SEALED", str(h1.get("reason") or "H1_FAIL")])
    if int(live.get("n_mature") or 0) < 3:
        blockers.append("LIVE_PREDICTION_FEEDBACK_INSUFFICIENT")
    if not comp.get("ready_for_live_session"):
        blockers.append("COMPETITION_NOT_READY_FOR_LIVE")
    if comp.get("blockers"):
        for b in comp.get("blockers") or []:
            if b not in blockers:
                blockers.append(str(b))

    growth = _assess_daily_growth_loop(root)
    if not growth.get("daily_loop_ok"):
        blockers.append("DAILY_GROWTH_LOOP_INCOMPLETE")

    # Institutional pass: champion beats benchmark on Sharpe+MDD after cost stress OR H1 sealed
    beats_bench_sharpe = False
    mdd_ok = False
    try:
        if ch.get("sharpe_0rf") is not None and bm.get("sharpe_0rf") is not None:
            beats_bench_sharpe = float(ch["sharpe_0rf"]) > float(bm["sharpe_0rf"])
        if ch.get("max_drawdown") is not None and bm.get("max_drawdown") is not None:
            mdd_ok = float(ch["max_drawdown"]) >= float(bm["max_drawdown"])
    except (TypeError, ValueError):
        pass

    delta: Dict[str, Any] = {}
    if prev:
        prev_bt = prev.get("prediction_quality", {}).get("backtest") or {}
        for key in ("ic_pearson", "signed_hit_rate", "mae"):
            if key in bt and key in prev_bt:
                try:
                    delta[f"bt_{key}"] = float(bt[key]) - float(prev_bt[key])
                except (TypeError, ValueError):
                    pass

    recommendations = [
        "Täglich 22:15 CET: EOD-Signal (tools/run_tomorrow_prediction.py) — Pflicht.",
        "Nach US-Close: python3 tools/sync_live_execution_outcomes.py — Live-Fills in Ledger.",
        "Wöchentlich: python3 tools/run_learning_cycle_audit.py — IC/Hit-Rate Delta.",
        "DAILY_ALPHA_H1 Backtest sealed laufen lassen (vs mom_1_top12 netto +25bps).",
        "Erst bei ≥3 reifen Live-Outcomes: Sport-Plus-Stufe — dann Slippage kalibrieren.",
        "Kein Auto-Retrain live — Challenger nur offline nach H1-Seal (Governance).",
    ]

    verdict = "INSTITUTIONAL_READY"
    if blockers:
        verdict = "NOT_INSTITUTIONAL_READY"
    elif not beats_bench_sharpe or not mdd_ok:
        verdict = "RESEARCH_ONLY_CHAMPION_BELOW_BENCHMARK"

    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "verdict": verdict,
        "verdict_de": {
            "INSTITUTIONAL_READY": "Wall-Street-Kriterien erfüllt — Live mit Governance.",
            "NOT_INSTITUTIONAL_READY": "Blocker offen — kein institutionelles Go-Live.",
            "RESEARCH_ONLY_CHAMPION_BELOW_BENCHMARK": "Champion unter Benchmark — Forschung, nicht Produktion.",
        }.get(verdict, verdict),
        "objective": {
            "horizon": (objective.get("objective") or {}).get("horizon"),
            "benchmark": (objective.get("objective") or {}).get("benchmark"),
            "success_criterion": (objective.get("objective") or {}).get("success_criterion"),
        },
        "performance": {
            "ranking_frame": headline.get("primary_ranking_frame"),
            "sharpe_leader_aligned": headline.get("aligned_intersection_sharpe_leader"),
            "sharpe_leader_matrix": headline.get("matrix_embedded_sharpe_leader"),
            "champion_is_sharpe_leader": headline.get("champion_is_sharpe_leader"),
            "cost_stress_gate_pass": bool(gate.get("pass")),
            "cost_stress_detail": gate.get("detail"),
            "scorecards_plus_25bps": scorecards,
            "champion_vs_benchmark": {
                "champion": champion_live,
                "benchmark": bench,
                "beats_benchmark_sharpe": beats_bench_sharpe,
                "max_drawdown_not_worse": mdd_ok,
                "champion_sharpe": ch.get("sharpe_0rf"),
                "benchmark_sharpe": bm.get("sharpe_0rf"),
                "champion_mdd": ch.get("max_drawdown"),
                "benchmark_mdd": bm.get("max_drawdown"),
            },
            "governance_champion": {
                "variant": governance,
                "scorecard": gov,
            },
        },
        "prediction_quality": {
            "backtest": bt,
            "live": live,
            "delta_vs_previous_audit": delta,
            "ic_institutional_floor": 0.02,
            "hit_rate_institutional_floor": 0.52,
            "backtest_ic_ok": float(bt.get("ic_pearson") or 0) >= 0.02,
            "backtest_hit_ok": float(bt.get("signed_hit_rate") or 0) >= 0.52,
        },
        "daily_alpha_h1": h1,
        "daily_growth_loop": growth,
        "competition_readiness": {
            "ready_for_live_session": comp.get("ready_for_live_session"),
            "signal_date": comp.get("signal_date"),
            "blockers": comp.get("blockers") or [],
        },
        "blockers": blockers,
        "recommendations_de": recommendations,
        "message_de": (
            f"Wall-Street-Audit: {verdict}. "
            f"Champion Sharpe {ch.get('sharpe_0rf', '—')} vs Benchmark {bm.get('sharpe_0rf', '—')} (+25bps). "
            f"Live reif {live.get('n_mature', 0)} · IC {bt.get('ic_pearson', '—')} · "
            f"Tages-Loop {'OK' if growth.get('daily_loop_ok') else 'LÜCKE'}."
        ),
    }

    atomic_write_json(root / AUDIT_LATEST, report)
    hist = root / AUDIT_HISTORY
    hist.parent.mkdir(parents=True, exist_ok=True)
    with hist.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
    return report
