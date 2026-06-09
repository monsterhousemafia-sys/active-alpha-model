"""Public-grade daily learning — capture, measure, trend, transparent evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

REPORT_LATEST = Path("evidence/public_learning_report_latest.json")
REPORT_HISTORY = Path("evidence/public_learning_report_history.jsonl")
PRINCIPLES_REL = Path("control/public_learning_principles.json")


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


def load_principles(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / PRINCIPLES_REL)


def _read_history_tail(path: Path, *, limit: int = 14) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def _metric_trend(history: List[Dict[str, Any]], key: str, *, nested: str = "live_metrics") -> Dict[str, Any]:
    vals: List[float] = []
    for row in history:
        block = row.get(nested) or row.get("metrics", {}).get(nested) or {}
        if nested == "backtest_metrics":
            block = row.get("backtest_metrics") or row.get("metrics", {}).get("backtest") or {}
        if key in block and block[key] is not None:
            try:
                vals.append(float(block[key]))
            except (TypeError, ValueError):
                pass
    if len(vals) < 2:
        return {"direction": "insufficient_data", "delta": None, "samples": len(vals)}
    delta = vals[-1] - vals[0]
    direction = "flat"
    if delta > 0.005:
        direction = "improving"
    elif delta < -0.005:
        direction = "declining"
    return {"direction": direction, "delta": round(delta, 6), "samples": len(vals), "latest": vals[-1]}


def _governance_ok(root: Path) -> Dict[str, Any]:
    policy = _load_json(root / "control/learning_collection_policy.json")
    kernel = _load_json(root / "control/AI_KERNEL.json")
    checks = []
    for key in (
        "auto_model_training_enabled",
        "auto_champion_update_enabled",
        "auto_execute_real_money_enabled",
    ):
        val = policy.get(key)
        if val is None and key == "auto_execute_real_money_enabled":
            val = (kernel.get("safety") or {}).get("auto_execute_real_money")
        ok = not bool(val)
        checks.append({"id": key, "ok": ok, "value": val})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def compute_quality_score(
    *,
    capture: Dict[str, Any],
    backtest: Dict[str, Any],
    live: Dict[str, Any],
    governance: Dict[str, Any],
    principles: Dict[str, Any],
    trends: Dict[str, Any],
) -> Dict[str, Any]:
    floors = principles.get("quality_floors") or {}
    components: List[Dict[str, Any]] = []

    cap_ok = bool(capture.get("learning_healthy") or capture.get("learning_collection_active"))
    cap_pts = 25 if cap_ok else (12 if capture.get("intraday_observations") else 0)
    components.append({"id": "data_capture", "points": cap_pts, "max": 25, "ok": cap_ok})

    ic = float(backtest.get("ic_pearson") or 0)
    hit = float(backtest.get("signed_hit_rate") or 0)
    ic_floor = float(floors.get("ic_pearson") or 0.02)
    hit_floor = float(floors.get("signed_hit_rate") or 0.52)
    pred_pts = 0
    if ic >= ic_floor:
        pred_pts += 12
    elif ic >= ic_floor * 0.75:
        pred_pts += 6
    if hit >= hit_floor:
        pred_pts += 13
    elif hit >= 0.50:
        pred_pts += 7
    components.append(
        {
            "id": "prediction_feedback",
            "points": pred_pts,
            "max": 25,
            "ic_pearson": ic,
            "signed_hit_rate": hit,
        }
    )

    live_n = int(live.get("n_mature") or 0)
    live_min = int(floors.get("min_live_mature_for_calibration") or 3)
    live_pts = 0
    if live_n >= live_min:
        live_pts = 25
    elif live_n > 0:
        live_pts = 8 + min(12, live_n * 4)
    if (trends.get("live_signed_hit_rate") or {}).get("direction") == "improving":
        live_pts = min(25, live_pts + 3)
    components.append({"id": "live_learning", "points": live_pts, "max": 25, "n_mature": live_n})

    gov_pts = 25 if governance.get("ok") else 0
    components.append({"id": "governance_safety", "points": gov_pts, "max": 25, "ok": governance.get("ok")})

    total = sum(int(c["points"]) for c in components)
    grade = "A" if total >= 85 else "B" if total >= 70 else "C" if total >= 55 else "D" if total >= 40 else "F"
    return {
        "total": total,
        "max": 100,
        "grade": grade,
        "components": components,
        "headline_de": (
            f"Lernqualität {total}/100 (Note {grade}) — "
            f"IC {ic:.4f}, Hit {hit:.1%}, Live reif {live_n}."
        ),
    }


def run_capture_only(
    root: Path,
    *,
    live_snapshot: Optional[Dict[str, Any]] = None,
    broker: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from market.learning_pipeline import run_learning_capture_cycle

    return run_learning_capture_cycle(
        root,
        live_snapshot=live_snapshot,
        broker=broker,
        cash={},
        force_eod=False,
    )


def run_daily_learning(
    root: Path,
    *,
    live_snapshot: Optional[Dict[str, Any]] = None,
    broker: Optional[Dict[str, Any]] = None,
    sync_outcomes: bool = True,
    run_audit: bool = True,
) -> Dict[str, Any]:
    """Full public learning day — capture, outcomes, audit, quality report."""
    root = Path(root)
    principles = load_principles(root)
    steps: List[Dict[str, Any]] = []

    capture = run_capture_only(root, live_snapshot=live_snapshot, broker=broker)
    steps.append({"step": "capture", "ok": capture.get("readiness", {}).get("learning_healthy", True)})

    outcome_sync: Dict[str, Any] = {"skipped": True}
    if sync_outcomes:
        try:
            from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

            outcome_sync = sync_live_execution_outcomes(root, refresh_history=False)
            steps.append({"step": "outcome_sync", "ok": bool(outcome_sync.get("ok"))})
        except Exception as exc:
            outcome_sync = {"ok": False, "error": str(exc)[:200]}
            steps.append({"step": "outcome_sync", "ok": False})
    else:
        steps.append({"step": "outcome_sync", "ok": True, "skipped": True})

    audit: Dict[str, Any] = {}
    if run_audit:
        try:
            from analytics.learning_cycle_audit import run_learning_cycle_audit

            audit = run_learning_cycle_audit(root)
            steps.append({"step": "learning_audit", "ok": bool(audit.get("ok"))})
        except Exception as exc:
            audit = _load_json(root / "evidence/learning_cycle_audit_latest.json")
            audit["audit_error"] = str(exc)[:200]
            steps.append({"step": "learning_audit", "ok": False, "fallback": True})
    else:
        audit = _load_json(root / "evidence/learning_cycle_audit_latest.json")

    evolution_cycle: Dict[str, Any] = {}
    try:
        from analytics.evolution_stage_runner import run_evolution_cycle

        evolution_cycle = run_evolution_cycle(
            root,
            audit=audit if audit else None,
            apply_improvements=True,
            skip_passive={"outcome_sync", "learning_capture"},
        )
        steps.append(
            {
                "step": "evolution_cycle",
                "ok": bool(evolution_cycle.get("ok")),
                "stage": (evolution_cycle.get("stage") or {}).get("stage_id"),
            }
        )
    except Exception as exc:
        evolution_cycle = {"ok": False, "error": str(exc)[:200]}
        steps.append({"step": "evolution_cycle", "ok": False})

    bt = audit.get("backtest_metrics") or {}
    live = audit.get("live_metrics") or {}
    capture_ready = capture.get("readiness") or {}

    hist = _read_history_tail(root / "evidence/learning_cycle_audit_history.jsonl")
    trends = {
        "ic_pearson": _metric_trend(hist, "ic_pearson", nested="backtest_metrics"),
        "signed_hit_rate": _metric_trend(hist, "signed_hit_rate", nested="backtest_metrics"),
        "live_n_mature": _metric_trend(hist, "n_mature", nested="live_metrics"),
    }

    governance = _governance_ok(root)
    quality = compute_quality_score(
        capture=capture_ready,
        backtest=bt,
        live=live,
        governance=governance,
        principles=principles,
        trends=trends,
    )

    stage = audit.get("stage") or {}
    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "mission_de": principles.get("mission_de", ""),
        "principles": principles.get("principles") or [],
        "quality_score": quality,
        "evolution": {
            "stage_id": stage.get("stage_id"),
            "stage_label_de": stage.get("stage_label_de"),
            "stage_order": stage.get("stage_order"),
            "auto_actions_allowed": stage.get("auto_actions_allowed") or [],
            "next_stage_id": audit.get("next_stage_id"),
            "learning_detected": audit.get("learning_detected"),
            "progress": evolution_cycle.get("progress") or {},
            "auto_apply": evolution_cycle.get("auto_apply") or {},
            "passive_actions": evolution_cycle.get("passive_actions") or [],
            "governance": evolution_cycle.get("governance") or {},
        },
        "metrics": {
            "backtest": bt,
            "live": live,
            "delta_vs_previous": audit.get("delta_vs_previous") or {},
            "trends": trends,
        },
        "capture": capture_ready,
        "outcome_sync": outcome_sync,
        "daily_cycle": {"steps": steps, "all_ok": all(s.get("ok") for s in steps)},
        "governance": governance,
        "transparency": {
            "ledger_intraday": "market_data/live_learning/intraday_quotes.jsonl",
            "ledger_eod": "market_data/live_learning/eod_closes.jsonl",
            "ledger_broker": "market_data/live_learning/broker_daily_snapshots.jsonl",
            "audit_history": str(REPORT_HISTORY),
            "learning_audit_history": "evidence/learning_cycle_audit_history.jsonl",
            "wallstreet_audit": "evidence/wallstreet_audit_latest.json",
        },
        "public_disclaimer_de": (
            "Forschungs- und Lernsystem — keine Anlageberatung. "
            "Metriken beziehen sich auf historische Backtests und beobachtete Live-Daten. "
            "Keine Garantie für zukünftige Rendite."
        ),
        "next_steps_de": _next_steps(quality, live, stage),
        "message_de": quality.get("headline_de", ""),
    }

    atomic_write_json(root / REPORT_LATEST, report)
    hist_path = root / REPORT_HISTORY
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    with hist_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
    return report


def _next_steps(quality: Dict[str, Any], live: Dict[str, Any], stage: Dict[str, Any]) -> List[str]:
    steps: List[str] = []
    comps = {c["id"]: c for c in quality.get("components") or []}
    if int((comps.get("live_learning") or {}).get("n_mature") or live.get("n_mature") or 0) < 3:
        steps.append("Live-Orders mit GUI bestätigen — ab 3 reifen Fills beginnt echte Kalibrierung.")
    if int((comps.get("prediction_feedback") or {}).get("points") or 0) < 20:
        steps.append("Offline H1-Backtest sealed — Challenger nur nach PASS vs mom_1_top12.")
    if int((comps.get("data_capture") or {}).get("points") or 0) < 20:
        steps.append("Täglich EOD-Capture: python3 tools/run_learning_eod_catchup.py")
    if stage.get("next_stage_id"):
        steps.append(f"Evolution-Ziel: {stage.get('next_stage_id')} — Kriterien in control/evolution_track.json")
    steps.append("Täglich: python3 tools/ai_kernel.py learn")
    return steps[:5]


def learning_summary_for_dashboard(report: Dict[str, Any]) -> Dict[str, Any]:
    """Compact block for Live-Trading UI."""
    q = report.get("quality_score") or {}
    ev = report.get("evolution") or {}
    m = report.get("metrics") or {}
    bt = m.get("backtest") or {}
    live = m.get("live") or {}
    progress = ev.get("progress") or {}
    auto = ev.get("auto_apply") or {}
    return {
        "grade": q.get("grade"),
        "score": q.get("total"),
        "headline_de": report.get("message_de") or q.get("headline_de"),
        "stage_de": ev.get("stage_label_de") or "Sportwagen",
        "stage_id": ev.get("stage_id") or "sportwagen",
        "next_stage_id": ev.get("next_stage_id") or progress.get("next_stage_id"),
        "stage_gaps_de": progress.get("gaps_de") or [],
        "stage_progress": progress,
        "auto_applied_count": len(auto.get("applied") or []),
        "ic_pearson": bt.get("ic_pearson"),
        "signed_hit_rate": bt.get("signed_hit_rate"),
        "live_mature": live.get("n_mature", 0),
        "learning_detected": ev.get("learning_detected"),
        "next_steps_de": (report.get("next_steps_de") or [])[:3],
    }
