"""Live trading operations — same rhythm as Paper (mark / rebalance / signal), T212 execution."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aa_safe_io import atomic_write_json

_STATE_REL = Path("live_pilot/confirmed_execution/live_trading_state.json")
_STATUS_REL = Path("live_pilot/confirmed_execution/live_trading_next_rebalance.json")
_EVIDENCE_REL = Path("evidence/live_trading_operations_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today_iso() -> str:
    return date.today().isoformat()


def default_policy() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "enabled": True,
        "auto_enable_on_startup": True,
        "rebalance_every_trading_days": 1,
        "daily_mark_enabled": True,
        "run_signal_before_rebalance": True,
        "auto_execute_at_us_open": True,
        "relaxed_order_preflight": True,
        "min_trade_eur": 5.0,
        "min_weight_gap_pct": 0.25,
        "max_rebalance_orders": 40,
        "auto_enqueue_on_rebalance_due": True,
        "order_execution_type": "limit",
        "limit_time_validity": "DAY",
        "max_orders_per_day": 0,
    }


def normalize_execution_result(exec_result: Dict[str, Any]) -> Dict[str, Any]:
    """Clarify enqueue-only vs live T212 POST for UI and evidence."""
    out = dict(exec_result)
    executed = int(out.get("executed") or 0)
    enqueued = int(out.get("enqueued") or 0)
    fallback = str(out.get("fallback") or "")
    mode = str(out.get("mode") or "")
    sent = executed > 0
    if fallback or mode.startswith("deferred"):
        if executed == 0 and (enqueued > 0 or fallback):
            sent = False
    out["submitted_count"] = executed
    out["enqueued_count"] = enqueued
    out["sent_to_t212"] = sent
    if not sent and (enqueued > 0 or fallback):
        out["enqueue_only"] = True
        if out.get("ok") and executed == 0:
            out["ok"] = False
        if not str(out.get("message_de") or "").startswith("Nicht an T212 gesendet"):
            prefix = (
                "Nicht an T212 gesendet — nur vorgemerkt. "
                if enqueued or fallback
                else ""
            )
            out["message_de"] = f"{prefix}{out.get('message_de', '')}".strip()
    return out


def load_policy(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import policy_section

    pol = policy_section(Path(root), "live_trading")
    if not pol.get("enabled") and pol.get("schema_version") is None:
        pol = policy_section(Path(root), "walkforward_mirror")
    merged = {**default_policy(), **pol}
    return _apply_daily_profile_rebalance_policy(root, merged)


def _apply_daily_profile_rebalance_policy(root: Path, pol: Dict[str, Any]) -> Dict[str, Any]:
    """Tighter min-weight gap for daily_alpha_h1 to cut turnover / FX drag."""
    try:
        from analytics.prediction_operations import load_prediction_operations

        ops = load_prediction_operations(root)
        if str(ops.get("active_profile") or "") != "daily_alpha_h1":
            return pol
        rebal = ops.get("rebalance") or {}
        budget = ops.get("budget") or {}
        out = dict(pol)
        if rebal.get("min_weight_gap_pct") is not None:
            out["min_weight_gap_pct"] = float(rebal["min_weight_gap_pct"])
        if budget.get("min_position_eur") is not None:
            out["min_trade_eur"] = max(
                float(out.get("min_trade_eur") or 5.0),
                float(budget["min_position_eur"]),
            )
        return out
    except Exception:
        return pol


def _state_path(root: Path) -> Path:
    p = Path(root) / _STATE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_state(root: Path) -> Dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        return {
            "schema_version": 1,
            "mark_dates": [],
            "last_rebalance_date": "",
            "recorded_trading_days_since_rebalance": 0,
            "last_signal_update_utc": "",
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "mark_dates": [], "recorded_trading_days_since_rebalance": 0}


def save_state(root: Path, state: Dict[str, Any]) -> Path:
    state["updated_at_utc"] = _utc_now()
    return atomic_write_json(_state_path(root), state)


def write_next_rebalance_status(root: Path, status: Dict[str, Any]) -> Path:
    path = Path(root) / _STATUS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Active Alpha Live Trading - Next Rebalance",
        "========================================",
        "",
        f"rebalance_every_recorded_trading_days: {status.get('rebalance_every_trading_days')}",
        f"last_rebalance_date: {status.get('last_rebalance_date')}",
        f"recorded_mark_days_since_rebalance: {status.get('recorded_trading_days_since_rebalance')}",
        f"days_remaining_until_due: {status.get('days_remaining')}",
        f"is_due: {status.get('is_due')}",
        f"recommendation: {status.get('recommendation')}",
        "",
        "Operational rule (Paper-parity)",
        "---------------------------",
        "- MARK_TO_MARKET_ONLY: daily sync + quotes only (1_live_daily_sync.bat).",
        "- REBALANCE_DUE: run signal update then live rebalance (2_live_rebalance_when_due.bat).",
        "- Counter = app-run days since last rebalance, not exchange calendar.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def rebalance_status(root: Path, *, pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pol = pol or load_policy(root)
    every = int(max(1, pol.get("rebalance_every_trading_days") or 1))
    state = load_state(root)
    recorded = int(state.get("recorded_trading_days_since_rebalance") or 0)
    last_rb = str(state.get("last_rebalance_date") or "")[:10]
    remaining = max(0, every - recorded)
    due = recorded >= every
    if not state.get("mark_dates"):
        rec = "REBALANCE_DUE_NO_HISTORY"
        due = True
    else:
        rec = "REBALANCE_DUE" if due else "MARK_TO_MARKET_ONLY"
    status = {
        "rebalance_every_trading_days": every,
        "last_rebalance_date": last_rb or "-",
        "recorded_trading_days_since_rebalance": recorded,
        "days_remaining": remaining,
        "is_due": bool(due),
        "recommendation": rec,
        "last_mark_date": str((state.get("mark_dates") or [""])[-1])[:10] if state.get("mark_dates") else "-",
        "summary_de": (
            f"Live-Trading: Rebalance fällig ({recorded}/{every} Mark-Tage)."
            if due
            else f"Live-Trading: nur Mark — Rebalance in {remaining} Tag(en) ({recorded}/{every})."
        ),
    }
    write_next_rebalance_status(root, status)
    return status


def record_daily_mark(root: Path, *, pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pol = pol or load_policy(root)
    if not pol.get("daily_mark_enabled", True):
        return {"recorded": False, "reason": "DISABLED"}
    state = load_state(root)
    today = _today_iso()
    marks = [str(d)[:10] for d in (state.get("mark_dates") or [])]
    if today in marks:
        return {"recorded": False, "reason": "ALREADY_MARKED_TODAY", "today": today}
    marks.append(today)
    state["mark_dates"] = marks[-400:]
    state["recorded_trading_days_since_rebalance"] = int(state.get("recorded_trading_days_since_rebalance") or 0) + 1
    save_state(root, state)
    return {"recorded": True, "today": today, "status": rebalance_status(root, pol=pol)}


def note_rebalance_completed(root: Path) -> Dict[str, Any]:
    state = load_state(root)
    state["last_rebalance_date"] = _today_iso()
    state["recorded_trading_days_since_rebalance"] = 0
    save_state(root, state)
    return rebalance_status(root)


def _venv_python(root: Path) -> Path:
    from aa_paths import resolve_venv_python

    return resolve_venv_python(root)


def _signal_env(root: Path) -> Dict[str, str]:
    from aa_config_env import load_aa_env, resolve_launcher_env
    from aa_frozen import apply_frozen_env_defaults, is_frozen_exe
    from analytics.prediction_operations import apply_prediction_profile_to_env

    frozen = is_frozen_exe()
    env = resolve_launcher_env(root, frozen=frozen) if frozen else dict(load_aa_env(root))
    env["AA_RUN_MODE"] = "signal"
    env["AA_NONINTERACTIVE"] = "1"
    env["AA_PLAIN_PROGRESS"] = "1"
    env["AA_NO_GUI"] = "1"
    env["AA_GUI"] = "0"
    env = apply_frozen_env_defaults(env, force=frozen, root=root)
    env = apply_prediction_profile_to_env(root, env)
    out = env.get("AA_PAPER_MODEL_OUT_DIR") or env.get("AA_BACKTEST_OUT_DIR") or "model_output_sp500_pit_t212"
    env["AA_BACKTEST_OUT_DIR"] = out
    env["AA_PAPER_MODEL_OUT_DIR"] = out
    env.setdefault("AA_REUSE_FEATURE_CACHE", "1")
    env.setdefault("AA_SKIP_DOWNLOAD_IF_CACHED", "1")
    env.setdefault("AA_REUSE_PREDICTION_CACHE", "1")
    env.setdefault("AA_PARALLEL_BACKTEST_BACKEND", "thread")
    return env


def _run_signal_subprocess(
    root: Path,
    env: Mapping[str, str],
    *,
    timeout_s: int,
    log: Optional[List[str]] = None,
) -> tuple[bool, Optional[subprocess.CompletedProcess], str]:
    """Paper-parity signal via repo .venv (required for Marktanalyse.exe — ML not in onefile)."""
    from aa_config_env import build_backtest_argv

    root = Path(root)
    model_script = root / "active_alpha_model.py"
    if not model_script.is_file():
        msg = (
            "active_alpha_model.py fehlt neben Marktanalyse.exe — "
            "EXE muss im Projektordner liegen (mit .venv)."
        )
        if log is not None:
            log.append(msg)
        return False, None, msg

    py = _venv_python(root)
    if not py.is_file():
        msg = (
            "Projekt-.venv fehlt — Windows: setup_active_alpha_env.bat · "
            "Linux: bash tools/setup_linux_native.sh"
        )
        if log is not None:
            log.append(msg)
        return False, None, msg

    argv = build_backtest_argv(dict(env))
    argv[argv.index("--mode") + 1] = "signal"
    cmd = [str(py), str(model_script), *argv[1:]]
    proc_env = {**os.environ, **{k: str(v) for k, v in env.items() if k.startswith("AA_")}}
    if log is not None:
        log.append(f"[INFO] Signal-Subprocess: {py.name} active_alpha_model.py --mode signal")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            env=proc_env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, None, "Signal-Lauf Zeitüberschreitung."
    ok = proc.returncode == 0
    if not ok and log is not None:
        tail = (proc.stderr or proc.stdout or "")[-400:]
        if tail:
            log.append(tail)
    return ok, proc, ""


def run_champion_signal_update(root: Path, *, timeout_s: int = 7200) -> Dict[str, Any]:
    """Profile-driven signal refresh (daily_alpha_h1 default) → latest_target_portfolio.csv."""
    root = Path(root)
    from aa_frozen import is_frozen_exe

    log_lines: list[str] = []
    try:
        from analytics.prediction_operations import active_profile, run_eod_prediction_switch

        prof = active_profile(root)
        log_lines.append(f"[INFO] Prediction-Profil: {prof}")
        pred = run_eod_prediction_switch(root, force=True)
        if pred.get("ok") and not pred.get("skipped"):
            out = _signal_env(root).get("AA_PAPER_MODEL_OUT_DIR") or "model_output_sp500_pit_t212"
            csv_path = root / out / "latest_target_portfolio.csv"
            return {
                "ok": True,
                "via_subprocess": False,
                "returncode": 0,
                "stdout_tail": "\n".join(log_lines + [str(pred.get("message_de") or "")])[-2000:],
                "stderr_tail": "",
                "portfolio_csv": str(csv_path),
                "portfolio_csv_exists": csv_path.is_file(),
                "message_de": str(pred.get("message_de") or "Signal aktualisiert."),
                "prediction_profile": prof,
                "prediction_result": pred.get("result"),
            }
        if not pred.get("skipped"):
            log_lines.append(str(pred.get("message_de") or pred.get("error") or "predict failed"))
    except Exception as exc:
        log_lines.append(f"[WARN] run_tomorrow_prediction: {exc} — Fallback Legacy-Signal.")

    env = _signal_env(root)
    out = env.get("AA_PAPER_MODEL_OUT_DIR") or env.get("AA_BACKTEST_OUT_DIR") or "model_output_sp500_pit_t212"
    sector_refresh: Dict[str, Any] = {}
    try:
        from aa_sector_reference import ensure_sector_reference_fresh

        sector_refresh = ensure_sector_reference_fresh(root, env)
        if sector_refresh.get("message_de"):
            log_lines.append(str(sector_refresh["message_de"]))
    except Exception as exc:
        sector_refresh = {"refreshed": False, "error": str(exc)[:200]}
        log_lines.append(f"[WARN] Sektor-Referenz: {exc}")

    def _log(msg: str) -> None:
        log_lines.append(msg)

    frozen = is_frozen_exe()
    ok = False
    proc: Optional[subprocess.CompletedProcess] = None
    spawn_reason = ""

    if not frozen:
        try:
            from aa_ops_refresh import refresh_signal_portfolio

            ok = refresh_signal_portfolio(root, env, log=_log)
        except Exception as exc:
            ok = False
            spawn_reason = str(exc)[:300]
            _log(spawn_reason)

    if not ok:
        if frozen:
            _log("[INFO] EXE: Signal über Projekt-.venv (ML nicht im Onefile gebündelt).")
        elif spawn_reason:
            _log("[INFO] In-process fehlgeschlagen — Fallback Subprocess.")
        ok, proc, err = _run_signal_subprocess(root, env, timeout_s=timeout_s, log=log_lines)
        if err and not ok:
            _log(err)

    state = load_state(root)
    if ok:
        state["last_signal_update_utc"] = _utc_now()
        save_state(root, state)
    csv_path = root / out / "latest_target_portfolio.csv"
    exists = csv_path.is_file()
    if ok and not exists:
        ok = False
        _log(f"[WARN] Portfolio fehlt: {csv_path}")
    msg_de = "Champion-Signal aktualisiert."
    if not ok:
        from aa_paths import venv_python_ok

        if frozen and not venv_python_ok(root):
            msg_de = "Signal fehlgeschlagen: .venv im Projektordner fehlt."
        elif not (root / "active_alpha_model.py").is_file():
            msg_de = "Signal fehlgeschlagen: EXE nicht im Projektordner."
        else:
            msg_de = "Signal-Lauf fehlgeschlagen — Log im Dialog / evidence."
    return {
        "ok": ok,
        "via_subprocess": frozen or proc is not None,
        "returncode": 0 if ok else (proc.returncode if proc else 1),
        "stdout_tail": "\n".join(log_lines)[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:] if proc else "",
        "portfolio_csv": str(csv_path),
        "portfolio_csv_exists": exists,
        "message_de": msg_de,
        "sector_refresh": sector_refresh,
    }


def _broker_dict_from_status(st: Any, *, root: Path | None = None, cached_fallback: bool = True) -> Dict[str, Any]:
    """Map BrokerConnectionStatus to dashboard broker payload (never silent zero cash)."""
    from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

    root_hint = root
    configured = bool(getattr(st, "credentials_configured", False))
    cash = getattr(st, "cash_eur", None)
    last_err = (getattr(st, "last_error", None) or "").strip()
    status_name = str(getattr(st, "status", "") or "")

    if not configured or status_name == "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI":
        return {
            "error": "Trading-212 API fehlt — unten API Key und Secret speichern, dann «Verbindung testen».",
            "credentials_configured": False,
            "cash_eur": None,
            "positions": [],
        }

    if cash is None and cached_fallback and root_hint is not None:
        cached = load_cached_broker_status(Path(root_hint))
        if cached and cached.cash_eur is not None:
            cash = cached.cash_eur
            positions = cached.positions or []
            out = {
                "cash_eur": float(cash),
                "positions": positions,
                "credentials_configured": True,
                "cached": True,
                "last_sync_utc": cached.last_successful_sync_utc,
            }
            if getattr(cached, "cash_breakdown", None):
                out["cash_breakdown"] = cached.cash_breakdown
            if last_err:
                out["warning"] = last_err[:200]
            return out

    if cash is None:
        msg = last_err or "Konto-Sync fehlgeschlagen — «Verbindung laden» oder API prüfen."
        return {
            "error": msg[:200],
            "credentials_configured": configured,
            "cash_eur": None,
            "positions": getattr(st, "positions", None) or [],
        }

    out = {
        "cash_eur": float(cash),
        "positions": getattr(st, "positions", None) or [],
        "credentials_configured": True,
        "last_sync_utc": getattr(st, "last_successful_sync_utc", None),
        "status": status_name,
    }
    if getattr(st, "cash_breakdown", None):
        out["cash_breakdown"] = st.cash_breakdown
    if last_err:
        out["warning"] = last_err[:200]
    return out


def sync_broker_and_quotes(root: Path, *, force_quotes: bool = True, force_sync: bool = True) -> Dict[str, Any]:
    """Live «mark»: T212 read-only + Yahoo live quotes."""
    root = Path(root)
    broker: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_readonly_connection_service import (
            load_cached_broker_status,
            sync_readonly_account,
        )

        cached = load_cached_broker_status(root)
        if cached and cached.cash_eur is not None and not force_sync:
            broker = _broker_dict_from_status(cached, cached_fallback=False)
            broker["cached"] = True
        else:
            st = sync_readonly_account(root, force=force_sync)
            broker = _broker_dict_from_status(st, root=root, cached_fallback=True)
    except Exception as exc:
        broker = {"error": str(exc)[:200], "credentials_configured": False}
        try:
            from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

            cached = load_cached_broker_status(root)
            if cached and cached.cash_eur is not None:
                broker = {
                    "cash_eur": float(cached.cash_eur),
                    "positions": cached.positions or [],
                    "credentials_configured": True,
                    "cached": True,
                    "warning": str(exc)[:120],
                }
        except Exception:
            pass
    quote_snapshot: Dict[str, Any] = {}
    try:
        from analytics.pilot_live_trade_gate import fetch_live_quotes_fail_closed

        quote_snapshot, _ = fetch_live_quotes_fail_closed(root, force=force_quotes)
    except Exception as exc:
        quote_snapshot = {"error": str(exc)[:200]}
    return {"broker": broker, "quote_snapshot": quote_snapshot}


def build_rebalance_orders(
    root: Path,
    *,
    broker: Mapping[str, Any],
    reevaluation: Mapping[str, Any],
    quote_snapshot: Optional[Mapping[str, Any]] = None,
    pol: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    from analytics.pilot_walkforward_mirror import build_rebalance_orders as _build

    pol = pol or load_policy(root)
    return _build(root, broker=broker, reevaluation=reevaluation, quote_snapshot=quote_snapshot, pol=pol)


def execute_live_rebalance(
    root: Path,
    *,
    broker: Optional[Mapping[str, Any]] = None,
    quote_snapshot: Optional[Mapping[str, Any]] = None,
    champion_guard: Optional[Mapping[str, Any]] = None,
    force: bool = False,
    run_signal_before: Optional[bool] = None,
    source: str = "LIVE_REBALANCE",
) -> Dict[str, Any]:
    """Paper 2_rebalance_when_due: optional signal, then full portfolio orders at T212 (nur R3-Oberfläche)."""
    root = Path(root)
    from analytics.r3_order_execution_gate import check_order_execution_allowed

    gate = check_order_execution_allowed(root, source=source, operation="execute_live_rebalance")
    if not gate.get("allowed"):
        blocked = {
            "ok": False,
            "mode": "r3_order_surface_required",
            "message_de": gate.get("message_de"),
            "order_gate": gate,
            "source": source,
        }
        atomic_write_json(root / _EVIDENCE_REL, {**blocked, "generated_at_utc": _utc_now()})
        return blocked

    pol = load_policy(root)
    status = rebalance_status(root, pol=pol)
    if not force and not status.get("is_due"):
        return {
            "ok": False,
            "mode": "mark_only",
            "message_de": status.get("summary_de", "Kein Rebalance fällig."),
            "rebalance_status": status,
        }

    from execution.confirmed_live.live_trading_enablement import ensure_live_trading_enabled

    ensure_live_trading_enabled(root, changed_by="live_rebalance")

    from analytics.prediction_operations import ensure_prediction_before_orders

    pred = ensure_prediction_before_orders(root, auto_run=True)
    if not pred.get("ok") and not pred.get("skipped"):
        blocked = {
            "ok": False,
            "mode": "prediction_blocked",
            "message_de": pred.get("message_de", "Predict fehlt — keine Orders."),
            "prediction_gate": pred,
            "rebalance_status": status,
        }
        atomic_write_json(root / _EVIDENCE_REL, {**blocked, "generated_at_utc": _utc_now()})
        return blocked

    sync = sync_broker_and_quotes(root, force_quotes=True)
    broker = broker or sync.get("broker") or {}
    quote_snapshot = quote_snapshot or sync.get("quote_snapshot") or {}

    from analytics.pilot_investment_plan import ensure_plan_symbols_in_scope

    signal_result: Dict[str, Any] = {"skipped": True}
    do_signal = pol.get("run_signal_before_rebalance", True) if run_signal_before is None else bool(
        run_signal_before
    )
    if do_signal:
        signal_result = run_champion_signal_update(root)
        if not signal_result.get("ok"):
            return {
                "ok": False,
                "mode": "signal_failed",
                "signal_update": signal_result,
                "rebalance_status": status,
                "message_de": signal_result.get("message_de", "Signal-Update fehlgeschlagen — Rebalance abgebrochen."),
            }

    from analytics.pilot_investment_plan import build_investment_plan
    from analytics.r3_closed_loop import load_r3_account_for_engine

    cash = float(broker.get("cash_eur") or 0)
    acct = load_r3_account_for_engine(root)
    inv = acct.get("investable_eur") if acct.get("ok") else None
    plan = build_investment_plan(
        root,
        cash,
        investable_eur=float(inv) if inv is not None else None,
        budget_source="r3_t212_investable" if inv is not None else None,
    )
    ensure_plan_symbols_in_scope(root, plan)

    from analytics.pilot_portfolio_reevaluation import evaluate_live_portfolio_vs_champion

    reeval = evaluate_live_portfolio_vs_champion(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snapshot,
        champion_guard=champion_guard,
    )
    orders = build_rebalance_orders(root, broker=broker, reevaluation=reeval, quote_snapshot=quote_snapshot, pol=pol)
    orders = orders[: int(pol.get("max_rebalance_orders") or 40)]

    from market.champion_quote_gate import require_champion_quote_coverage, symbols_from_orders

    buy_symbols = symbols_from_orders(orders)
    quote_gate = require_champion_quote_coverage(
        root,
        symbols=buy_symbols if buy_symbols else None,
        quote_snapshot=quote_snapshot,
        refresh_if_stale=False,
    )
    if buy_symbols and not quote_gate.get("ok"):
        blocked = {
            "ok": False,
            "mode": "quote_coverage_blocked",
            "quote_coverage": quote_gate,
            "quote_coverage_label_de": quote_gate.get("quote_coverage_label_de"),
            "orders_planned": len(orders),
            "message_de": quote_gate.get("message_de"),
            "rebalance_status": status,
            "signal_update": signal_result,
        }
        atomic_write_json(root / _EVIDENCE_REL, {**blocked, "generated_at_utc": _utc_now()})
        return blocked

    from execution.confirmed_live.us_equity_deferred_intents import try_execute_walkforward_rebalance_now

    exec_result = try_execute_walkforward_rebalance_now(
        root,
        orders=orders,
        plan=plan,
        quote_snapshot=quote_snapshot,
        broker=broker,
        source=source,
        champion_guard=champion_guard,
    )
    from analytics.execution_result_report import attach_execution_report

    exec_result = attach_execution_report(exec_result, orders)
    exec_result["quote_coverage"] = quote_gate
    exec_result["quote_coverage_label_de"] = quote_gate.get("quote_coverage_label_de")
    exec_result = normalize_execution_result(exec_result)
    if exec_result.get("rebalance_completed") or exec_result.get("sent_to_t212"):
        status = note_rebalance_completed(root)
    elif exec_result.get("fallback") == "enqueue_after_readiness_block" and exec_result.get("enqueued", 0) > 0:
        status = note_rebalance_completed(root)

    out = {
        "ok": bool(exec_result.get("ok")),
        "signal_update": signal_result,
        "rebalance_status": status,
        "orders_planned": len(orders),
        "execution": exec_result,
        "sent_to_t212": exec_result.get("sent_to_t212"),
        "quote_coverage": quote_gate,
        "quote_coverage_label_de": quote_gate.get("quote_coverage_label_de"),
        "execution_breakdown": exec_result.get("execution_breakdown"),
        "message_de": exec_result.get("message_de") or status.get("summary_de", ""),
    }
    atomic_write_json(root / _EVIDENCE_REL, {**out, "generated_at_utc": _utc_now()})
    return out


def enqueue_live_rebalance_when_due(
    root: Path,
    *,
    broker: Optional[Mapping[str, Any]] = None,
    quote_snapshot: Optional[Mapping[str, Any]] = None,
    champion_guard: Optional[Mapping[str, Any]] = None,
    source: str = "LIVE_REBALANCE_ENQUEUE",
) -> Dict[str, Any]:
    """Rebalance fällig: Orders vormerken (Paper 2_rebalance — manuell oder US-Eröffnung)."""
    root = Path(root)
    pol = load_policy(root)
    sync = sync_broker_and_quotes(root, force_quotes=True)
    broker = broker or sync.get("broker") or {}
    quote_snapshot = quote_snapshot or sync.get("quote_snapshot") or {}

    from analytics.pilot_investment_plan import build_investment_plan

    plan = build_investment_plan(root, float(broker.get("cash_eur") or 0))
    from analytics.pilot_portfolio_reevaluation import evaluate_live_portfolio_vs_champion

    reeval = evaluate_live_portfolio_vs_champion(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snapshot,
        champion_guard=champion_guard,
    )
    from analytics.pilot_investment_plan import ensure_plan_symbols_in_scope

    ensure_plan_symbols_in_scope(root, plan)

    orders = build_rebalance_orders(root, broker=broker, reevaluation=reeval, quote_snapshot=quote_snapshot, pol=pol)
    orders = orders[: int(pol.get("max_rebalance_orders") or 40)]

    from market.champion_quote_gate import require_champion_quote_coverage, symbols_from_orders

    buy_symbols = symbols_from_orders(orders)
    quote_gate = require_champion_quote_coverage(
        root,
        symbols=buy_symbols if buy_symbols else None,
        quote_snapshot=quote_snapshot,
        refresh_if_stale=False,
    )
    if buy_symbols and not quote_gate.get("ok"):
        return {
            "ok": False,
            "mode": "quote_coverage_blocked",
            "quote_coverage": quote_gate,
            "message_de": quote_gate.get("message_de"),
            "orders_planned": len(orders),
        }

    from execution.confirmed_live.planning_cash import resolve_planning_cash_eur
    from execution.confirmed_live.rebalance_wave_planner import plan_rebalance_wave

    cash_plan = resolve_planning_cash_eur(float(broker.get("cash_eur") or 0), broker=broker, root=root)
    wave = plan_rebalance_wave(orders, cash_plan)
    orders = list(wave.get("orders") or orders)
    plan = {**plan, "rebalance_wave": {k: v for k, v in wave.items() if k != "orders"}}

    from execution.confirmed_live.us_equity_deferred_intents import enqueue_walkforward_rebalance_orders

    enq = enqueue_walkforward_rebalance_orders(
        root,
        orders=orders,
        plan=plan,
        quote_snapshot=quote_snapshot,
        source=source,
    )
    status = rebalance_status(root, pol=pol)
    if enq.get("ok"):
        status = note_rebalance_completed(root)
    sells = sum(1 for o in orders if o.get("side") == "SELL")
    buys = sum(1 for o in orders if o.get("side") == "BUY")
    out = {
        "ok": bool(enq.get("ok")),
        "mode": "live_enqueue",
        "orders_planned": len(orders),
        "enqueue": enq,
        "rebalance_status": status,
        "message_de": (
            f"Rebalance fällig — {sells} Verkauf(e), {buys} Kauf(e) vorgemerkt (US-Eröffnung / «Order ausführen»)."
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, {**out, "generated_at_utc": _utc_now()})
    return out


def run_daily_live_cycle(
    root: Path,
    *,
    champion_guard: Optional[Mapping[str, Any]] = None,
    armed_auto: bool = False,
    force_rebalance: bool = False,
) -> Dict[str, Any]:
    """1_daily: sync + mark day; 2: rebalance if due (or forced)."""
    root = Path(root)
    pol = load_policy(root)
    from execution.confirmed_live.live_trading_enablement import ensure_live_trading_enabled

    if pol.get("auto_enable_on_startup", True):
        ensure_live_trading_enabled(root, changed_by="daily_cycle")

    sector_refresh: Dict[str, Any] = {}
    try:
        from aa_sector_reference import ensure_sector_reference_fresh

        sector_refresh = ensure_sector_reference_fresh(root, _signal_env(root))
    except Exception as exc:
        sector_refresh = {"refreshed": False, "error": str(exc)[:200]}

    sync = sync_broker_and_quotes(root, force_quotes=True)
    mark = record_daily_mark(root, pol=pol)
    status = rebalance_status(root, pol=pol)
    broker = sync.get("broker") or {}
    sync_ok = "error" not in broker and bool(broker.get("credentials_configured", True))
    if mark.get("recorded"):
        summary = (
            f"Tages-Mark gezählt ({status.get('recorded_trading_days_since_rebalance', 0)}"
            f"/{status.get('rebalance_every_trading_days', 5)}). "
            f"Konto: {float(broker.get('cash_eur') or 0):.2f} €."
        )
    elif mark.get("reason") == "ALREADY_MARKED_TODAY":
        summary = (
            f"Sync OK — Mark-Tag war heute schon gezählt "
            f"({status.get('recorded_trading_days_since_rebalance', 0)}"
            f"/{status.get('rebalance_every_trading_days', 5)}). "
            f"Konto: {float(broker.get('cash_eur') or 0):.2f} €."
        )
    else:
        summary = status.get("summary_de", "")
    sector_msg = str(sector_refresh.get("message_de") or "").strip()
    if sector_msg:
        summary = f"{summary} · {sector_msg}" if summary else sector_msg

    out: Dict[str, Any] = {
        "ok": sync_ok,
        "sync_ok": sync_ok,
        "mode": "live_trading",
        "generated_at_utc": _utc_now(),
        "daily_mark": mark,
        "sync": sync,
        "rebalance_status": status,
        "sector_refresh": sector_refresh,
        "summary_de": summary,
        "message_de": summary,
    }

    if force_rebalance or status.get("is_due"):
        # Orders nur über R3 — Hintergrund-Zyklus vormerkt höchstens, führt nie aus.
        if pol.get("auto_enqueue_on_rebalance_due", True):
            rb = enqueue_live_rebalance_when_due(
                root,
                broker=sync.get("broker"),
                quote_snapshot=sync.get("quote_snapshot"),
                champion_guard=champion_guard,
            )
        else:
            rb = {
                "ok": False,
                "mode": "rebalance_due_manual",
                "message_de": status.get(
                    "summary_de",
                    "Rebalance fällig — Orders nur über R3 (Order-Desk / Cockpit).",
                ),
            }
        out["rebalance"] = rb
        out["summary_de"] = rb.get("message_de", out["summary_de"])

    try:
        from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

        out["live_outcome_sync"] = sync_live_execution_outcomes(root, refresh_history=True)
    except Exception as exc:
        out["live_outcome_sync"] = {"ok": False, "error": str(exc)[:200]}

    atomic_write_json(root / _EVIDENCE_REL, out)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    from aa_paths import project_root

    parser = argparse.ArgumentParser(description="Live trading ops (Paper-parity BATs)")
    parser.add_argument(
        "--mode",
        choices=("daily", "rebalance", "rebalance-force"),
        default="daily",
        help="daily=mark+sync; rebalance=if due; rebalance-force=always",
    )
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else project_root()
    if args.mode == "daily":
        run_daily_live_cycle(root, armed_auto=False, force_rebalance=False)
    elif args.mode == "rebalance":
        st = rebalance_status(root)
        if st.get("is_due"):
            execute_live_rebalance(root, force=True, source="LIVE_BAT_REBALANCE")
        else:
            sync_broker_and_quotes(root)
            record_daily_mark(root)
            print(st.get("summary_de", "MARK_ONLY"))
    else:
        execute_live_rebalance(root, force=True, source="LIVE_BAT_REBALANCE_FORCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
