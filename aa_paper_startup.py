"""Paper-trading startup hooks for Marktanalyse.exe (daily mark + rebalance alerts)."""
from __future__ import annotations

import subprocess
import sys
import threading
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

LogFn = Callable[[str], None]
PumpFn = Callable[..., None]


def paper_dir_from_env(env: Mapping[str, str], *, root: Optional[Path] = None) -> Path:
    rel = str(env.get("AA_PAPER_DIR", "paper_output") or "paper_output")
    path = Path(rel)
    if path.is_absolute():
        return path
    return (root or Path.cwd()) / path


def mark_recorded_today(paper_dir: Path, *, today: Optional[str] = None) -> bool:
    """True when paper_equity.csv already has a mark/rebalance row for today."""
    eq_path = paper_dir / "paper_equity.csv"
    if not eq_path.is_file():
        return False
    try:
        import pandas as pd
    except ImportError:
        return False
    try:
        eq = pd.read_csv(eq_path)
    except Exception:
        return False
    if eq.empty or "date" not in eq.columns:
        return False
    day = today or date.today().isoformat()
    modes = eq["mode"].astype(str).str.lower() if "mode" in eq.columns else pd.Series("", index=eq.index)
    dates = eq["date"].astype(str)
    mask = dates.eq(day) & modes.isin({"mark", "rebalance"})
    return bool(mask.any())


def build_paper_mark_argv(env: Mapping[str, str]) -> list[str]:
    """Build argv for paper_trading_engine.py mark mode (mirrors run_paper_mark_to_market.bat)."""
    argv = [
        "paper_trading_engine.py",
        "--mode",
        "mark",
        "--paper-dir",
        str(env.get("AA_PAPER_DIR", "paper_output")),
        "--benchmark",
        str(env.get("AA_BENCHMARK", "SPY")),
        "--capital",
        str(env.get("AA_PAPER_CAPITAL", "400")),
        "--fee-model",
        "trading212_us",
        "--slippage-bps",
        str(env.get("AA_SLIPPAGE_BPS", "2")),
        "--market-impact-bps",
        str(env.get("AA_MARKET_IMPACT_BPS", "0")),
        "--trading212-sec-fee-rate",
        str(env.get("AA_TRADING212_SEC_FEE_RATE", "0.0000278")),
        "--trading212-finra-taf-per-share",
        str(env.get("AA_TRADING212_FINRA_TAF_PER_SHARE", "0.000195")),
        "--trading212-fx-bps",
        str(env.get("AA_TRADING212_FX_BPS", "0")),
        "--trading212-policy",
        str(env.get("AA_TRADING212_POLICY", "threshold")),
        "--max-gross-exposure",
        str(env.get("AA_MAX_GROSS_EXPOSURE", "1.0")),
        "--price-lookback-days",
        str(env.get("AA_PRICE_LOOKBACK_DAYS", "10")),
        "--price-interval",
        str(env.get("AA_PRICE_INTERVAL", "1d")),
        "--execute",
    ]
    if str(env.get("AA_EXECUTION_POLICY_MODE", "")).lower() == "capital_curve":
        argv.append("--capital-curve-policy")
    return argv


def run_paper_mark_inprocess(env: Mapping[str, str], *, plain_progress: bool = True) -> int:
    """Run mark-to-market in the current process (no second Python / no extra dashboard window)."""
    from paper_trading_engine import parse_args, run_engine

    argv = list(build_paper_mark_argv(env))
    if plain_progress:
        argv.append("--plain-progress")
    old_argv = sys.argv
    sys.argv = argv
    try:
        args = parse_args()
        return int(run_engine(args))
    finally:
        sys.argv = old_argv


def _run_mark_with_ui_pump(
    env: Mapping[str, str],
    *,
    inprocess: bool,
    venv_py: Path,
    root: Path,
    pump_ui_fn: Optional[PumpFn],
    run_subprocess: Optional[Callable[..., subprocess.CompletedProcess]],
) -> int:
    if inprocess:
        if pump_ui_fn is None:
            return run_paper_mark_inprocess(env, plain_progress=True)
        result = {"rc": 1}

        def _worker() -> None:
            result["rc"] = run_paper_mark_inprocess(env, plain_progress=True)

        worker = threading.Thread(target=_worker, name="paper-mark", daemon=True)
        worker.start()
        while worker.is_alive():
            pump_ui_fn(force=True)
            worker.join(timeout=0.04)
        return int(result["rc"])

    runner = run_subprocess
    if runner is None:
        from aa_dashboard_qt import run_subprocess_with_ui

        runner = run_subprocess_with_ui
    cmd = [str(venv_py), *build_paper_mark_argv(env), "--plain-progress"]
    proc = runner(cmd, cwd=str(root), check=False)
    return int(getattr(proc, "returncode", 1))


