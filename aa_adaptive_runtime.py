"""Adaptive runtime — dynamic self-tuning orchestration for Marktanalyse.

Assesses market data, R3 diagnosis, feedback, and connectivity; adapts price source,
refinement intensity, and follow-up actions. No champion auto-promotion.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from aa_safe_io import atomic_write_json

ADAPTIVE_CONFIG = "control/adaptive_runtime.json"
ADAPTIVE_STATE = "control/adaptive_runtime_state.json"
ADAPTIVE_LOG = "control/adaptive_runtime.jsonl"

DEFAULT_ADAPTIVE = {
    "enabled": True,
    "price_data_mode": "auto",
    "prefer_internet_when_available": True,
    "loop_interval_normal_s": 300,
    "loop_interval_aggressive_s": 120,
    "aggressive_on_regime_drift": True,
    "aggressive_on_stale_prices": True,
    "auto_exemplar_retrain_when_stale": False,
    "exemplar_retrain_stale_days": 7,
    "boost_background_research_on_r3_weakness": True,
    "risk_off_hit_rate_floor": 0.45,
    "capability_profile": "full",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log(root: Path, event: str, **details: Any) -> None:
    ctrl = Path(root) / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"at_utc": _utc_now(), "event": event, **details}, ensure_ascii=False, sort_keys=True)
    with (ctrl / "adaptive_runtime.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_adaptive_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = dict(DEFAULT_ADAPTIVE)
    path = root / ADAPTIVE_CONFIG
    if path.is_file():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_adaptive_config(root: Path, patch: Mapping[str, Any]) -> Path:
    cfg = load_adaptive_config(root)
    cfg.update(dict(patch))
    path = Path(root) / ADAPTIVE_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, cfg)
    return path


def probe_internet_prices(*, timeout_s: float = 10.0) -> bool:
    """Quick connectivity check for live OHLCV (SPY)."""
    try:
        import yfinance as yf

        df = yf.download("SPY", period="5d", progress=False, threads=False, timeout=timeout_s)
        return df is not None and not df.empty
    except Exception:
        return False


def _read_adaptive_state(root: Path) -> Dict[str, Any]:
    path = Path(root) / ADAPTIVE_STATE
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def refresh_price_feed_state(
    root: Path,
    env: Optional[Mapping[str, str]] = None,
    *,
    write: bool = True,
) -> Dict[str, Any]:
    """Probe live connectivity and refresh price_source in adaptive state (no refinement)."""
    root = Path(root)
    merged_env = dict(os.environ if env is None else env)
    adaptive_cfg = load_adaptive_config(root)
    internet_ok = probe_internet_prices()
    price_source, price_source_reason = resolve_adaptive_price_source(
        merged_env,
        adaptive_cfg=adaptive_cfg,
        internet_ok=internet_ok,
    )

    prior = _read_adaptive_state(root)
    ctx = dict(prior.get("context") or {})
    ctx["internet_ok"] = internet_ok
    ctx["price_current"] = bool(ctx.get("price_current")) if price_source != "internet" else ctx.get("price_current", False)

    notes = list(prior.get("notes") or [])
    if price_source == "internet":
        notes = [n for n in notes if "Fictive/offline" not in str(n)]
        if "Live internet OHLCV active" not in notes:
            notes.append("Live internet OHLCV active")
    else:
        notes = [n for n in notes if "Live internet OHLCV" not in str(n)]
        if "Fictive/offline OHLCV active (internet later)" not in notes:
            notes.append("Fictive/offline OHLCV active (internet later)")

    state = {
        "at_utc": _utc_now(),
        "mode": str(prior.get("mode") or "NORMAL"),
        "price_source": price_source,
        "price_source_reason": price_source_reason,
        "loop_interval_s": int(prior.get("loop_interval_s") or 300),
        "actions": list(prior.get("actions") or []),
        "notes": notes[:6],
        "context": ctx,
    }
    if write:
        atomic_write_json(root / ADAPTIVE_STATE, state)
    return state


def resolve_adaptive_price_source(
    env: Mapping[str, str],
    *,
    adaptive_cfg: Optional[Mapping[str, Any]] = None,
    internet_ok: Optional[bool] = None,
) -> Tuple[str, str]:
    """Return (resolved_source, reason)."""
    explicit = str(env.get("AA_PRICE_DATA_SOURCE", "") or "").strip().lower()
    mode = str((adaptive_cfg or {}).get("price_data_mode", "auto") or "auto").lower()

    if explicit in {"fictive", "mock", "synthetic", "offline"}:
        return "fictive", "explicit_fictive"
    if explicit in {"internet", "live", "yfinance", "online", "real"}:
        return "internet", "explicit_internet"

    if explicit in {"auto", "dynamic", "adaptive", ""} or mode == "auto":
        if internet_ok is None:
            internet_ok = probe_internet_prices()
        if internet_ok and (adaptive_cfg or {}).get("prefer_internet_when_available", True):
            return "internet", "auto_internet_available"
        return "fictive", "auto_fictive_fallback"

    if mode == "fictive":
        return "fictive", "config_fictive"
    if mode == "internet":
        ok = internet_ok if internet_ok is not None else probe_internet_prices()
        return ("internet", "config_internet") if ok else ("fictive", "config_internet_unavailable")

    return "fictive", "default_fictive"


@dataclass
class AdaptiveContext:
    internet_ok: bool = False
    price_current: bool = False
    signal_current: bool = False
    price_latest: Optional[str] = None
    signal_date: Optional[str] = None
    r3_regime_match: Optional[bool] = None
    live_regime: str = ""
    cache_data_source: str = ""
    integrity_status: str = "NOT_VALIDATED"
    mature_outcomes: int = 0
    risk_off_hit_rate: Optional[float] = None
    risk_on_hit_rate: Optional[float] = None
    batch_busy: bool = False
    training_log_age_hours: Optional[float] = None


@dataclass
class AdaptivePlan:
    mode: str = "NORMAL"
    price_source: str = "fictive"
    price_source_reason: str = ""
    loop_interval_s: int = 300
    refinement_overrides: Dict[str, Any] = field(default_factory=dict)
    env_updates: Dict[str, str] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _read_price_cache_source(out_dir: Path) -> str:
    for base in (out_dir / "price_cache", Path("robustness_results_trading212") / "_shared_cache" / "price"):
        meta = base / "price_cache_meta.json"
        if meta.is_file():
            try:
                return str(json.loads(meta.read_text(encoding="utf-8")).get("data_source", "") or "")
            except Exception:
                pass
    return ""


def assess_adaptive_context(root: Path, env: Mapping[str, str]) -> AdaptiveContext:
    root = Path(root)
    ctx = AdaptiveContext()
    ctx.internet_ok = probe_internet_prices()

    try:
        from aa_data_freshness import assess_daily_data

        report = assess_daily_data(root, env)
        ctx.price_current = bool(report.price_current)
        ctx.signal_current = bool(report.signal_current)
        ctx.price_latest = report.price_latest.isoformat() if report.price_latest else None
        ctx.signal_date = report.signal_date.isoformat() if report.signal_date else None
    except Exception:
        pass

    try:
        from aa_ops_refresh import resolve_out_dir

        out_dir = resolve_out_dir(root, env)
        from aa_r3_daily_diagnosis import read_r3_diagnosis_manifest

        r3 = read_r3_diagnosis_manifest(out_dir)
        ctx.r3_regime_match = r3.get("regime_match")
        live = r3.get("live_regime") or {}
        ctx.live_regime = str(live.get("regime_label", "") or "")
        ctx.cache_data_source = _read_price_cache_source(out_dir)

        from aa_model_status import resolve_integrity_label

        ctx.integrity_status = resolve_integrity_label(out_dir)

        from aa_prediction_outcomes import ledger_status_counts

        counts = ledger_status_counts(out_dir)
        ctx.mature_outcomes = int(counts.get("mature_outcomes", 0) or 0)

        fb = r3.get("feedback_by_regime") or {}
        ro = fb.get("risk_on") or {}
        rf = fb.get("risk_off") or {}
        ctx.risk_on_hit_rate = ro.get("selected_signed_hit_rate")
        ctx.risk_off_hit_rate = rf.get("selected_signed_hit_rate")
    except Exception:
        pass

    try:
        from aa_pipeline_autopilot import is_batch_work_active

        ctx.batch_busy = is_batch_work_active(root)
    except Exception:
        pass

    log_path = root / "evidence" / "exemplar_portfolio_train.log"
    if log_path.is_file():
        age_h = (datetime.now().timestamp() - log_path.stat().st_mtime) / 3600.0
        ctx.training_log_age_hours = round(age_h, 2)

    return ctx


def build_adaptive_plan(
    ctx: AdaptiveContext,
    *,
    adaptive_cfg: Mapping[str, Any],
    env: Mapping[str, str],
) -> AdaptivePlan:
    plan = AdaptivePlan()
    plan.price_source, plan.price_source_reason = resolve_adaptive_price_source(
        env,
        adaptive_cfg=adaptive_cfg,
        internet_ok=ctx.internet_ok,
    )
    plan.env_updates["AA_PRICE_DATA_SOURCE"] = plan.price_source

    aggressive = False
    if adaptive_cfg.get("aggressive_on_regime_drift") and ctx.r3_regime_match is False:
        aggressive = True
        plan.notes.append("Regime-Drift: aggressive refinement")
    if adaptive_cfg.get("aggressive_on_stale_prices") and not ctx.price_current:
        aggressive = True
        plan.notes.append("Stale prices: force refresh")

    plan.mode = "AGGRESSIVE" if aggressive else "NORMAL"
    plan.loop_interval_s = int(
        adaptive_cfg.get("loop_interval_aggressive_s", 120)
        if aggressive
        else adaptive_cfg.get("loop_interval_normal_s", 300)
    )

    plan.refinement_overrides = {
        "force_prices": not ctx.price_current or aggressive,
        "refresh_signal": True,
        "auto_signal_on_regime_drift": True,
        "apply_turbo_env": True,
    }

    floor = float(adaptive_cfg.get("risk_off_hit_rate_floor", 0.45) or 0.45)
    if (
        adaptive_cfg.get("boost_background_research_on_r3_weakness")
        and ctx.mature_outcomes >= 5
        and ctx.risk_off_hit_rate is not None
        and ctx.risk_on_hit_rate is not None
        and ctx.risk_off_hit_rate < floor
        and ctx.risk_off_hit_rate < ctx.risk_on_hit_rate - 0.03
    ):
        plan.refinement_overrides["run_background_research"] = True
        plan.notes.append("R3 risk-off feedback weak: background research boosted")

    plan.actions.append("operational_refinement")

    if (
        adaptive_cfg.get("auto_exemplar_retrain_when_stale")
        and not ctx.batch_busy
        and ctx.integrity_status != "PASS"
    ):
        stale_days = int(adaptive_cfg.get("exemplar_retrain_stale_days", 7) or 7)
        if ctx.training_log_age_hours is None or ctx.training_log_age_hours > stale_days * 24:
            plan.actions.append("exemplar_retrain")
            plan.notes.append("No fresh validated model: schedule exemplar retrain")

    if plan.price_source == "internet":
        plan.notes.append("Live internet OHLCV active")
    else:
        plan.notes.append("Fictive/offline OHLCV active (internet later)")

    if ctx.live_regime:
        plan.notes.append(f"Live regime: {ctx.live_regime}")

    return plan


def adapt_operational_context(
    root: Path,
    env: Mapping[str, str],
    refinement_cfg: Mapping[str, Any],
) -> Tuple[Dict[str, str], Dict[str, Any], AdaptivePlan]:
    """Merge adaptive decisions into env + refinement config."""
    root = Path(root)
    adaptive_cfg = load_adaptive_config(root)
    if not adaptive_cfg.get("enabled", True):
        plan = AdaptivePlan(notes=["Adaptive runtime disabled"])
        return dict(env), dict(refinement_cfg), plan

    ctx = assess_adaptive_context(root, env)
    plan = build_adaptive_plan(ctx, adaptive_cfg=adaptive_cfg, env=env)

    merged_env = dict(env)
    merged_env.update(plan.env_updates)

    merged_ref = dict(refinement_cfg)
    merged_ref.update(plan.refinement_overrides)

    state = {
        "at_utc": _utc_now(),
        "mode": plan.mode,
        "price_source": plan.price_source,
        "price_source_reason": plan.price_source_reason,
        "loop_interval_s": plan.loop_interval_s,
        "actions": plan.actions,
        "notes": plan.notes,
        "context": {
            "internet_ok": ctx.internet_ok,
            "price_current": ctx.price_current,
            "signal_current": ctx.signal_current,
            "r3_regime_match": ctx.r3_regime_match,
            "live_regime": ctx.live_regime,
            "integrity_status": ctx.integrity_status,
            "mature_outcomes": ctx.mature_outcomes,
            "batch_busy": ctx.batch_busy,
        },
    }
    atomic_write_json(root / ADAPTIVE_STATE, state)
    _log(root, "adaptive_plan", **state)
    return merged_env, merged_ref, plan


def _python(root: Path) -> str:
    venv = root / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.is_file() else sys.executable


def run_exemplar_retrain(root: Path, *, fictive: bool = True) -> int:
    cmd = [_python(root), str(root / "tools" / "train_exemplar_portfolio.py")]
    if fictive:
        cmd.append("--fictive")
    env = os.environ.copy()
    if fictive:
        env["AA_PRICE_DATA_SOURCE"] = "fictive"
    return subprocess.run(cmd, cwd=str(root), env=env).returncode


@dataclass
class AdaptiveRunReport:
    ok: bool = False
    plan: Optional[AdaptivePlan] = None
    refinement_ok: bool = False
    retrain_rc: Optional[int] = None
    messages: List[str] = field(default_factory=list)


def run_adaptive_marktanalyse(
    root: Path,
    env: Optional[Mapping[str, str]] = None,
    *,
    log_print: bool = True,
    allow_retrain: bool = True,
) -> AdaptiveRunReport:
    """Single adaptive tick: plan -> refine -> optional retrain."""
    root = Path(root)
    report = AdaptiveRunReport()

    if env is None:
        from aa_config_env import load_aa_env

        env = load_aa_env(root)

    from aa_operational_refinement import load_refinement_config, run_operational_refinement

    ref_cfg = load_refinement_config(root)
    merged_env, merged_ref, plan = adapt_operational_context(root, env, ref_cfg)
    report.plan = plan

    if log_print:
        report.messages.append(f"[ADAPTIVE] Modus={plan.mode} Preise={plan.price_source} ({plan.price_source_reason})")
        for note in plan.notes:
            report.messages.append(f"  - {note}")

    if "operational_refinement" in plan.actions:
        ref_report = run_operational_refinement(root, merged_env, cfg=merged_ref, log_print=False)
        report.refinement_ok = ref_report.ok
        report.messages.extend(ref_report.messages)

    if allow_retrain and "exemplar_retrain" in plan.actions and not plan.refinement_overrides.get("batch_busy"):
        report.messages.append("[ADAPTIVE] Starte Exemplar-Retrain (Hintergrundprozess) …")
        report.retrain_rc = run_exemplar_retrain(root, fictive=(plan.price_source != "internet"))

    report.ok = report.refinement_ok or report.retrain_rc == 0
    if log_print:
        for line in report.messages:
            print(line)

    return report


def run_adaptive_loop(root: Path, *, max_iterations: Optional[int] = None) -> None:
    import time

    root = Path(root)
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        cfg = load_adaptive_config(root)
        if not cfg.get("enabled", True):
            break
        ctx = assess_adaptive_context(root, os.environ)
        plan = build_adaptive_plan(ctx, adaptive_cfg=cfg, env=os.environ)
        run_adaptive_marktanalyse(root, log_print=True, allow_retrain=True)
        time.sleep(max(60, int(plan.loop_interval_s)))


def format_adaptive_status_block(root: Path) -> str:
    path = Path(root) / ADAPTIVE_STATE
    if not path.is_file():
        return ""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    ctx = state.get("context") or {}
    lines = [
        "Adaptive Runtime",
        f"  Modus: {state.get('mode', '—')}",
        f"  Preisquelle: {state.get('price_source', '—')} ({state.get('price_source_reason', '')})",
        f"  Loop-Intervall: {state.get('loop_interval_s', '—')}s",
        f"  Internet: {'OK' if ctx.get('internet_ok') else 'offline'}",
        f"  R3-Regime: {ctx.get('live_regime') or '—'} | Match: {ctx.get('r3_regime_match')}",
        f"  Integritaet: {ctx.get('integrity_status', '—')}",
    ]
    for note in (state.get("notes") or [])[:4]:
        lines.append(f"  -> {note}")
    return "\n".join(lines)
