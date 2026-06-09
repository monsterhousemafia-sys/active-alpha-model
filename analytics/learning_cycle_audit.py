"""Weekly learning audit + Sportwagen->Rennwagen stage evaluation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_prediction_outcomes import compute_feedback_metrics, load_ledger
from aa_safe_io import atomic_write_json

EVOLUTION_TRACK_REL = Path("control/evolution_track.json")
EVOLUTION_STATE_REL = Path("control/evolution_state.json")
AUDIT_LATEST_REL = Path("evidence/learning_cycle_audit_latest.json")
AUDIT_HISTORY_REL = Path("evidence/learning_cycle_audit_history.jsonl")
OUT_DIR_NAME = "model_output_sp500_pit_t212"
LIVE_SOURCE = "LIVE_T212"


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


def load_evolution_track(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / EVOLUTION_TRACK_REL)


def load_evolution_state(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / EVOLUTION_STATE_REL)
    if not doc:
        return {
            "schema_version": 1,
            "current_stage_id": "sportwagen",
            "promoted_at_utc": None,
            "history": [],
        }
    return doc


def save_evolution_state(root: Path, state: Dict[str, Any]) -> None:
    state["updated_at_utc"] = _utc_now()
    atomic_write_json(Path(root) / EVOLUTION_STATE_REL, state)


def _ledger_metrics(root: Path, *, live_only: bool | None = None) -> Dict[str, Any]:
    ledger = load_ledger(Path(root) / OUT_DIR_NAME)
    if ledger.empty:
        return compute_feedback_metrics(ledger)
    if live_only is True:
        sub = ledger[ledger["source_run_id"].astype(str) == LIVE_SOURCE]
    elif live_only is False:
        sub = ledger[ledger["source_run_id"].astype(str) != LIVE_SOURCE]
    else:
        sub = ledger
    return compute_feedback_metrics(sub)


def _backtest_sealed(root: Path) -> bool:
    try:
        from analytics.live_profile_governance import is_h1_backtest_sealed

        if is_h1_backtest_sealed(root):
            return True
    except Exception:
        pass
    try:
        path = Path(root) / "research_evidence/r0_tuning_trial_ledger.json"
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            for row in doc.get("trials") or []:
                if str(row.get("variant_key") or "") == "DAILY_ALPHA_H1":
                    return str(row.get("status") or "").upper() in ("SEALED", "PASS", "COMPLETE")
    except Exception:
        pass
    runs = sorted((Path(root) / "validation_runs").glob("*DAILY_ALPHA_H1"), reverse=True)
    for run in runs[:3]:
        summary = run / "summary.json"
        if summary.is_file():
            try:
                doc = json.loads(summary.read_text(encoding="utf-8"))
                if doc.get("ok") or doc.get("status") == "PASS":
                    return True
            except (json.JSONDecodeError, OSError):
                pass
        if (run / "backtest_decisions.csv").is_file():
            return True
    return False


def _criteria_met(criteria: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if not criteria:
        return True
    live = ctx.get("live_metrics") or {}
    bt = ctx.get("backtest_metrics") or {}
    if "min_mature_live" in criteria and int(live.get("n_mature") or 0) < int(criteria["min_mature_live"]):
        return False
    if "min_live_signed_hit_rate" in criteria:
        rate = live.get("signed_hit_rate")
        if rate is None or float(rate) < float(criteria["min_live_signed_hit_rate"]):
            return False
    if criteria.get("live_mae_below_backtest"):
        live_mae = live.get("mae")
        bt_mae = bt.get("mae")
        if live_mae is None or bt_mae is None or float(live_mae) >= float(bt_mae):
            return False
    if criteria.get("backtest_sealed") is True and not ctx.get("backtest_sealed"):
        return False
    if criteria.get("daily_alpha_h1_backtest_sealed") and not ctx.get("backtest_sealed"):
        return False
    if criteria.get("min_weeks_improving"):
        need = int(criteria["min_weeks_improving"])
        if int(ctx.get("weeks_improving_signed_hit") or 0) < need:
            return False
    if criteria.get("shadow_pass") and not ctx.get("shadow_pass"):
        return False
    if criteria.get("m9_approved") and not ctx.get("m9_approved"):
        return False
    if criteria.get("evolution_allow_full_auto") and not ctx.get("evolution_allow_full_auto"):
        return False
    return True


def resolve_stage(root: Path, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root)
    track = load_evolution_track(root)
    stages = sorted(track.get("stages") or [], key=lambda s: int(s.get("order") or 0))
    gov = track.get("governance") or {}
    if ctx is None:
        ctx = build_audit_context(root)

    max_without_m9 = str(gov.get("max_auto_stage_without_m9") or "rennsport")
    max_order = next((int(s.get("order") or 0) for s in stages if s.get("id") == max_without_m9), 3)

    best = stages[0] if stages else {"id": "sportwagen", "label_de": "Sportwagen", "order": 0}
    for stage in stages:
        order = int(stage.get("order") or 0)
        if order > max_order and not ctx.get("evolution_allow_full_auto"):
            break
        if _criteria_met(stage.get("criteria") or {}, ctx):
            best = stage
        else:
            break
    return {
        "stage_id": str(best.get("id") or "sportwagen"),
        "stage_label_de": str(best.get("label_de") or "Sportwagen"),
        "stage_order": int(best.get("order") or 0),
        "auto_actions_allowed": list(best.get("auto_actions") or []),
        "next_stage_id": _next_stage_id(stages, best),
    }


def _next_stage_id(stages: List[Dict[str, Any]], current: Dict[str, Any]) -> Optional[str]:
    order = int(current.get("order") or 0)
    for s in stages:
        if int(s.get("order") or 0) == order + 1:
            return str(s.get("id"))
    return None


def _weeks_improving(prev: Dict[str, Any], live: Dict[str, Any]) -> int:
    prior_weeks = int(prev.get("weeks_improving_signed_hit") or 0)
    prev_rate = prev.get("live_signed_hit_rate")
    cur_rate = live.get("signed_hit_rate")
    if prev_rate is None or cur_rate is None:
        return prior_weeks
    if float(cur_rate) > float(prev_rate):
        return prior_weeks + 1
    return 0


def build_audit_context(root: Path) -> Dict[str, Any]:
    root = Path(root)
    track = load_evolution_track(root)
    gov = track.get("governance") or {}
    live_m = _ledger_metrics(root, live_only=True)
    bt_m = _ledger_metrics(root, live_only=False)
    prev = _load_json(root / AUDIT_LATEST_REL)
    prev_live = (prev.get("live_metrics") or {}) if prev else {}

    ctx = {
        "live_metrics": live_m,
        "backtest_metrics": bt_m,
        "backtest_sealed": _backtest_sealed(root),
        "shadow_pass": bool(_load_json(root / "evidence/shadow_monitoring_pass.json").get("ok")),
        "m9_approved": bool(_load_json(root / "control/champion_strategic_decision.json").get("champion_change_executed")),
        "evolution_allow_full_auto": bool(gov.get("evolution_allow_full_auto")),
        "weeks_improving_signed_hit": _weeks_improving(prev, live_m),
    }
    ctx["resolved_stage"] = resolve_stage(root, ctx)
    return ctx


def run_learning_cycle_audit(root: Path) -> Dict[str, Any]:
    """Compare WoW metrics, evaluate evolution stage, write evidence."""
    root = Path(root)
    ctx = build_audit_context(root)
    prev = _load_json(root / AUDIT_LATEST_REL)
    live = ctx["live_metrics"]
    bt = ctx["backtest_metrics"]
    stage = ctx["resolved_stage"]
    state = load_evolution_state(root)
    prev_stage = str(state.get("current_stage_id") or "sportwagen")
    new_stage = str(stage.get("stage_id") or "sportwagen")

    delta: Dict[str, Any] = {}
    if prev:
        pl = prev.get("live_metrics") or {}
        for key in ("n_mature", "signed_hit_rate", "mae", "ic_pearson"):
            if key in live and key in pl:
                try:
                    delta[f"live_{key}"] = float(live[key]) - float(pl[key])
                except (TypeError, ValueError):
                    pass

    learning_ok = int(live.get("n_mature") or 0) > int((prev.get("live_metrics") or {}).get("n_mature") or 0)
    hit_improved = float(delta.get("live_signed_hit_rate") or 0) > 0 if delta.get("live_signed_hit_rate") is not None else False

    if new_stage != prev_stage:
        hist = list(state.get("history") or [])
        hist.append({"from": prev_stage, "to": new_stage, "at_utc": _utc_now()})
        state["history"] = hist[-20:]
        state["current_stage_id"] = new_stage
        state["promoted_at_utc"] = _utc_now()
        save_evolution_state(root, state)
    elif not (Path(root) / EVOLUTION_STATE_REL).is_file():
        state["current_stage_id"] = new_stage
        save_evolution_state(root, state)

    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "ok": True,
        "stage": stage,
        "evolution_state": state,
        "live_metrics": live,
        "backtest_metrics": bt,
        "delta_vs_previous": delta,
        "learning_detected": learning_ok or hit_improved or int(live.get("n_mature") or 0) > 0,
        "backtest_sealed": ctx.get("backtest_sealed"),
        "message_de": (
            f"Evolution: {stage.get('stage_label_de')} (Stufe {stage.get('stage_order')}). "
            f"Live reif: {live.get('n_mature', 0)}, signed_hit: "
            f"{live.get('signed_hit_rate', '—') if live.get('signed_hit_rate') is not None else '—'}."
        ),
        "next_stage_id": stage.get("next_stage_id"),
        "blocked_full_auto_reason": (
            None
            if ctx.get("evolution_allow_full_auto")
            else "evolution_allow_full_auto=false — Rennwagen-Stufe gesperrt bis M9+Shadow"
        ),
    }
    atomic_write_json(root / AUDIT_LATEST_REL, report)
    hist_path = root / AUDIT_HISTORY_REL
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    with hist_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")
    return report
