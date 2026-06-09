"""Live daily OHLCV sync for portfolio-corresponding tickers (continuous prediction refinement)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

SYNC_MANIFEST = "live_daily_sync.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _out_dir(root: Path, env: Mapping[str, str]) -> Path:
    rel = str(env.get("AA_BACKTEST_OUT_DIR", "model_output_sp500_pit_t212") or "model_output_sp500_pit_t212")
    path = Path(rel)
    return path if path.is_absolute() else root / path


def read_exemplar_portfolio_tickers(out_dir: Path) -> List[str]:
    from aa_dashboard_result import exemplar_stock_portfolio, load_target_portfolio

    portfolio, _ = load_target_portfolio(out_dir)
    if portfolio.empty:
        return []
    stock = exemplar_stock_portfolio(portfolio)
    if stock.empty or "ticker" not in stock.columns:
        return []
    return [str(t).upper().strip() for t in stock["ticker"].tolist() if str(t).strip()]


def merge_ticker_universe(*groups: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    merged: List[str] = []
    for group in groups:
        for raw in group:
            tk = str(raw or "").upper().strip()
            if not tk or tk in seen:
                continue
            seen.add(tk)
            merged.append(tk)
    return sorted(merged)


def resolve_prediction_tickers(root: Path, env: Mapping[str, str]) -> Tuple[List[str], Dict[str, object]]:
    """Universe tickers + exemplar portfolio tickers + benchmark (always included for features)."""
    from aa_config import BacktestConfig, parse_args
    from aa_config_env import build_backtest_argv
    from aa_universe import load_tickers

    out_dir = _out_dir(root, env)
    portfolio_tickers = read_exemplar_portfolio_tickers(out_dir)
    benchmark = str(env.get("AA_BENCHMARK", "SPY") or "SPY").upper().strip()

    old_argv = sys.argv
    try:
        argv = build_backtest_argv(dict(env))
        sys.argv = argv
        args = parse_args()
        universe_tickers = load_tickers(args)
    finally:
        sys.argv = old_argv

    merged = merge_ticker_universe(universe_tickers, portfolio_tickers, [benchmark])
    detail = {
        "benchmark": benchmark,
        "portfolio_tickers": portfolio_tickers,
        "universe_ticker_count": len(universe_tickers),
        "merged_ticker_count": len(merged),
        "portfolio_only_added": sorted(set(portfolio_tickers) - set(universe_tickers)),
    }
    return merged, detail


def fetch_portfolio_live_quotes(tickers: Sequence[str]) -> Dict[str, object]:
    from aa_dashboard_result import fetch_last_prices_usd

    if not tickers:
        return {"fetched_at_utc": _utc_now(), "quotes_usd": {}, "tickers_requested": 0}
    quotes = fetch_last_prices_usd(list(tickers))
    return {
        "fetched_at_utc": _utc_now(),
        "quotes_usd": {k: float(v) for k, v in quotes.items()},
        "tickers_requested": len(tickers),
        "tickers_fetched": len(quotes),
    }


def write_sync_manifest(out_dir: Path, payload: Dict[str, object]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SYNC_MANIFEST
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_sync_manifest(out_dir: Path) -> Dict[str, object]:
    path = out_dir / SYNC_MANIFEST
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@dataclass
class LiveDailySyncReport:
    ok: bool = False
    prices_refreshed: bool = False
    signal_refreshed: bool = False
    price_latest: Optional[str] = None
    signal_date: Optional[str] = None
    portfolio_tickers: List[str] = field(default_factory=list)
    merged_ticker_count: int = 0
    live_quotes: Dict[str, float] = field(default_factory=dict)
    manifest_path: str = ""
    r3_diagnosis_ok: bool = False
    r3_regime_match: Optional[bool] = None
    r3_diagnosis_path: str = ""
    messages: List[str] = field(default_factory=list)


def refresh_prediction_prices(
    root: Path,
    env: Mapping[str, str],
    *,
    tickers: Sequence[str],
    force: bool = False,
) -> Tuple[bool, Optional[str], List[str]]:
    """Download/update OHLCV panel for merged ticker universe."""
    from aa_config import BacktestConfig, parse_args
    from aa_config_env import build_backtest_argv
    from aa_data_freshness import assess_daily_data, last_expected_market_date
    from aa_features import download_data, merge_recent_ohlcv_into_price_cache

    messages: List[str] = []
    out_dir = _out_dir(root, env)
    bench = str(env.get("AA_BENCHMARK", "SPY") or "SPY").upper().strip()
    ref = last_expected_market_date()
    cache_dir = out_dir / "price_cache"

    def _run_tail_merge() -> Optional[date]:
        port = read_exemplar_portfolio_tickers(out_dir)
        tail = merge_ticker_universe([bench], port, list(tickers)[:120])
        return merge_recent_ohlcv_into_price_cache(cache_dir, tail, lookback_days=14)

    report = assess_daily_data(root, env)
    need_refresh = force or not report.price_current

    # Fast path: yfinance tail merge when benchmark (SPY) lags reference session.
    if force or report.price_latest is None or report.price_latest < ref:
        try:
            tail_latest = _run_tail_merge()
            if tail_latest is not None:
                messages.append(
                    f"[INFO] Tages-Tail-Merge ({bench}): Panel bis {tail_latest.isoformat()} "
                    f"(Referenz {ref.isoformat()})"
                )
            report = assess_daily_data(root, env)
            if report.price_current and not force:
                latest = report.price_latest.isoformat() if report.price_latest else None
                messages.append(f"[OK] Preis-Cache via Tail-Merge aktuell — Stand {latest}")
                return True, latest, messages
            need_refresh = True
        except Exception as exc:
            messages.append(f"[WARN] Tail-Merge fehlgeschlagen: {exc}")

    if not need_refresh:
        latest = report.price_latest.isoformat() if report.price_latest else None
        messages.append(f"[OK] Preis-Cache bereits tagesaktuell ({latest}, Benchmark {bench})")
        return False, latest, messages

    old_argv = sys.argv
    try:
        argv = build_backtest_argv(dict(env))
        sys.argv = argv
        args = parse_args()
        cfg = BacktestConfig.from_args(args)
        cfg.skip_download_if_cached = False
        cfg.write_price_cache = True
        messages.append(
            f"[INFO] Live-Tagesdaten: lade {len(tickers)} Ticker ab {cfg.start} "
            f"(Portfolio + Universum + Benchmark) …"
        )
        download_data(list(tickers), cfg.start, dashboard=None, cfg=cfg, out_dir=out_dir)
        report = assess_daily_data(root, env)
        if report.price_latest is not None and report.price_latest < ref:
            tail_latest = _run_tail_merge()
            if tail_latest is not None:
                messages.append(
                    f"[INFO] Nach Voll-Download Tail-Merge bis {tail_latest.isoformat()} "
                    f"(Referenz {ref.isoformat()})"
                )
            report = assess_daily_data(root, env)
        latest = report.price_latest.isoformat() if report.price_latest else None
        messages.append(f"[OK] Preis-Cache aktualisiert — Stand {latest or 'unbekannt'} (Benchmark {bench})")
        return True, latest, messages
    except Exception as exc:
        messages.append(f"[WARN] Preis-Update fehlgeschlagen: {exc}")
        return False, None, messages
    finally:
        sys.argv = old_argv


def _local_calendar_day_from_utc_iso(iso: str) -> str:
    if not iso:
        return ""
    try:
        ts = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone().date().isoformat()
    except Exception:
        return ""


def needs_between_trading_day_refresh(root: Path, env: Mapping[str, str]) -> bool:
    """True when a new local day started or price/signal lag the last US session."""
    from aa_data_freshness import assess_daily_data

    report = assess_daily_data(root, env)
    if not report.price_current or not report.signal_current:
        return True
    manifest = read_sync_manifest(_out_dir(root, env))
    synced_day = _local_calendar_day_from_utc_iso(str(manifest.get("synced_at_utc") or ""))
    return synced_day != date.today().isoformat()


def ensure_between_trading_day_daily_refresh(
    root: Path,
    env: Optional[Mapping[str, str]] = None,
    *,
    force: bool = False,
    log_print: bool = True,
) -> LiveDailySyncReport:
    """Run daily OHLCV + signal sync when the calendar day changed or data is stale."""
    root = Path(root)
    if env is None:
        from aa_config_env import load_aa_env

        env = load_aa_env(root)
    env = dict(env)
    try:
        from analytics.prediction_operations import apply_prediction_profile_to_env

        env = apply_prediction_profile_to_env(root, env)
    except Exception:
        pass
    env.setdefault("AA_SKIP_DOWNLOAD_IF_CACHED", "0")

    from aa_data_freshness import assess_daily_data

    if not force and not needs_between_trading_day_refresh(root, env):
        report = assess_daily_data(root, env)
        if log_print:
            ref = report.reference_date.isoformat()
            sig = report.signal_date.isoformat() if report.signal_date else "n/a"
            px = report.price_latest.isoformat() if report.price_latest else "n/a"
            print(f"[OK] Tagesdaten aktuell — Preise {px}, Signal {sig} (Ref. {ref})")
        return LiveDailySyncReport(
            ok=report.ok,
            price_latest=report.price_latest.isoformat() if report.price_latest else None,
            signal_date=report.signal_date.isoformat() if report.signal_date else None,
        )

    if log_print:
        print("[INFO] Zwischen-Handelstag-Refresh: Preise und Signal werden aktualisiert …")
    data = assess_daily_data(root, env)
    return sync_live_daily_for_predictions(
        root,
        env,
        force_prices=force or not data.price_current,
        refresh_signal=True,
        log_print=log_print,
    )


def sync_live_daily_for_predictions(
    root: Path,
    env: Optional[Mapping[str, str]] = None,
    *,
    force_prices: bool = False,
    refresh_signal: bool = True,
    log_print: bool = True,
) -> LiveDailySyncReport:
    """Refresh live daily bars for portfolio-corresponding tickers and optionally recompute signal."""
    root = Path(root)
    if env is None:
        from aa_config_env import load_aa_env

        env = load_aa_env(root)
    env = dict(env)

    old_env_slice = {k: os.environ.get(k) for k in env}
    os.environ.update({str(k): str(v) for k, v in env.items()})

    report = LiveDailySyncReport()
    try:
        return _sync_live_daily_body(
            root,
            env,
            report,
            force_prices=force_prices,
            refresh_signal=refresh_signal,
            log_print=log_print,
        )
    finally:
        for key, prior in old_env_slice.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def _sync_live_daily_body(
    root: Path,
    env: Mapping[str, str],
    report: LiveDailySyncReport,
    *,
    force_prices: bool,
    refresh_signal: bool,
    log_print: bool,
) -> LiveDailySyncReport:
    out_dir = _out_dir(root, env)
    merged, detail = resolve_prediction_tickers(root, env)
    report.portfolio_tickers = list(detail.get("portfolio_tickers") or [])
    report.merged_ticker_count = int(detail.get("merged_ticker_count") or len(merged))

    prices_refreshed, price_latest, price_msgs = refresh_prediction_prices(
        root, env, tickers=merged, force=force_prices
    )
    report.prices_refreshed = prices_refreshed
    report.price_latest = price_latest
    report.messages.extend(price_msgs)

    quotes_doc = fetch_portfolio_live_quotes(report.portfolio_tickers)
    report.live_quotes = dict(quotes_doc.get("quotes_usd") or {})

    signal_refreshed = False
    signal_date: Optional[str] = None
    if refresh_signal:
        from aa_data_freshness import assess_daily_data
        from aa_ops_refresh import refresh_signal_portfolio

        data_report = assess_daily_data(root, env)
        signal_behind_prices = bool(
            data_report.signal_date
            and data_report.price_latest
            and data_report.signal_date < data_report.price_latest
        )
        if (
            not data_report.signal_current
            or force_prices
            or prices_refreshed
            or signal_behind_prices
        ):
            if signal_behind_prices:
                report.messages.append(
                    f"[INFO] Signal ({data_report.signal_date}) hinter Preisen "
                    f"({data_report.price_latest}) — Neuberechnung …"
                )
            else:
                report.messages.append("[INFO] Signal-Update mit frischen Tagesdaten …")
            if signal_behind_prices or prices_refreshed:
                from aa_cache_coherence import apply_price_refresh_env

                os.environ.update(apply_price_refresh_env(dict(env), prices_refreshed=True))
            signal_refreshed = refresh_signal_portfolio(
                root,
                env,
                log=lambda m: report.messages.append(m),
            )
        else:
            report.messages.append(
                f"[OK] Modell-Signal bereits aktuell ({data_report.signal_date})"
            )
        data_report = assess_daily_data(root, env)
        signal_date = data_report.signal_date.isoformat() if data_report.signal_date else None

    report.signal_refreshed = signal_refreshed
    report.signal_date = signal_date

    from aa_r3_daily_diagnosis import verify_r3_diagnosis_against_daily_data

    r3_report = verify_r3_diagnosis_against_daily_data(
        root,
        env,
        update_feedback=True,
        log_print=False,
    )
    report.r3_diagnosis_ok = r3_report.ok
    report.r3_regime_match = r3_report.regime_match
    report.r3_diagnosis_path = r3_report.manifest_path
    report.messages.extend(r3_report.messages)
    for hint in r3_report.refinement_hints:
        report.messages.append(f"  -> {hint}")

    manifest = {
        "schema_version": 1,
        "synced_at_utc": _utc_now(),
        "price_latest": price_latest,
        "signal_date": signal_date,
        "prices_refreshed": prices_refreshed,
        "signal_refreshed": signal_refreshed,
        "portfolio_tickers": report.portfolio_tickers,
        "merged_ticker_count": report.merged_ticker_count,
        "portfolio_only_tickers": detail.get("portfolio_only_added") or [],
        "live_quotes": report.live_quotes,
        "live_quotes_meta": quotes_doc,
        "r3_diagnosis_ok": r3_report.ok,
        "r3_regime_match": r3_report.regime_match,
        "r3_diagnosis_path": r3_report.manifest_path,
        "purpose": "continuous_prediction_refinement",
    }
    manifest_path = write_sync_manifest(out_dir, manifest)
    report.manifest_path = str(manifest_path)
    report.ok = price_latest is not None or bool(report.live_quotes)

    if log_print:
        for line in report.messages:
            print(line)
        print(json.dumps({k: v for k, v in asdict(report).items() if k != "messages"}, indent=2))

    return report
