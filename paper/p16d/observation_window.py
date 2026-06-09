"""Post-baseline observation window — baseline not counted as performance."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_window(root: Path) -> Dict[str, Any]:
    path = root / "paper/p16d/observation_window_state.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))

    p16c = root / "paper/p16c/observation_window_state.json"
    base = {
        "p16c_baseline_batch_count": 1,
        "p16c_baseline_independent_performance_marks": 0,
        "p16c_baseline_classification": "INITIAL_CORRECTED_BASELINE_BATCH_NOT_INDEPENDENT_PERFORMANCE_EVENT",
        "validated_performance_window_start_utc": None,
        "post_baseline_validated_batches": 0,
        "independent_post_baseline_portfolio_marks": 0,
        "valid_performance_instrument_observations": 0,
        "independent_signal_events": 0,
        "independent_virtual_rebalances": 0,
        "data_quality_pass_rate": 0.0,
        "fx_quality_pass_rate": 0.0,
        "portfolio_reconciliation_pass_rate": 1.0,
        "incident_count": 0,
        "paused_instrument_count": 0,
        "status": "BASELINE_ONLY",
        "scaling_gate_status": "NOT_READY_BASELINE_ONLY",
    }
    if p16c.is_file():
        pc = json.loads(p16c.read_text(encoding="utf-8"))
        base["p16c_validated_epoch_utc"] = pc.get("validated_observation_epoch_start_utc")
    return base


def record_post_baseline_batch(
    root: Path,
    batch: Dict[str, Any],
    mtm: Dict[str, Any],
    *,
    hardening_complete: bool,
) -> Dict[str, Any]:
    win = load_window(root)
    if hardening_complete and not win.get("validated_performance_window_start_utc"):
        win["validated_performance_window_start_utc"] = _utc_now()

    if win.get("validated_performance_window_start_utc"):
        win["post_baseline_validated_batches"] = int(win.get("post_baseline_validated_batches", 0)) + 1
        perf_obs = sum(1 for _ in (batch.get("instrument_conversions") or []) if _.get("performance_valid"))
        win["valid_performance_instrument_observations"] = int(win.get("valid_performance_instrument_observations", 0)) + perf_obs

        if mtm.get("independent_post_baseline_mark"):
            win["independent_post_baseline_portfolio_marks"] = int(win.get("independent_post_baseline_portfolio_marks", 0)) + 1

        start = win["validated_performance_window_start_utc"]
        elapsed_h = (_parse(_utc_now()) - _parse(start)).total_seconds() / 3600.0
        win["elapsed_performance_window_hours"] = round(elapsed_h, 4)

        pol_path = root / "paper/config/p16_forward_observation_and_scaling_policy.json"
        min_batches = 3
        min_hours = 24
        min_marks = 3
        if pol_path.is_file():
            pol = json.loads(pol_path.read_text(encoding="utf-8"))
            min_batches = int(pol.get("minimum_independent_portfolio_marks", 3))
            min_hours = int(pol.get("minimum_observation_duration_hours", 24))
            min_marks = min_batches

        limited = batch.get("portfolio_scope") == "PROVISIONAL_EXECUTABLE"
        if (
            win["post_baseline_validated_batches"] >= min_batches
            and win["independent_post_baseline_portfolio_marks"] >= min_marks
            and elapsed_h >= min_hours
        ):
            win["status"] = "POST_BASELINE_WINDOW_COMPLETE_FOR_VIRTUAL_SCALING_REVIEW"
            win["scaling_gate_status"] = "READY_FOR_VIRTUAL_SCALING_REVIEW"
        elif limited:
            win["status"] = "POST_BASELINE_WINDOW_RUNNING_LIMITED_PORTFOLIO"
            win["scaling_gate_status"] = "NOT_READY_PENDING_POST_BASELINE_WINDOW"
        else:
            win["status"] = "POST_BASELINE_WINDOW_RUNNING_SAMPLE_INSUFFICIENT"
            win["scaling_gate_status"] = "NOT_READY_PENDING_POST_BASELINE_WINDOW"

        dq = batch.get("data_quality_gate", "")
        if dq.startswith("PASS"):
            win["data_quality_pass_rate"] = round(
                (win.get("_dq_pass", 0) + 1) / max(win["post_baseline_validated_batches"], 1), 4
            )
            win["_dq_pass"] = win.get("_dq_pass", 0) + 1
        if batch.get("fx_runtime_gate") == "PASS_READ_ONLY_FX_OBSERVATION":
            win["fx_quality_pass_rate"] = 1.0

    atomic_write_json(root / "paper/p16d/observation_window_state.json", win)

    ledger = root / "paper/p16d/observation_batch_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"batch": batch, "mtm": {k: mtm.get(k) for k in ("portfolio_value_eur", "independent_post_baseline_mark")}}, default=str) + "\n")

    perf = root / "paper/p16d/performance_window_ledger.jsonl"
    with perf.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"window": {k: win.get(k) for k in win if not k.startswith("_")}}, default=str) + "\n")

    return win
