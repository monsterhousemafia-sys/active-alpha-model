"""OS-facing prediction profile, EOD switch, and variable budget from control/prediction_operations.json."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from zoneinfo import ZoneInfo

OPS_REL = Path("control/prediction_operations.json")
READINESS_REL = Path("control/prediction_readiness.json")
EOD_STATE_REL = Path("control/prediction_eod_switch_state.json")
DEFAULT_PROFILE = "daily_alpha_h1"
DEFAULT_BUFFER_PCT = 5.0
DEFAULT_EOD_CET = "22:15"
BERLIN = ZoneInfo("Europe/Berlin")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_prediction_operations(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / OPS_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


def active_profile(root: Path) -> str:
    ops = load_prediction_operations(root)
    return str(ops.get("active_profile") or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE


def profile_variant_key(root: Path, profile: Optional[str] = None) -> str:
    ops = load_prediction_operations(root)
    prof = profile or str(ops.get("active_profile") or DEFAULT_PROFILE)
    profiles = ops.get("profiles") or {}
    row = profiles.get(prof) or {}
    key = str(row.get("variant_key") or "").strip()
    if key:
        return key
    try:
        from tools.prediction_profiles import list_profiles

        return list_profiles().get(prof, prof)
    except Exception:
        return prof


def resolve_operational_signal_id(root: Path) -> str:
    """Variant key used for live signal generation (OS operational identity)."""
    return profile_variant_key(root)


def budget_config(root: Path) -> Dict[str, Any]:
    ops = load_prediction_operations(root)
    raw = dict(ops.get("budget") or {})
    use_full = bool(raw.get("use_full_free_cash", True))
    buf = float(raw.get("cash_buffer_pct") if raw.get("cash_buffer_pct") is not None else DEFAULT_BUFFER_PCT)
    if use_full:
        buf = 0.0
    planning_capital: Optional[float] = None
    if raw.get("planning_capital_eur") is not None:
        try:
            planning_capital = round(max(0.0, float(raw["planning_capital_eur"])), 2)
        except (TypeError, ValueError):
            planning_capital = None
    return {
        "mode": str(raw.get("mode") or "variable_free_cash"),
        "source": str(raw.get("source") or "T212_availableToTrade"),
        "cash_buffer_pct": buf,
        "min_position_eur": float(raw.get("min_position_eur") or 0),
        "exclude_symbols": [str(s).upper() for s in (raw.get("exclude_symbols") or []) if str(s).strip()],
        "use_full_free_cash": bool(raw.get("use_full_free_cash", True)),
        "planning_capital_eur": planning_capital,
        "note_de": str(raw.get("note_de") or ""),
    }


def fixed_preview_capital_eur(root: Path) -> Optional[float]:
    """Fixed preview capital when budget.mode == fixed_preview."""
    bcfg = budget_config(root)
    if bcfg.get("mode") != "fixed_preview":
        return None
    return bcfg.get("planning_capital_eur")


def resolve_planning_basis_eur(
    root: Path,
    live_planning_cash_eur: float | None,
) -> Dict[str, Any]:
    """
    Planungs-Kapitalbasis für Modell-Skalierung und Prognose.
    fixed_preview überschreibt Live-T212; Orders nutzen weiterhin resolve_planning_cash_eur.
    """
    root = Path(root)
    bcfg = budget_config(root)
    live: Optional[float] = None
    if live_planning_cash_eur is not None:
        try:
            live = round(max(0.0, float(live_planning_cash_eur)), 2)
        except (TypeError, ValueError):
            live = None

    fixed = fixed_preview_capital_eur(root)
    if fixed is not None:
        buffer_pct = float(bcfg.get("cash_buffer_pct", 0.0))
        planning = fixed
        investable = round(planning * (1.0 - buffer_pct / 100.0), 2)
        return {
            "planning_cash_eur": planning,
            "investable_eur": investable,
            "budget_mode": "fixed_preview",
            "budget_source": "fixed_preview",
            "live_planning_cash_eur": live,
            "planning_override": True,
        }

    planning = live
    investable: Optional[float] = None
    if planning is not None:
        from analytics.r3_closed_loop import resolve_r3_investable_eur

        investable = resolve_r3_investable_eur(root, planning)
    return {
        "planning_cash_eur": planning,
        "investable_eur": investable,
        "budget_mode": bcfg.get("mode"),
        "budget_source": bcfg.get("source"),
        "live_planning_cash_eur": live,
        "planning_override": False,
    }


def schedule_config(root: Path) -> Dict[str, Any]:
    ops = load_prediction_operations(root)
    sched = dict(ops.get("schedule") or {})
    return {
        "switch_at": str(sched.get("switch_at") or "eod"),
        "eod_local_time_cet": str(sched.get("eod_local_time_cet") or DEFAULT_EOD_CET),
        "eod_after_us_close": bool(sched.get("eod_after_us_close", True)),
        "windows_command": str(sched.get("windows_command") or "python tools/run_tomorrow_prediction.py"),
        "wsl_command": str(sched.get("wsl_command") or "bash tools/wsl_conductor.sh predict"),
    }


def apply_prediction_profile_to_env(root: Path, env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Merge active prediction profile into AA_* env (signal/backtest)."""
    merged = dict(env or {})
    prof = active_profile(root)
    try:
        from tools.prediction_profiles import profile_env

        merged.update(profile_env(prof))
    except Exception:
        merged.setdefault("AA_PREDICTION_PROFILE", prof)
        merged.setdefault("AA_VARIANT_ID", resolve_operational_signal_id(root))
    merged.setdefault("AA_PREDICTION_PROFILE", prof)
    return merged