def refresh_rebalance_status(paper_dir: Path, env: Mapping[str, str]) -> Dict[str, object]:
    from paper_trading_engine import choose_capital_aware_execution_policy, write_next_rebalance_file

    capital = float(str(env.get("AA_PAPER_CAPITAL", "400")).replace(",", "."))
    policy = choose_capital_aware_execution_policy(
        capital,
        fee_model="trading212_us",
        policy=str(env.get("AA_TRADING212_POLICY", "threshold")),
    )
    return write_next_rebalance_file(paper_dir, policy)


def is_rebalance_due(status: Mapping[str, object]) -> bool:
    rec = str(status.get("recommendation", "") or "")
    if bool(status.get("is_due", False)):
        return True
    return rec.startswith("REBALANCE_DUE")


def format_rebalance_notice(status: Mapping[str, object], *, paper_dir: Path) -> str:
    rec = str(status.get("recommendation", "-"))
    last = str(status.get("last_rebalance_date", "-"))
    every = status.get("rebalance_every", "?")
    recorded = status.get("recorded_mark_days_since_rebalance", "?")
    remaining = status.get("days_remaining", "?")
    return (
        "Paper-Trading: Rebalance ist fällig.\n\n"
        f"Empfehlung: {rec}\n"
        f"Letztes Rebalance: {last}\n"
        f"Erfasste Mark-Tage seit Rebalance: {recorded} / {every}\n"
        f"Verbleibend bis fällig: {remaining}\n\n"
        "Bitte run_paper_trading.bat ausführen (Reset = Nein).\n\n"
        f"Details: {paper_dir / 'next_rebalance_due.txt'}"
    )


def notify_rebalance_due(message: str) -> None:
    from aa_dashboard_qt import notify_user_dialog

    notify_user_dialog(message, title="Active Alpha — Rebalance fällig", warning=True)


def run_paper_startup(
    root: Path,
    venv_py: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    inprocess: bool = True,
    pump_ui_fn: Optional[PumpFn] = None,
    run_subprocess: Optional[Callable[..., subprocess.CompletedProcess]] = None,
) -> Dict[str, object]:
    """Run daily mark-to-market once per calendar day; alert when rebalance is due."""
    paper_dir = paper_dir_from_env(env, root=root)
    state_path = paper_dir / "paper_state.json"
    if not state_path.is_file():
        log("[INFO] Kein Paper-Depot — Mark-to-Market übersprungen.")
        return {}

    status: Dict[str, object] = {"paper_mark_ok": True, "paper_mark_rc": 0}
    try:
        status = refresh_rebalance_status(paper_dir, env)
    except Exception as exc:
        log(f"[WARN] Rebalance-Status konnte nicht aktualisiert werden: {exc}")

    if mark_recorded_today(paper_dir):
        log("[OK] Mark-to-Market für heute bereits erfasst.")
    else:
        log("[INFO] Tägliches Mark-to-Market …")
        if pump_ui_fn is not None:
            pump_ui_fn(force=True)
        try:
            rc = _run_mark_with_ui_pump(
                env,
                inprocess=inprocess,
                venv_py=venv_py,
                root=root,
                pump_ui_fn=pump_ui_fn,
                run_subprocess=run_subprocess,
            )
        except Exception as exc:
            log(f"[WARN] Mark-to-Market fehlgeschlagen: {exc}")
            rc = 1
            status["paper_mark_ok"] = False
            status["paper_mark_rc"] = rc
        else:
            status["paper_mark_rc"] = rc
            if rc == 0:
                log("[OK] Mark-to-Market abgeschlossen.")
                status["paper_mark_ok"] = True
            else:
                log(f"[WARN] Mark-to-Market beendet mit Code {rc}.")
                status["paper_mark_ok"] = False
        if rc == 0:
            try:
                status = refresh_rebalance_status(paper_dir, env)
            except Exception as exc:
                log(f"[WARN] Rebalance-Status nach Mark nicht aktualisiert: {exc}")
        if pump_ui_fn is not None:
            pump_ui_fn(force=True)

    if not status:
        try:
            status = refresh_rebalance_status(paper_dir, env)
        except Exception:
            return {}

    if is_rebalance_due(status):
        msg = format_rebalance_notice(status, paper_dir=paper_dir)
        log(f"[HINWEIS] REBALANCE FÄLLIG — {status.get('recommendation', 'REBALANCE_DUE')}")
        notify_rebalance_due(msg)
    else:
        remaining = status.get("days_remaining", "?")
        log(f"[OK] Kein Rebalance fällig (noch {remaining} Mark-Tage bis zum nächsten Rebalance).")

    return dict(status)
