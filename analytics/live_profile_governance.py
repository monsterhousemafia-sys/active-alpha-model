"""Live-profile governance: single truth, experimental H1 gate, daily-trading fee context."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VARIANT_H1 = "DAILY_ALPHA_H1"
PROFILE_H1 = "daily_alpha_h1"
LEDGER_REL = Path("research_evidence/r0_tuning_trial_ledger.json")
EVAL_REL = Path("evidence/daily_alpha_h1_evaluation_latest.json")
OBJECTIVE_REL = Path("control/r0_migration/alpha_objective.json")
OPS_REL = Path("control/prediction_operations.json")

# Daily rebalance (h=1): turnover drag dominates — stress gate uses +25 bps incremental on turnover.
DAILY_COST_STRESS_EXTRA_BPS = 25.0
DEFAULT_SLIPPAGE_BPS = 2.0
DEFAULT_FX_BPS = 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_alpha_objective(root: Path) -> Dict[str, Any]:
    path = Path(root) / OBJECTIVE_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def is_h1_backtest_sealed(root: Path) -> bool:
    root = Path(root)
    eval_doc = _load_json(root / EVAL_REL)
    if eval_doc.get("pass_alpha_objective") and eval_doc.get("pass_daily_cost_stress"):
        return True
    ledger = _load_json(root / LEDGER_REL)
    for row in ledger.get("trials") or []:
        if str(row.get("variant_key") or "") == VARIANT_H1:
            return str(row.get("status") or "").upper() in ("SEALED", "PASS", "COMPLETE")
    return False


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _h1_backtest_process_active(root: Path, run: Path) -> bool:
    """True if validation/backtest child process still targets this run dir."""
    import subprocess

    needle = run.name
    try:
        proc = subprocess.run(
            ["ps", "-eo", "args"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        for line in (proc.stdout or "").splitlines():
            if needle not in line:
                continue
            if "active_alpha_model.py" in line or "run_validation_matrix.py" in line:
                return True
    except Exception:
        pass
    return False


def _h1_checkpoint_progress(run: Path) -> tuple[int, int]:
    ck = run / "path_sim_checkpoint_meta.json"
    if not ck.is_file():
        return 0, 0
    meta = _load_json(ck)
    return int(meta.get("last_n") or 0), int(meta.get("n_daily") or 0)


def _classify_h1_run(root: Path, run: Path) -> Optional[Dict[str, Any]]:
    rel = str(run.relative_to(root)).replace("\\", "/")
    if (run / "strategy_daily_returns.csv").is_file():
        return {"status": "COMPLETE", "run_dir": rel, "progress_pct": 100}
    if _h1_backtest_process_active(root, run):
        detail = "Backtest-Prozess aktiv"
        if (run / "features.parquet").is_file():
            detail = "Path-Simulation läuft (Features fertig)"
        last_n, n_daily = _h1_checkpoint_progress(run)
        pct = int(100 * last_n / n_daily) if n_daily else 5
        ck = run / "path_sim_checkpoint_meta.json"
        log = run / "validation_run.log"
        log_age_s = max(0.0, datetime.now().timestamp() - log.stat().st_mtime) if log.is_file() else 999999.0
        if ck.is_file():
            ck_age_s = max(0.0, datetime.now().timestamp() - ck.stat().st_mtime)
            recently_active = log_age_s < 600 or ck_age_s < 600
            if (
                not recently_active
                and ck_age_s > 1800
                and n_daily
                and last_n >= max(0, n_daily - 2)
            ):
                return {
                    "status": "ZOMBIE",
                    "run_dir": rel,
                    "detail_de": (
                        f"Checkpoint stale ({int(ck_age_s // 60)}min) bei {last_n}/{n_daily} — "
                        "Turbo-Resume nötig"
                    ),
                    "progress_pct": pct,
                }
        return {"status": "RUNNING", "run_dir": rel, "detail_de": detail, "progress_pct": pct}
    if (run / "features.parquet").is_file():
        ck = run / "path_sim_checkpoint_meta.json"
        last_n, n_daily = _h1_checkpoint_progress(run)
        pct = int(100 * last_n / n_daily) if n_daily else 50
        if ck.is_file():
            age_s = max(0.0, datetime.now().timestamp() - ck.stat().st_mtime)
            if age_s > 600:
                return {
                    "status": "ZOMBIE",
                    "run_dir": rel,
                    "detail_de": "Path-Sim hängt — ai_kernel h1 (setzt bei Checkpoint fort)",
                    "progress_pct": pct,
                }
        return {
            "status": "ZOMBIE",
            "run_dir": rel,
            "detail_de": "Kein Prozess — Checkpoint-Fortsetzung",
            "progress_pct": pct,
        }
    log = run / "validation_run.log"
    if not log.is_file():
        return None
    text = log.read_text(encoding="utf-8", errors="replace")
    age_s = max(0.0, datetime.now().timestamp() - log.stat().st_mtime)
    if "Traceback (most recent call last)" in text or "ModuleNotFoundError" in text:
        return {
            "status": "FAILED",
            "run_dir": rel,
            "detail_de": "Backtest abgebrochen — python3 tools/ai_kernel.py h1 (Linux)",
            "progress_pct": 0,
        }
    if len(text) < 8000 and "PROGRESS" in text and age_s > 900:
        return {
            "status": "ZOMBIE",
            "run_dir": rel,
            "detail_de": "Backtest-Log ohne Fortschritt — ai_kernel h1",
            "progress_pct": 0,
        }
    if age_s < 86_400 and len(text) < 500_000:
        return {"status": "RUNNING", "run_dir": rel, "progress_pct": 5}
    return None


def h1_backtest_status(root: Path) -> Dict[str, Any]:
    """Distinguish complete / running / zombie / missing — bevorzugt Run mit höchstem Fortschritt."""
    root = Path(root)
    vroot = root / "validation_runs"
    if not vroot.is_dir():
        return {"status": "MISSING", "run_dir": None}
    runs = sorted(
        (p for p in vroot.iterdir() if p.is_dir() and p.name.endswith(f"_{VARIANT_H1}")),
        key=lambda p: p.name,
        reverse=True,
    )
    best: Optional[Dict[str, Any]] = None
    best_score = -1
    status_rank = {"COMPLETE": 1000, "RUNNING": 300, "ZOMBIE": 200, "FAILED": 50, "MISSING": 0}
    for run in runs:
        doc = _classify_h1_run(root, run)
        if not doc:
            continue
        pct = int(doc.get("progress_pct") or 0)
        score = status_rank.get(str(doc.get("status")), 0) * 1000 + pct
        if score > best_score:
            best_score = score
            best = doc
    if best:
        out = {k: v for k, v in best.items() if k != "progress_pct"}
        return out
    return {"status": "MISSING", "run_dir": None}


def daily_trading_fee_context(root: Path) -> Dict[str, Any]:
    """Document T212 + slippage cost pressure for daily (h=1) rebalance."""
    root = Path(root)
    obj = load_alpha_objective(root)
    ocfg = obj.get("objective") or {}
    slippage = float(ocfg.get("slippage_bps") or DEFAULT_SLIPPAGE_BPS)
    roundtrip_bps = 2.0 * slippage + 2.0 * DEFAULT_FX_BPS
    stress_bps = DAILY_COST_STRESS_EXTRA_BPS
    return {
        "schema_version": 1,
        "rebalance_every": int(obj.get("decision", {}).get("rebalance_every") or ocfg.get("rebalance_every") or 1),
        "horizon": int(obj.get("decision", {}).get("horizon") or ocfg.get("horizon") or 1),
        "fee_model": str(ocfg.get("fee_model") or "trading212_us"),
        "slippage_bps_per_side": slippage,
        "fx_bps_per_side": DEFAULT_FX_BPS,
        "roundtrip_bps_baseline": roundtrip_bps,  # no T212 commission; FX+slippage on USD names
        "cost_stress_incremental_bps": stress_bps,
        "note_de": (
            "Tages-Rebalance (h=1): Kosten skaliieren mit Turnover pro Tag — "
            f"Baseline ~{roundtrip_bps:.1f} bps Roundtrip + Stress +{stress_bps:.0f} bps auf Rebalance-Turnover. "
            "Ohne sealed PASS vs mom_1_top12 netto ist Live-Echtgeld Forschung."
        ),
    }


def h1_model_evidence(root: Path) -> Dict[str, Any]:
    """Consolidated H1 state for prediction/plan/engine (no fabricated pass_full_seal)."""
    root = Path(root)
    bt = h1_backtest_status(root)
    sealed = is_h1_backtest_sealed(root)
    eval_doc = _load_json(root / EVAL_REL)
    seal_required = True
    seal_policy_de = ""
    try:
        from analytics.h1_seal_policy import is_h1_seal_required, seal_policy_banner_de

        seal_required = is_h1_seal_required(root)
        if not seal_required:
            seal_policy_de = seal_policy_banner_de(root)
    except Exception:
        pass

    metrics_raw = eval_doc.get("metrics_strategy") or {}
    metrics_summary: Optional[Dict[str, Any]] = None
    if metrics_raw:
        metrics_summary = {
            k: metrics_raw[k]
            for k in ("sharpe_0rf", "cagr", "max_drawdown", "n_days", "daily_hit_rate")
            if metrics_raw.get(k) is not None
        }

    status = str(bt.get("status") or "MISSING")
    run_dir = bt.get("run_dir") or eval_doc.get("run_dir")
    operational_ok = status == "COMPLETE" and (sealed or not seal_required)

    return {
        "h1_status": status,
        "run_dir": run_dir,
        "sealed": sealed,
        "pass_full_seal": bool(eval_doc.get("pass_full_seal")),
        "seal_required": seal_required,
        "seal_policy_de": seal_policy_de,
        "operational_ok": operational_ok,
        "metrics_strategy": metrics_summary,
        "evaluated_at_utc": eval_doc.get("evaluated_at_utc"),
        "message_de": eval_doc.get("message_de"),
        "detail_de": bt.get("detail_de"),
    }


def experimental_profile_blockers(root: Path) -> List[str]:
    """Hard blockers for unvalidated experimental live profile + real money."""
    root = Path(root)
    try:
        from analytics.h1_seal_policy import is_h1_seal_required

        if not is_h1_seal_required(root):
            return []
    except Exception:
        pass
    ops = _load_json(root / OPS_REL)
    safety = ops.get("safety") or {}
    if not safety.get("real_money"):
        return []
    active = str(ops.get("active_profile") or "")
    experimental = list(ops.get("experimental_profiles") or [PROFILE_H1])
    if active not in experimental:
        return []
    if is_h1_backtest_sealed(root):
        return []
    blockers = ["EXPERIMENTAL_PROFILE_UNSEALED_REAL_MONEY"]
    bt = h1_backtest_status(root)
    if bt.get("status") == "ZOMBIE":
        blockers.append("DAILY_ALPHA_H1_BACKTEST_ZOMBIE")
    elif bt.get("status") in ("MISSING", "RUNNING", "FAILED"):
        blockers.append("DAILY_ALPHA_H1_NOT_SEALED")
    if bt.get("status") == "FAILED":
        blockers.append("DAILY_ALPHA_H1_BACKTEST_FAILED")
    return blockers


def sync_readiness_with_order_gate(root: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Single truth: prediction_readiness.ok follows order gate + experimental profile rules."""
    from analytics.prediction_operations import evaluate_prediction_readiness_for_orders

    root = Path(root)
    gate = evaluate_prediction_readiness_for_orders(root, readiness=payload)
    exp_blockers = experimental_profile_blockers(root)
    blockers = sorted(set((gate.get("blockers") or []) + exp_blockers))
    ok = len(blockers) == 0 and bool(payload.get("profile_used")) and bool(payload.get("top_picks"))
    out = dict(payload)
    out["ok"] = ok
    out["order_gate_ok"] = bool(gate.get("ok"))
    out["blockers"] = blockers
    out["price_latest"] = gate.get("price_latest") or out.get("price_latest")
    out["price_current"] = gate.get("price_current")
    out["signal_current"] = gate.get("signal_current")
    out["daily_trading_fee_context"] = daily_trading_fee_context(root)
    h1 = h1_model_evidence(root)
    out["h1_backtest_status"] = {"status": h1["h1_status"], "run_dir": h1.get("run_dir")}
    out["h1_backtest_sealed"] = h1["sealed"]
    out["h1_operational_ok"] = h1["operational_ok"]
    out["h1_evaluation"] = {
        "pass_full_seal": h1["pass_full_seal"],
        "evaluated_at_utc": h1.get("evaluated_at_utc"),
        "metrics_strategy": h1.get("metrics_strategy"),
        "message_de": h1.get("message_de"),
        "run_dir": h1.get("run_dir"),
    }
    if h1.get("seal_policy_de"):
        out["h1_governance_banner_de"] = h1["seal_policy_de"]
    elif h1["h1_status"] == "COMPLETE":
        out["h1_governance_banner_de"] = (
            f"H1 COMPLETE — pass_full_seal={h1['pass_full_seal']} (informativ)"
        )
    if not ok:
        out["last_error"] = ", ".join(blockers) if blockers else out.get("last_error")
    out["message_de"] = gate.get("message_de") if not ok else out.get("message_de", "Predict bereit.")
    return out


def apply_cost_stress_to_returns(series, turnover, *, extra_bps: float = DAILY_COST_STRESS_EXTRA_BPS):
    """Apply incremental bps on rebalance turnover (same logic as aa_cost_stress)."""
    from aa_cost_stress import apply_incremental_cost_stress

    return apply_incremental_cost_stress(series, turnover, extra_bps=extra_bps)


def load_run_turnover(root: Path, run_dir: Path):
    import pandas as pd

    for name in ("backtest_decisions.csv",):
        path = run_dir / name
        if not path.is_file():
            continue
        try:
            frame = pd.read_csv(path, usecols=lambda c: c in {"rebalance_date", "turnover"})
            if "turnover" not in frame.columns:
                continue
            rb = frame.drop_duplicates("rebalance_date")
            rb["rebalance_date"] = pd.to_datetime(rb["rebalance_date"])
            return pd.Series(rb["turnover"].values, index=rb["rebalance_date"]).sort_index()
        except Exception:
            pass
    return None