def load_prediction_readiness(root: Path) -> Dict[str, Any]:
    path = Path(root) / READINESS_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _parse_eod_time_cet(value: str) -> time:
    parts = str(value or DEFAULT_EOD_CET).strip().split(":")
    hour = int(parts[0]) if parts else 22
    minute = int(parts[1]) if len(parts) > 1 else 15
    return time(hour=hour, minute=minute)


def eod_switch_due(root: Path, *, now: Optional[datetime] = None) -> bool:
    """True when local CET passed EOD cutoff and today's switch not yet recorded."""
    sched = schedule_config(root)
    if str(sched.get("switch_at") or "").lower() != "eod":
        return False
    now_local = (now or datetime.now(BERLIN)).astimezone(BERLIN)
    cutoff = _parse_eod_time_cet(str(sched.get("eod_local_time_cet") or DEFAULT_EOD_CET))
    if now_local.time() < cutoff:
        return False
    state_path = Path(root) / EOD_STATE_REL
    today = now_local.date().isoformat()
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if str(state.get("last_switch_local_date") or "") == today and state.get("ok"):
                return False
        except (json.JSONDecodeError, OSError):
            pass
    readiness = load_prediction_readiness(root)
    gen = str(readiness.get("generated_at_utc") or "")
    if gen:
        try:
            gen_dt = datetime.fromisoformat(gen.replace("Z", "+00:00")).astimezone(BERLIN)
            if gen_dt.date().isoformat() == today and readiness.get("ok"):
                return False
        except ValueError:
            pass
    return True


def _write_eod_state(root: Path, payload: Dict[str, Any]) -> None:
    from aa_safe_io import atomic_write_json

    atomic_write_json(Path(root) / EOD_STATE_REL, payload)


def run_eod_prediction_switch(root: Path, *, force: bool = False) -> Dict[str, Any]:
    """Refresh prices + ML signal for tomorrow (profile-driven)."""
    root = Path(root)
    if not force and not eod_switch_due(root):
        return {
            "ok": True,
            "skipped": True,
            "reason": "eod_not_due",
            "profile": active_profile(root),
            "message_de": "EOD-Umstellung noch nicht fällig (nach 22:15 CET oder bereits gelaufen).",
        }
    try:
        from tools.run_tomorrow_prediction import run_prediction

        result = run_prediction(root, force_prices=True, allow_fallback=True)
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "last_attempt_utc": _utc_now(),
            "last_switch_local_date": datetime.now(BERLIN).date().isoformat(),
            "ok": False,
            "profile": active_profile(root),
            "error": str(exc)[:300],
        }
        _write_eod_state(root, payload)
        return {
            "ok": False,
            "skipped": False,
            "profile": active_profile(root),
            "message_de": f"EOD-Signal fehlgeschlagen: {exc}",
            "error": str(exc)[:300],
        }

    ok = bool(result.get("ok"))
    payload = {
        "schema_version": 1,
        "last_attempt_utc": _utc_now(),
        "last_switch_local_date": datetime.now(BERLIN).date().isoformat(),
        "ok": ok,
        "profile": str(result.get("profile_used") or active_profile(root)),
        "signal_date": result.get("signal_date"),
        "prediction_readiness_ref": str(READINESS_REL),
    }
    _write_eod_state(root, payload)
    msg = (
        f"EOD-Umstellung OK — Profil {payload['profile']}, Signal {result.get('signal_date') or '—'}."
        if ok
        else f"EOD-Umstellung fehlgeschlagen — {result.get('last_error') or 'unbekannt'}"
    )
    return {
        "ok": ok,
        "skipped": False,
        "profile": payload["profile"],
        "signal_date": result.get("signal_date"),
        "message_de": msg,
        "result": result,
    }


