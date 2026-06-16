"""Operational refinement orchestrator — full daily capacity chain for live predictions.

Runs the complete loop: Tagesdaten → R3-Diagnose → Signal (bei Drift) → Feedback →
Modellstatus → Control-Plane → Cockpit-Snapshot. Designed for Ryzen 3950X / turbo profile.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aa_safe_io import atomic_write_json

REFINEMENT_CONFIG = "control/operational_refinement.json"
REFINEMENT_STATE = "control/operational_refinement_state.json"
REFINEMENT_LOG = "control/operational_refinement.jsonl"

DEFAULT_REFINEMENT = {
    "enabled": True,
    "force_prices": False,
    "refresh_signal": True,
    "auto_signal_on_regime_drift": True,
    "update_model_status": True,
    "refresh_cockpit_snapshot": True,
    "sync_control_plane": True,
    "sync_outcome_ledger": True,
    "run_self_calibration": True,
    "run_background_research": False,
    "apply_turbo_env": True,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log_event(root: Path, event: str, **details: Any) -> None:
    ctrl = Path(root) / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"at_utc": _utc_now(), "event": event, **details}, ensure_ascii=False, sort_keys=True)
    with (ctrl / "operational_refinement.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_refinement_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = dict(DEFAULT_REFINEMENT)
    path = root / REFINEMENT_CONFIG
    if path.is_file():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    safety = root / "control" / "operational_safety_flags.json"
    if safety.is_file():
        try:
            flags = json.loads(safety.read_text(encoding="utf-8"))
            if str(flags.get("AUTO_RESEARCH", "")).upper() == "ENABLED":
                cfg.setdefault("run_background_research", True)
        except Exception:
            pass
    return cfg


def save_refinement_config(root: Path, patch: Mapping[str, Any]) -> Path:
    root = Path(root)
    cfg = load_refinement_config(root)
    cfg.update(dict(patch))
    path = root / REFINEMENT_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, cfg)
    return path


def apply_turbo_capacity_env(env: Dict[str, str]) -> Dict[str, str]:
    """Apply hardware-max settings when not explicitly overridden."""
    out = dict(env)
    if str(out.get("AA_CPU_CORES", "") or "").strip():
        pass
    else:
        out["AA_CPU_CORES"] = "16"
    out.setdefault("AA_RESERVE_CPU_CORES", "0")
    out.setdefault("AA_RUNTIME_PROFILE", "turbo")
    out.setdefault("AA_PROCESS_PRIORITY", "high")
    out.setdefault("AA_AUTO_OPS_REFRESH", "1")
    out.setdefault("AA_SKIP_DOWNLOAD_IF_CACHED", "0")
    return out


def _resolve_out_dir(root: Path, env: Mapping[str, str]) -> Path:
    from aa_ops_refresh import resolve_out_dir

    return resolve_out_dir(root, env)


@dataclass
class OperationalRefinementReport:
    ok: bool = False
    steps: List[Dict[str, Any]] = field(default_factory=list)
    live_sync: Dict[str, Any] = field(default_factory=dict)
    r3_regime_match: Optional[bool] = None
    signal_refreshed: bool = False
    cockpit_refreshed: bool = False
    model_status_updated: bool = False
    messages: List[str] = field(default_factory=list)

    def add(self, step: str, status: str, **extra: Any) -> None:
        self.steps.append({"step": step, "status": status, **extra})


def run_operational_refinement(
    root: Path,
    env: Optional[Mapping[str, str]] = None,
    *,
    cfg: Optional[Mapping[str, Any]] = None,
    log_print: bool = True,
) -> OperationalRefinementReport:
    """Execute the full operational refinement chain."""
    root = Path(root)
    refinement_cfg = dict(cfg or load_refinement_config(root))
    report = OperationalRefinementReport()

    if not refinement_cfg.get("enabled", True):
        report.add("refinement", "DISABLED")
        report.messages.append("[SKIP] Operational refinement deaktiviert")
        return report

    if env is None:
        from aa_config_env import load_aa_env

        env = load_aa_env(root)
    env = dict(env)

    try:
        from aa_adaptive_runtime import adapt_operational_context

        env, refinement_cfg, adaptive_plan = adapt_operational_context(root, env, refinement_cfg)
        report.add("adaptive_plan", adaptive_plan.mode, price_source=adaptive_plan.price_source)
    except Exception as exc:
        report.add("adaptive_plan", "WARN", error=str(exc))

    if refinement_cfg.get("apply_turbo_env", True):
        env = apply_turbo_capacity_env(env)

    out_dir = _resolve_out_dir(root, env)

    # 1 — Live daily sync + R3 diagnosis (core)
    try:
        from aa_live_daily_sync import sync_live_daily_for_predictions

        sync = sync_live_daily_for_predictions(
            root,
            env,
            force_prices=bool(refinement_cfg.get("force_prices")),
            refresh_signal=bool(refinement_cfg.get("refresh_signal", True)),
            log_print=False,
        )
        report.live_sync = {
            "ok": sync.ok,
            "prices_refreshed": sync.prices_refreshed,
            "signal_refreshed": sync.signal_refreshed,
            "price_latest": sync.price_latest,
            "signal_date": sync.signal_date,
            "r3_regime_match": sync.r3_regime_match,
            "r3_diagnosis_ok": sync.r3_diagnosis_ok,
            "merged_ticker_count": sync.merged_ticker_count,
        }
        report.r3_regime_match = sync.r3_regime_match
        report.signal_refreshed = sync.signal_refreshed
        report.messages.extend(sync.messages)
        report.add(
            "live_daily_sync",
            "OK" if sync.ok else "WARN",
            r3_regime_match=sync.r3_regime_match,
            signal_refreshed=sync.signal_refreshed,
        )
    except Exception as exc:
        report.add("live_daily_sync", "FAIL", error=str(exc))
        report.messages.append(f"[FAIL] Live-Sync: {exc}")

    # 2 — Force signal refresh on regime drift
    if (
        refinement_cfg.get("auto_signal_on_regime_drift", True)
        and report.r3_regime_match is False
        and refinement_cfg.get("refresh_signal", True)
    ):
        try:
            from aa_data_freshness import assess_daily_data
            from aa_ops_refresh import refresh_signal_portfolio
            from aa_r3_daily_diagnosis import verify_r3_diagnosis_against_daily_data

            report.messages.append("[INFO] Regime-Drift erkannt — erzwinge Signal-Refresh mit Tagesdaten …")
            refreshed = refresh_signal_portfolio(root, env, log=lambda m: report.messages.append(m))
            report.signal_refreshed = report.signal_refreshed or refreshed
            r3 = verify_r3_diagnosis_against_daily_data(root, env, update_feedback=False, log_print=False)
            report.r3_regime_match = r3.regime_match
            report.messages.extend(r3.messages)
            data = assess_daily_data(root, env)
            report.add(
                "auto_signal_on_drift",
                "OK" if refreshed else "WARN",
                regime_match=r3.regime_match,
                signal_date=data.signal_date.isoformat() if data.signal_date else None,
            )
        except Exception as exc:
            report.add("auto_signal_on_drift", "FAIL", error=str(exc))
            report.messages.append(f"[WARN] Auto-Signal bei Drift fehlgeschlagen: {exc}")

    # 3 — Outcome ledger (redundant-safe; R3 sync may have run it)
    if refinement_cfg.get("sync_outcome_ledger", True):
        try:
            from aa_prediction_outcomes import update_prediction_outcomes

            summary = update_prediction_outcomes(out_dir)
            report.add(
                "sync_outcome_ledger",
                "OK",
                mature=summary.get("metrics", {}).get("n_mature", 0),
            )
        except Exception as exc:
            report.add("sync_outcome_ledger", "FAIL", error=str(exc))

    # 4 — Model status
    if refinement_cfg.get("update_model_status", True):
        try:
            from aa_model_status import write_model_status

            write_model_status(out_dir)
            report.model_status_updated = True
            report.add("model_status", "OK")
        except Exception as exc:
            report.add("model_status", "FAIL", error=str(exc))

    # 5 — Control plane
    if refinement_cfg.get("sync_control_plane", True):
        try:
            from aa_control_plane import sync_control_plane, write_next_cursor_prompt

            sync_control_plane(root, out_dir)
            write_next_cursor_prompt(root)
            report.add("sync_control_plane", "OK")
        except Exception as exc:
            report.add("sync_control_plane", "FAIL", error=str(exc))

    # 6 — Background research (optional, CPU-heavy)
    if refinement_cfg.get("run_background_research", False):
        try:
            from aa_background_research import run_background_research

            summary = run_background_research(root, out_dir)
            report.add(
                "background_research",
                "OK" if summary.get("status") == "OK" else str(summary.get("status", "FAIL")),
                variants_checked=summary.get("variants_checked"),
            )
        except Exception as exc:
            report.add("background_research", "FAIL", error=str(exc))

    # 7 — Cockpit snapshot
    if refinement_cfg.get("refresh_cockpit_snapshot", True):
        try:
            from aa_decision_cockpit_readonly_snapshot import refresh_live_review_snapshot

            path = refresh_live_review_snapshot(root)
            report.cockpit_refreshed = True
            report.add("cockpit_snapshot", "OK", path=str(path))
            report.messages.append(f"[OK] Cockpit-Snapshot aktualisiert: {path}")
        except Exception as exc:
            report.add("cockpit_snapshot", "FAIL", error=str(exc))
            report.messages.append(f"[WARN] Cockpit-Snapshot: {exc}")

    # 8 — Prognose-Selbstkalibrierung (read-only)
    if refinement_cfg.get("run_self_calibration", True):
        try:
            from analytics.prediction_self_calibration import run_prediction_self_calibration

            cal = run_prediction_self_calibration(root, persist=True)
            report.add(
                "self_calibration",
                "OK" if cal.get("ok") or cal.get("skipped") else "WARN",
                headline_de=str(cal.get("headline_de") or "")[:120],
            )
        except Exception as exc:
            report.add("self_calibration", "FAIL", error=str(exc))

    failed = [s for s in report.steps if s.get("status") == "FAIL"]
    report.ok = not failed and bool(report.live_sync.get("ok", False) or report.cockpit_refreshed)

    state = {
        "at_utc": _utc_now(),
        "ok": report.ok,
        "steps": report.steps,
        "r3_regime_match": report.r3_regime_match,
        "signal_refreshed": report.signal_refreshed,
        "cockpit_refreshed": report.cockpit_refreshed,
        "model_status_updated": report.model_status_updated,
    }
    atomic_write_json(root / REFINEMENT_STATE, state)
    _log_event(root, "operational_refinement_complete", **state)

    if log_print:
        for line in report.messages:
            print(line)
        print(json.dumps(state, indent=2))

    return report


def run_operational_refinement_loop(
    root: Path,
    *,
    interval_seconds: int = 300,
    max_iterations: Optional[int] = None,
) -> None:
    """Continuous refinement loop for unattended operation."""
    import time

    root = Path(root)
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        cfg = load_refinement_config(root)
        if not cfg.get("enabled", True):
            break
        run_operational_refinement(root, cfg=cfg, log_print=True)
        time.sleep(max(60, int(interval_seconds)))
