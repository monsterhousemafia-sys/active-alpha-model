"""Periodic refresh of operational caches (prices, universe, signals) for Marktanalyse.exe."""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from aa_data_freshness import DailyDataReport, apply_stale_data_env, assess_daily_data

LogFn = Callable[[str], None]
PumpFn = Callable[..., None]

OPS_META_FILE = "ops_refresh_meta.json"
OPS_LOCK_FILE = ".ops_refresh.lock"
DEFAULT_LOCK_MAX_AGE_S = 7200
DEFAULT_RETRY_ATTEMPTS = 3


@dataclass
class OpsRefreshReport:
    skipped: bool = False
    lock_contended: bool = False
    prices_refreshed: bool = False
    universe_refreshed: bool = False
    signal_refreshed: bool = False
    data_report: Optional[DailyDataReport] = None
    env_updates: Dict[str, str] = field(default_factory=dict)


def _yes(env: Mapping[str, str], key: str, default: str = "1") -> bool:
    return str(env.get(key, default) or default).strip().lower() not in {"0", "false", "no", "off"}


def resolve_out_dir(root: Path, env: Mapping[str, str]) -> Path:
    rel = str(env.get("AA_BACKTEST_OUT_DIR", "model_output") or "model_output")
    path = Path(rel)
    return path if path.is_absolute() else root / path


class AutopilotOutDirError(Exception):
    """Configured output directory cannot be resolved safely."""


def resolve_autopilot_out_dir(
    root: Path,
    env: Optional[Mapping[str, str]] = None,
) -> Tuple[Path, Dict[str, str]]:
    """Resolve production out_dir from env or project BAT config; fail closed on ambiguity."""
    root = Path(root)
    merged: Dict[str, str] = {str(k): str(v) for k, v in (env or os.environ).items()}
    out_key = "AA_BACKTEST_OUT_DIR"
    if not str(merged.get(out_key, "") or "").strip():
        try:
            from aa_config_env import parse_aa_env_files

            for key, val in parse_aa_env_files(root).items():
                if key not in merged or not str(merged.get(key, "") or "").strip():
                    merged[key] = val
        except ImportError:
            pass
    rel = str(merged.get(out_key, "") or "").strip()
    if not rel:
        raise AutopilotOutDirError(
            "AA_BACKTEST_OUT_DIR not configured; refusing silent fallback to model_output/"
        )
    path = Path(rel)
    return (path if path.is_absolute() else root / path), merged


def ops_meta_path(out_dir: Path) -> Path:
    return Path(out_dir) / OPS_META_FILE


