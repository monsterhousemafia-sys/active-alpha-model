"""R3 daily diagnosis — verify risk-off regime and selection against live Tagesdaten.

Always cross-checks stored model signal with fresh benchmark OHLCV so operational
predictions refine continuously (feedback loop, no champion auto-promotion).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd

from aa_safe_io import atomic_write_json

R3_DIAGNOSIS_FILE = "r3_daily_diagnosis.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _out_dir(root: Path, env: Mapping[str, str]) -> Path:
    rel = str(env.get("AA_BACKTEST_OUT_DIR", "model_output_sp500_pit_t212") or "model_output_sp500_pit_t212")
    path = Path(rel)
    return path if path.is_absolute() else root / path


def load_benchmark_close_series(out_dir: Path, benchmark: str) -> Tuple[Optional[pd.Series], Optional[str]]:
    """Load benchmark close prices from price_cache panel."""
    panel_path = Path(out_dir) / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return None, None
    try:
        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
    except Exception:
        try:
            panel = pd.read_parquet(panel_path)
        except Exception:
            return None, None
    if panel.empty or "ticker" not in panel.columns or "Close" not in panel.columns:
        return None, None
    bench = str(benchmark or "SPY").upper().strip()
    sub = panel[panel["ticker"].astype(str).str.upper() == bench].copy()
    if sub.empty:
        return None, None
    sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
    sub = sub.dropna(subset=["date"]).sort_values("date")
    if sub.empty:
        return None, None
    close = pd.to_numeric(sub["Close"], errors="coerce")
    series = pd.Series(close.values, index=pd.DatetimeIndex(sub["date"]), name=bench)
    series = series[~series.index.duplicated(keep="last")].dropna()
    latest = series.index.max().date().isoformat() if not series.empty else None
    return series, latest


def compute_live_market_regime(
    bench_close: pd.Series,
    cfg: Any,
) -> Dict[str, Any]:
    """Recompute SPY regime inputs using the same rules as backtest."""
    from aa_portfolio import determine_risk_on

    if bench_close.empty:
        return {
            "market_trend_200": None,
            "market_ret_63": None,
            "risk_on": None,
            "regime_label": "UNKNOWN",
        }
    close = bench_close.sort_index()
    trend = float((close.iloc[-1] > close.rolling(200).mean().iloc[-1]))
    ret63 = float(close.iloc[-1] / close.shift(63).iloc[-1] - 1.0) if len(close) > 63 else -1.0
    risk_on = bool(determine_risk_on(trend, ret63, cfg))
    return {
        "as_of_date": close.index[-1].date().isoformat(),
        "market_trend_200": trend,
        "market_ret_63": ret63,
        "risk_on": risk_on,
        "regime_label": "RISK_ON" if risk_on else "RISK_OFF",
        "risk_regime_mode": str(getattr(cfg, "risk_regime_mode", "normal") or "normal"),
    }


def load_stored_signal_diagnosis(out_dir: Path) -> Dict[str, Any]:
    """Read regime + R3 selection diagnostics from latest signal export."""
    out_dir = Path(out_dir)
    signals_path = out_dir / "latest_signals.csv"
    if not signals_path.is_file():
        return {"available": False}
    try:
        df = pd.read_csv(signals_path)
    except Exception:
        return {"available": False}
    if df.empty:
        return {"available": False}

    def _first(col: str, default: Any = None) -> Any:
        if col not in df.columns:
            return default
        val = df[col].iloc[0]
        if pd.isna(val):
            return default
        return val

    risk_on_raw = _first("risk_on")
    if isinstance(risk_on_raw, str):
        risk_on = risk_on_raw.strip().lower() in {"true", "1", "yes", "y", "j", "ja"}
    else:
        risk_on = bool(risk_on_raw) if risk_on_raw is not None else None

    selected = df[pd.to_numeric(df.get("target_weight", 0), errors="coerce").fillna(0.0) > 0]
    rescued = 0
    if "rescued_by_momentum" in df.columns:
        rescued = int(pd.to_numeric(selected.get("rescued_by_momentum"), errors="coerce").fillna(0).astype(bool).sum())
    elif "eligibility_reason" in df.columns:
        rescued = int((selected["eligibility_reason"] == "risk_off_momentum_rescue").sum())

    return {
        "available": True,
        "signal_date": str(_first("signal_date", "")),
        "risk_on": risk_on,
        "regime_label": "RISK_ON" if risk_on else ("RISK_OFF" if risk_on is False else "UNKNOWN"),
        "target_exposure": _first("target_exposure"),
        "risk_off_selection_mode": str(_first("risk_off_selection_mode", "") or ""),
        "risk_off_gate_mode": str(_first("risk_off_gate_mode", "") or ""),
        "risk_off_momentum_rescue_quantile": _first("risk_off_momentum_rescue_quantile"),
        "n_selected": int(len(selected)),
        "n_rescued_by_momentum": rescued,
        "n_eligible_candidates": _first("n_eligible_candidates"),
    }


def compute_regime_feedback(out_dir: Path) -> Dict[str, Any]:
    """Summarize mature prediction outcomes split by risk_on regime."""
    try:
        from aa_prediction_outcomes import compute_feedback_metrics, load_ledger
    except Exception:
        return {}
    ledger = load_ledger(out_dir)
    if ledger.empty or "risk_on" not in ledger.columns:
        return {"available": False}
    mature = ledger[ledger["status"] == "mature"].copy()
    if mature.empty:
        return {"available": False, "n_mature": 0}
    out: Dict[str, Any] = {"available": True, "n_mature": int(len(mature))}
    for regime_key, flag in (("risk_on", True), ("risk_off", False)):
        sub = mature[mature["risk_on"].fillna(False).astype(bool) == flag]
        if sub.empty:
            out[regime_key] = {"n": 0}
            continue
        metrics = compute_feedback_metrics(sub)
        out[regime_key] = {
            "n": int(len(sub)),
            "signed_hit_rate": metrics.get("signed_hit_rate"),
            "mae": metrics.get("mae"),
            "selected_signed_hit_rate": metrics.get("selected_signed_hit_rate"),
        }
    return out


def build_refinement_hints(
    *,
    live: Dict[str, Any],
    stored: Dict[str, Any],
    feedback: Dict[str, Any],
    price_latest: Optional[str],
    signal_date: Optional[str],
) -> List[str]:
    hints: List[str] = []
    live_ro = live.get("risk_on")
    stored_ro = stored.get("risk_on") if stored.get("available") else None
    if live_ro is not None and stored_ro is not None and live_ro != stored_ro:
        hints.append(
            "Regime-Drift: frische Tagesdaten ({live}) weichen vom gespeicherten Signal ({stored}) ab — "
            "Signal-Refresh empfohlen.".format(
                live=live.get("regime_label", "?"),
                stored=stored.get("regime_label", "?"),
            )
        )
    if price_latest and signal_date and price_latest > signal_date:
        hints.append(
            f"Preis-Stand ({price_latest}) ist neuer als Signal-Datum ({signal_date}) — Prognose mit Tagesdaten verfeinern."
        )
    if feedback.get("available"):
        ro = feedback.get("risk_on") or {}
        rf = feedback.get("risk_off") or {}
        ro_hr = ro.get("selected_signed_hit_rate")
        rf_hr = rf.get("selected_signed_hit_rate")
        if ro_hr is not None and rf_hr is not None and rf_hr < ro_hr - 0.05:
            hints.append(
                "Feedback: Risk-off-Trefferquote unter Risk-on — R3 Momentum-Rescue-Gate weiter beobachten."
            )
        elif ro_hr is not None and rf_hr is not None and rf_hr >= ro_hr:
            hints.append(
                "Feedback: Risk-off-Selektion (R3) trifft mindestens so gut wie Risk-on — Champion-Logik bestätigt."
            )
    if not hints:
        hints.append("R3-Diagnose konsistent mit Tagesdaten — Prognose-Feedback wird fortgeführt.")
    return hints


@dataclass
class R3DailyDiagnosisReport:
    ok: bool = False
    regime_match: Optional[bool] = None
    live_regime: Dict[str, Any] = field(default_factory=dict)
    stored_signal: Dict[str, Any] = field(default_factory=dict)
    feedback_by_regime: Dict[str, Any] = field(default_factory=dict)
    refinement_hints: List[str] = field(default_factory=list)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    manifest_path: str = ""
    messages: List[str] = field(default_factory=list)


def verify_r3_diagnosis_against_daily_data(
    root: Path,
    env: Mapping[str, str],
    *,
    update_feedback: bool = True,
    log_print: bool = False,
) -> R3DailyDiagnosisReport:
    """Cross-check R3 regime/selection with fresh daily OHLCV and optional outcome feedback."""
    root = Path(root)
    report = R3DailyDiagnosisReport()
    out_dir = _out_dir(root, env)
    benchmark = str(env.get("AA_BENCHMARK", "SPY") or "SPY").upper().strip()

    try:
        import sys

        from aa_config import BacktestConfig, parse_args
        from aa_config_env import build_backtest_argv

        old_argv = sys.argv
        try:
            sys.argv = build_backtest_argv(dict(env))
            cfg = BacktestConfig.from_args(parse_args())
        finally:
            sys.argv = old_argv
    except Exception as exc:
        report.messages.append(f"[WARN] R3-Diagnose: Config nicht geladen ({exc})")
        return report

    report.config_snapshot = {
        "variant_profile": str(getattr(cfg, "variant_id", "") or env.get("AA_VARIANT_ID", "")),
        "risk_off_selection_mode": str(getattr(cfg, "risk_off_selection_mode", "")),
        "risk_off_gate_mode": str(getattr(cfg, "risk_off_gate_mode", "")),
        "risk_off_momentum_weight": float(getattr(cfg, "risk_off_momentum_weight", 0.0) or 0.0),
        "risk_off_momentum_rescue_quantile": float(getattr(cfg, "risk_off_momentum_rescue_quantile", 0.0) or 0.0),
        "benchmark": benchmark,
    }

    bench_close, price_latest = load_benchmark_close_series(out_dir, benchmark)
    if bench_close is None or bench_close.empty:
        report.messages.append("[WARN] R3-Diagnose: Benchmark-Preise fehlen — zuerst Live-Tagesdaten syncen.")
        payload = _build_manifest(report, price_latest=price_latest, signal_date=None)
        report.manifest_path = str(write_r3_diagnosis_manifest(out_dir, payload))
        return report

    report.live_regime = compute_live_market_regime(bench_close, cfg)
    report.stored_signal = load_stored_signal_diagnosis(out_dir)

    if update_feedback:
        try:
            from aa_prediction_outcomes import update_prediction_outcomes

            fb = update_prediction_outcomes(out_dir)
            report.messages.append(
                f"[OK] Prognose-Feedback: +{fb.get('added', 0)} neu, {fb.get('matured', 0)} reif"
            )
        except Exception as exc:
            report.messages.append(f"[INFO] Prognose-Feedback übersprungen: {exc}")

    report.feedback_by_regime = compute_regime_feedback(out_dir)

    stored_ro = report.stored_signal.get("risk_on") if report.stored_signal.get("available") else None
    live_ro = report.live_regime.get("risk_on")
    if stored_ro is not None and live_ro is not None:
        report.regime_match = bool(stored_ro == live_ro)
    else:
        report.regime_match = None

    signal_date = str(report.stored_signal.get("signal_date") or "")
    report.refinement_hints = build_refinement_hints(
        live=report.live_regime,
        stored=report.stored_signal,
        feedback=report.feedback_by_regime,
        price_latest=price_latest,
        signal_date=signal_date or None,
    )

    report.ok = report.live_regime.get("risk_on") is not None
    if report.regime_match is True:
        report.messages.append(
            f"[OK] R3-Diagnose: Regime {report.live_regime.get('regime_label')} bestätigt "
            f"(SPY Stand {report.live_regime.get('as_of_date')})"
        )
    elif report.regime_match is False:
        report.messages.append(
            f"[WARN] R3-Diagnose: Regime-Drift — live {report.live_regime.get('regime_label')}, "
            f"Signal {report.stored_signal.get('regime_label', '?')}"
        )
    else:
        report.messages.append(
            f"[INFO] R3-Diagnose: Live-Regime {report.live_regime.get('regime_label')} "
            f"(kein gespeichertes Signal zum Vergleich)"
        )

    payload = _build_manifest(
        report,
        price_latest=price_latest,
        signal_date=signal_date or None,
    )
    report.manifest_path = str(write_r3_diagnosis_manifest(out_dir, payload))

    if log_print:
        for line in report.messages:
            print(line)
        for hint in report.refinement_hints:
            print(f"  -> {hint}")

    return report


def _build_manifest(
    report: R3DailyDiagnosisReport,
    *,
    price_latest: Optional[str],
    signal_date: Optional[str],
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "diagnosed_at_utc": _utc_now(),
        "purpose": "r3_daily_diagnosis_vs_tagesdaten",
        "ok": report.ok,
        "regime_match": report.regime_match,
        "price_latest": price_latest,
        "signal_date": signal_date,
        "live_regime": report.live_regime,
        "stored_signal": report.stored_signal,
        "feedback_by_regime": report.feedback_by_regime,
        "refinement_hints": report.refinement_hints,
        "config_snapshot": report.config_snapshot,
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    try:
        import numpy as np

        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, (np.bool_,)):
            return bool(value)
    except Exception:
        pass
    return str(value)


def write_r3_diagnosis_manifest(out_dir: Path, payload: Dict[str, Any]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(out_dir / R3_DIAGNOSIS_FILE, _json_safe(payload))


def read_r3_diagnosis_manifest(out_dir: Path) -> Dict[str, Any]:
    path = Path(out_dir) / R3_DIAGNOSIS_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def format_r3_diagnosis_block(doc: Optional[Dict[str, Any]] = None) -> str:
    """Human-readable R3 diagnosis for cockpit / model status."""
    doc = doc or {}
    if not doc:
        return ""
    live = doc.get("live_regime") or {}
    stored = doc.get("stored_signal") or {}
    lines = [
        "R3-Diagnose (Tagesdaten)",
        f"  Live-Regime: {live.get('regime_label', '—')} "
        f"(SPY {live.get('as_of_date', '—')}, ret63={_fmt_pct(live.get('market_ret_63'))})",
    ]
    if stored.get("available"):
        match = doc.get("regime_match")
        match_txt = "ja" if match is True else ("nein — Refresh empfohlen" if match is False else "n/a")
        lines.append(f"  Signal-Regime: {stored.get('regime_label', '—')} ({stored.get('signal_date', '—')})")
        lines.append(f"  Abgleich: {match_txt}")
        if stored.get("risk_off_gate_mode"):
            lines.append(
                f"  R3 Gate: {stored.get('risk_off_gate_mode')} | "
                f"Rescue q={stored.get('risk_off_momentum_rescue_quantile', '—')} | "
                f"Rescue-Positionen: {stored.get('n_rescued_by_momentum', 0)}"
            )
    fb = doc.get("feedback_by_regime") or {}
    if fb.get("available"):
        ro = fb.get("risk_on") or {}
        rf = fb.get("risk_off") or {}
        lines.append(
            f"  Feedback reif: {fb.get('n_mature', 0)} | "
            f"Risk-on Hit: {_fmt_pct(ro.get('selected_signed_hit_rate'))} | "
            f"Risk-off Hit: {_fmt_pct(rf.get('selected_signed_hit_rate'))}"
        )
    for hint in doc.get("refinement_hints") or []:
        lines.append(f"  -> {hint}")
    return "\n".join(lines)


def _fmt_pct(val: Any) -> str:
    if val is None:
        return "—"
    try:
        f = float(val)
        if 0 <= f <= 1:
            return f"{f:.1%}"
        return f"{f:.4f}"
    except Exception:
        return str(val)