def maybe_run_eod_prediction_switch(root: Path, *, force: bool = False) -> Dict[str, Any]:
    """Non-blocking hook for OS startup / dashboard timer."""
    sched = schedule_config(root)
    if str(sched.get("switch_at") or "").lower() != "eod" and not force:
        return {"ok": True, "skipped": True, "reason": "switch_at_not_eod"}
    return run_eod_prediction_switch(root, force=force)


def orders_config(root: Path) -> Dict[str, Any]:
    ops = load_prediction_operations(root)
    raw = dict(ops.get("orders") or {})
    return {
        "require_prediction_ready": bool(raw.get("require_prediction_ready", True)),
        "auto_run_predict_before_orders": bool(raw.get("auto_run_predict_before_orders", True)),
        "auto_run_predict_on_scheduled_mark": bool(raw.get("auto_run_predict_on_scheduled_mark", True)),
    }


PORTFOLIO_REL = Path("model_output_sp500_pit_t212") / "latest_target_portfolio.csv"


def evaluate_prediction_readiness_for_orders(
    root: Path,
    *,
    readiness: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Hard gate: predict must be OK before any live order path proceeds."""
    root = Path(root)
    ocfg = orders_config(root)
    if not ocfg.get("require_prediction_ready", True):
        return {"ok": True, "skipped": True, "reason": "require_prediction_ready=false"}

    blockers: List[str] = []
    readiness = readiness if readiness is not None else load_prediction_readiness(root)
    active = active_profile(root)
    signal_date: Optional[str] = None
    profile_used = str(readiness.get("profile_used") or "")
    predict_ok = bool(readiness.get("ok")) or (
        bool(readiness.get("profile_used")) and bool(readiness.get("top_picks"))
    )

    if not readiness:
        blockers.append("PREDICTION_READINESS_MISSING")
    elif not predict_ok:
        existing = [str(b) for b in (readiness.get("blockers") or []) if b]
        stale_recheck = {"PRICE_NOT_CURRENT", "SIGNAL_NOT_CURRENT"}
        if existing:
            blockers.extend(b for b in existing if b not in stale_recheck)
        else:
            err = str(readiness.get("last_error") or "predict failed")
            blockers.append(f"PREDICTION_NOT_OK ({err[:80]})")
        signal_date = str(readiness.get("signal_date") or "")[:10] or None
    else:
        signal_date = str(readiness.get("signal_date") or "")[:10] or None
        if profile_used and profile_used != active:
            blockers.append(f"PREDICTION_PROFILE_MISMATCH ({profile_used} != {active})")
        picks = readiness.get("top_picks") or []
        if not picks:
            blockers.append("PREDICTION_PICKS_EMPTY")

    portfolio = root / PORTFOLIO_REL
    if not portfolio.is_file() or portfolio.stat().st_size <= 0:
        blockers.append("PORTFOLIO_CSV_MISSING")

    signal_current = False
    price_current = False
    price_latest: Optional[str] = None
    try:
        from aa_config_env import load_aa_env
        from aa_data_freshness import assess_daily_data, is_market_data_current, is_signal_current, read_signal_date

        env = load_aa_env(root)
        env.setdefault("AA_BACKTEST_OUT_DIR", "model_output_sp500_pit_t212")
        data = assess_daily_data(root, env)
        sig = data.signal_date or read_signal_date(
            root / str(env.get("AA_BACKTEST_OUT_DIR", "model_output_sp500_pit_t212"))
        )
        signal_current = bool(data.signal_current or is_signal_current(sig))
        price_current = bool(data.price_current or is_market_data_current(data.price_latest))
        if data.price_latest is not None:
            price_latest = data.price_latest.isoformat()
        if sig is not None:
            signal_date = sig.isoformat()
        if not signal_current:
            blockers.append("SIGNAL_NOT_CURRENT")
        if not price_current:
            blockers.append("PRICE_NOT_CURRENT")
    except Exception as exc:
        blockers.append(f"SIGNAL_CHECK_FAILED ({str(exc)[:60]})")

    try:
        from analytics.live_profile_governance import experimental_profile_blockers

        blockers.extend(experimental_profile_blockers(root))
    except Exception:
        pass
    blockers = sorted(set(blockers))

    ok = len(blockers) == 0
    msg = (
        f"Predict bereit — Profil {profile_used or active}, Signal {signal_date or '—'}."
        if ok
        else "Kein gültiges Predict — zuerst Signal (predict) ausführen, dann Orders."
    )
    return {
        "ok": ok,
        "blockers": blockers,
        "message_de": msg,
        "profile_used": profile_used or active,
        "active_profile": active,
        "signal_date": signal_date,
        "signal_current": signal_current,
        "price_current": price_current,
        "price_latest": price_latest,
        "prediction_readiness_ok": bool(readiness.get("ok")) if readiness else False,
        "generated_at_utc": readiness.get("generated_at_utc") if readiness else None,
    }


def ensure_prediction_before_orders(
    root: Path,
    *,
    auto_run: Optional[bool] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Ensure predict is ready; optionally auto-run run_tomorrow_prediction first."""
    root = Path(root)
    ocfg = orders_config(root)
    if auto_run is None:
        auto_run = bool(ocfg.get("auto_run_predict_before_orders", True))

    gate = evaluate_prediction_readiness_for_orders(root)
    if gate.get("skipped"):
        return gate
    if gate.get("ok") and not force_refresh:
        return {**gate, "auto_run": False, "already_ready": True}

    if not auto_run:
        return {**gate, "auto_run": False, "message_de": gate.get("message_de")}

    try:
        from tools.run_tomorrow_prediction import run_prediction

        predict_result = run_prediction(root, force_prices=True, allow_fallback=True)
    except Exception as exc:
        return {
            **evaluate_prediction_readiness_for_orders(root),
            "auto_run": True,
            "predict_ok": False,
            "predict_error": str(exc)[:300],
            "message_de": f"Predict fehlgeschlagen: {exc}",
        }

    gate = evaluate_prediction_readiness_for_orders(root)
    return {
        **gate,
        "auto_run": True,
        "predict_ok": bool(predict_result.get("ok")),
        "predict_result": {
            "profile_used": predict_result.get("profile_used"),
            "signal_date": predict_result.get("signal_date"),
            "ok": predict_result.get("ok"),
        },
    }


def plan_metadata(root: Path, *, available_cash_eur: float, investable_eur: float) -> Dict[str, Any]:
    """Dashboard fields: profile, budget mode, EOD status."""
    ops = load_prediction_operations(root)
    bcfg = budget_config(root)
    sched = schedule_config(root)
    readiness = load_prediction_readiness(root)
    h1_meta: Dict[str, Any] = {}
    try:
        from analytics.live_profile_governance import h1_model_evidence

        h1 = h1_model_evidence(root)
        h1_meta = {
            "h1_status": h1["h1_status"],
            "run_dir": h1.get("run_dir"),
            "sealed": h1["sealed"],
            "pass_full_seal": h1["pass_full_seal"],
            "operational_ok": h1["operational_ok"],
            "metrics_strategy": h1.get("metrics_strategy"),
        }
    except Exception:
        pass
    return {
        "prediction_profile": active_profile(root),
        "operational_signal_id": resolve_operational_signal_id(root),
        "governance_champion": str(ops.get("governance_champion") or ""),
        "budget_mode": bcfg["mode"],
        "budget_source": "fixed_preview" if bcfg["mode"] == "fixed_preview" else bcfg["source"],
        "planning_capital_eur": bcfg.get("planning_capital_eur"),
        "planning_override": bcfg["mode"] == "fixed_preview" and bcfg.get("planning_capital_eur") is not None,
        "available_cash_eur": round(float(available_cash_eur), 2),
        "investable_eur": round(float(investable_eur), 2),
        "cash_buffer_pct": bcfg["cash_buffer_pct"],
        "eod_switch_at": sched["switch_at"],
        "eod_local_time_cet": sched["eod_local_time_cet"],
        "eod_due_now": eod_switch_due(root),
        "prediction_readiness_ok": bool(readiness.get("ok")),
        "prediction_generated_at_utc": readiness.get("generated_at_utc"),
        "prediction_order_gate": evaluate_prediction_readiness_for_orders(root),
        "h1_evidence": h1_meta or None,
    }


def format_plan_summary_de(root: Path, *, n_symbols: int, investable_eur: float, cash_eur: float) -> str:
    meta = plan_metadata(root, available_cash_eur=cash_eur, investable_eur=investable_eur)
    prof = meta["prediction_profile"]
    sig = meta["operational_signal_id"]
    buf = meta["cash_buffer_pct"]
    eod = meta["eod_local_time_cet"]
    cash_part = (
        f"volles T212-Guthaben {cash_eur:.0f} €"
        if buf <= 0
        else f"({buf:.0f} % Puffer auf {cash_eur:.0f} € frei handelbar laut T212)"
    )
    return (
        f"Profil {prof} ({sig}): {n_symbols} Positionen auf {investable_eur:.0f} € investierbar "
        f"({cash_part}). Umstellung zum Tagesende ab {eod} CET."
    )