def read_ops_meta(out_dir: Path) -> Dict[str, object]:
    path = ops_meta_path(out_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_ops_meta(out_dir: Path, patch: Mapping[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = read_ops_meta(out_dir)
    meta.update(patch)
    meta["updated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    ops_meta_path(out_dir).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def ops_refresh_due(meta: Mapping[str, object], *, interval_hours: int) -> bool:
    if interval_hours <= 0:
        return True
    raw = str(meta.get("last_success_at_utc", "") or "")
    if not raw:
        return True
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        return age_hours >= float(interval_hours)
    except Exception:
        return True


def apply_post_price_refresh_env(env: Dict[str, str], *, prices_refreshed: bool) -> Dict[str, str]:
    from aa_cache_coherence import apply_price_refresh_env

    return apply_price_refresh_env(env, prices_refreshed=prices_refreshed)


class RefreshLock:
    """Prevent overlapping refresh jobs (scheduler + EXE)."""

    def __init__(self, root: Path, *, max_age_s: int = DEFAULT_LOCK_MAX_AGE_S) -> None:
        self.path = Path(root) / OPS_LOCK_FILE
        self.max_age_s = int(max_age_s)

    def acquire(self) -> bool:
        if self.path.is_file():
            age = time.time() - self.path.stat().st_mtime
            if age < self.max_age_s:
                return False
            self.path.unlink(missing_ok=True)
        self.path.write_text(f"{os.getpid()} marktanalyse", encoding="utf-8")
        return True

    def owner_hint(self) -> str:
        if not self.path.is_file():
            return ""
        try:
            return self.path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def release(self) -> None:
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> "RefreshLock":
        if not self.acquire():
            raise RuntimeError("Refresh läuft bereits (Lock aktiv)")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def refresh_price_panel_with_retry(
    root: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    pump_ui_fn: Optional[PumpFn] = None,
    attempts: int = DEFAULT_RETRY_ATTEMPTS,
) -> bool:
    tries = max(int(attempts), 1)
    for attempt in range(1, tries + 1):
        if refresh_price_panel(root, env, log=log, pump_ui_fn=pump_ui_fn):
            return True
        if attempt < tries:
            wait = 5 * attempt
            log(f"[INFO] Preis-Update Retry in {wait}s ({attempt}/{tries}) …")
            time.sleep(wait)
    return False


def refresh_price_panel(
    root: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    pump_ui_fn: Optional[PumpFn] = None,
) -> bool:
    from aa_config import BacktestConfig, parse_args
    from aa_config_env import build_backtest_argv
    from aa_features import download_data
    from aa_universe import load_tickers

    old_argv = sys.argv
    try:
        argv = build_backtest_argv(dict(env))
        sys.argv = argv
        args = parse_args()
        cfg = BacktestConfig.from_args(args)
        tickers = load_tickers(args)
        out_dir = resolve_out_dir(root, env)
        out_dir.mkdir(parents=True, exist_ok=True)
        log(f"[INFO] Preis-Update: lade Kurse für {len(tickers)} Ticker ab {cfg.start} …")
        if pump_ui_fn is not None:
            pump_ui_fn(force=True)
        cfg.skip_download_if_cached = False
        cfg.write_price_cache = True
        download_data(tickers, cfg.start, dashboard=None, cfg=cfg, out_dir=out_dir)
        latest = assess_daily_data(root, env).price_latest
        if latest is not None:
            log(f"[OK] Preis-Cache aktualisiert — Stand {latest.isoformat()}")
        else:
            log("[OK] Preis-Cache aktualisiert")
        return True
    except Exception as exc:
        log(f"[WARN] Preis-Update fehlgeschlagen: {exc}")
        return False
    finally:
        sys.argv = old_argv


def refresh_universe_if_needed(root: Path, env: Mapping[str, str], *, log: LogFn) -> bool:
    from aa_universe import (
        cached_snapshot_age_days,
        fetch_wikipedia_sp500_components,
        latest_cached_sp500_path,
        save_universe_snapshot,
    )

    source = str(env.get("AA_PAPER_TICKER_SOURCE", "") or env.get("AA_BACKTEST_TICKER_SOURCE", "")).strip().lower()
    if source not in {"sp500_auto", "wikipedia_sp500", "slickcharts_sp500"}:
        return False

    cache_rel = str(env.get("AA_TICKER_CACHE_DIR", "universe_snapshots") or "universe_snapshots")
    cache_dir = Path(cache_rel) if Path(cache_rel).is_absolute() else root / cache_rel
    max_age = int(str(env.get("AA_TICKER_CACHE_MAX_AGE_DAYS", "7") or "7"))
    latest = latest_cached_sp500_path(cache_dir)
    if latest is not None:
        age = cached_snapshot_age_days(latest)
        if age is not None and age <= max_age:
            log(f"[OK] Universum-Cache: {latest.name} ({age:.1f} Tage alt)")
            return False

    log("[INFO] Universum-Cache: Online-Update …")
    try:
        from aa_sector_reference import sync_sector_reference_after_universe

        records = fetch_wikipedia_sp500_components()
        path = save_universe_snapshot(records, cache_dir, source_detail="wikipedia_sp500")
        valid_from = path.stem.replace("sp500_", "")[:10] if path.stem.startswith("sp500_") else ""
        if len(valid_from) != 10:
            valid_from = datetime.now(timezone.utc).date().isoformat()
        sector_result = sync_sector_reference_after_universe(
            records,
            valid_from=valid_from,
            source_detail="wikipedia_sp500",
            root=root,
        )
        with_gics = sum(1 for r in records if str(r.get("sector_gics") or "").strip())
        log(
            f"[OK] Universum-Cache aktualisiert ({path.name}, {len(records)} Titel, "
            f"Sektoren {with_gics}/{len(records)})"
        )
        log(
            f"[OK] Sektor-Referenz: {sector_result.get('row_count', 0)} Zeilen "
            f"(+{sector_result.get('added', 0)})"
        )
        return True
    except Exception as exc:
        log(f"[WARN] Universum-Update fehlgeschlagen: {exc}")
        return False


def refresh_signal_portfolio(
    root: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    pump_ui_fn: Optional[PumpFn] = None,
) -> bool:
    from time import monotonic

    from aa_config import BacktestConfig, apply_capital_curve_policy_to_config, enforce_reproducibility_inputs, parse_args
    from aa_config_env import build_backtest_argv
    from aa_dashboard import RunDashboard
    from aa_frozen import apply_frozen_runtime_config
    from aa_runtime import execute_run

    old_argv = sys.argv
    old_gui = os.environ.get("AA_GUI")
    try:
        os.environ.update(dict(env))
        os.environ["AA_GUI"] = "0"
        os.environ["AA_NO_PLOT"] = "1"
        argv = build_backtest_argv({**os.environ, **dict(env)})
        idx = argv.index("--mode")
        argv[idx + 1] = "signal"
        sys.argv = argv
        args = parse_args()
        cfg = BacktestConfig.from_args(args)
        cfg = apply_capital_curve_policy_to_config(cfg)
        enforce_reproducibility_inputs(cfg)
        apply_frozen_runtime_config(cfg)
        out_dir = resolve_out_dir(root, env)
        out_dir.mkdir(parents=True, exist_ok=True)
        log("[INFO] Signal-Update: berechne latest_target_portfolio.csv …")
        if pump_ui_fn is not None:
            pump_ui_fn(force=True)
        dashboard = RunDashboard(enabled=False, title="Signal-Refresh", use_rich=False)
        result = execute_run(args, cfg, dashboard, out_dir=out_dir, run_started=monotonic())
        portfolio = out_dir / "latest_target_portfolio.csv"
        if result.success and portfolio.is_file():
            signal = assess_daily_data(root, env).signal_date
            if signal is not None:
                log(f"[OK] Modell-Signal aktualisiert — {signal.isoformat()}")
            else:
                log("[OK] Modell-Signal aktualisiert")
            return True
        log("[WARN] Signal-Update fehlgeschlagen oder Portfolio fehlt")
        return False
    except Exception as exc:
        log(f"[WARN] Signal-Update fehlgeschlagen: {exc}")
        return False
    finally:
        sys.argv = old_argv
        if old_gui is None:
            os.environ.pop("AA_GUI", None)
        else:
            os.environ["AA_GUI"] = old_gui


def run_ops_refresh(
    root: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    pump_ui_fn: Optional[PumpFn] = None,
    force: bool = False,
    include_signal: bool = False,
    data_report: Optional[DailyDataReport] = None,
) -> OpsRefreshReport:
    """Refresh stale operational data so Marktanalyse.exe can reuse caches."""
    out_dir = resolve_out_dir(root, env)
    meta = read_ops_meta(out_dir)
    interval_hours = int(str(env.get("AA_OPS_REFRESH_INTERVAL_HOURS", "24") or "24"))
    report = data_report or assess_daily_data(root, env)
    auto_refresh = _yes(env, "AA_AUTO_OPS_REFRESH", default="1")

    if not force and report.ok and not ops_refresh_due(meta, interval_hours=interval_hours):
        log("[OK] Betriebsdaten aktuell — periodisches Update übersprungen")
        updates = apply_stale_data_env(dict(env), report)
        updates.setdefault("AA_SKIP_DOWNLOAD_IF_CACHED", "1")
        return OpsRefreshReport(skipped=True, data_report=report, env_updates=updates)

    lock = RefreshLock(root)
    if not lock.acquire():
        owner = lock.owner_hint()
        detail = f" ({owner})" if owner else ""
        log(f"[INFO] Betriebsdaten-Refresh übersprungen — anderer Lauf aktiv{detail}")
        updates = apply_stale_data_env(dict(env), report)
        updates.setdefault("AA_SKIP_DOWNLOAD_IF_CACHED", "1")
        return OpsRefreshReport(skipped=True, lock_contended=True, data_report=report, env_updates=updates)

    try:
        return _run_ops_refresh_locked(
            root,
            env,
            log=log,
            pump_ui_fn=pump_ui_fn,
            force=force,
            include_signal=include_signal,
            report=report,
            auto_refresh=auto_refresh,
            out_dir=out_dir,
            meta=meta,
            interval_hours=interval_hours,
        )
    finally:
        lock.release()


def _run_ops_refresh_locked(
    root: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    pump_ui_fn: Optional[PumpFn],
    force: bool,
    include_signal: bool,
    report: DailyDataReport,
    auto_refresh: bool,
    out_dir: Path,
    meta: Dict[str, object],
    interval_hours: int,
) -> OpsRefreshReport:
    if not auto_refresh and not force:
        log("[INFO] Auto-Refresh deaktiviert (AA_AUTO_OPS_REFRESH=0)")
        updates = apply_stale_data_env(dict(env), report)
        return OpsRefreshReport(skipped=True, data_report=report, env_updates=updates)

    log("[INFO] Betriebsdaten-Refresh startet …")
    prices_refreshed = False
    universe_refreshed = False
    signal_refreshed = False

    if not report.price_current or force:
        prices_refreshed = refresh_price_panel_with_retry(root, env, log=log, pump_ui_fn=pump_ui_fn)
    else:
        log(f"[OK] Preis-Cache bereits tagesaktuell ({report.price_latest})")

    universe_refreshed = refresh_universe_if_needed(root, env, log=log)

    sector_refreshed = False
    sector_summary = ""
    try:
        from aa_sector_reference import ensure_sector_reference_fresh

        sector_out = ensure_sector_reference_fresh(root, env)
        sector_refreshed = bool(sector_out.get("refreshed"))
        sector_summary = str(sector_out.get("message_de") or "")
        if sector_summary:
            log(sector_summary)
    except Exception as exc:
        log(f"[WARN] Sektor-Referenz-Refresh: {exc}")

    report = assess_daily_data(root, env)
    if include_signal and not report.signal_current:
        signal_refreshed = refresh_signal_portfolio(root, env, log=log, pump_ui_fn=pump_ui_fn)
        report = assess_daily_data(root, env)
    elif not report.signal_current and not include_signal:
        log("[INFO] Modell-Signal wird im Analyse-Lauf aktualisiert")

    updates = apply_stale_data_env(dict(env), report)
    updates = apply_post_price_refresh_env(updates, prices_refreshed=prices_refreshed)
    if report.ok:
        updates["AA_SKIP_DOWNLOAD_IF_CACHED"] = "1"

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta_patch: Dict[str, object] = {
        "last_attempt_at_utc": now_iso,
        "price_latest": report.price_latest.isoformat() if report.price_latest else None,
        "signal_date": report.signal_date.isoformat() if report.signal_date else None,
        "prices_refreshed": prices_refreshed,
        "universe_refreshed": universe_refreshed,
        "sector_reference_refreshed": sector_refreshed,
        "signal_refreshed": signal_refreshed,
        "ok": report.ok,
    }
    if report.ok:
        meta_patch["last_success_at_utc"] = now_iso
    else:
        meta_patch["last_error"] = "data_not_current_after_refresh"
    write_ops_meta(out_dir, meta_patch)

    if report.ok:
        log("[OK] Betriebsdaten-Refresh abgeschlossen — EXE nutzt aktuelle Caches")
    else:
        log("[INFO] Betriebsdaten-Refresh abgeschlossen — verbleibende Updates im Analyse-Lauf")

    return OpsRefreshReport(
        skipped=False,
        prices_refreshed=prices_refreshed,
        universe_refreshed=universe_refreshed,
        signal_refreshed=signal_refreshed,
        data_report=report,
        env_updates=updates,
    )
