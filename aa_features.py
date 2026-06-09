from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, normalize_yfinance_ticker, non_tradable_benchmark_tickers
from aa_execution import _hash_file, effective_alpha_target_roundtrip_decimal
from aa_constants import (
    FEATURE_COLUMNS,
    deduplicate_dataframe_columns,
    ticker_to_correlation_cluster,
    ticker_to_issuer,
    ticker_to_sector,
)
from aa_dashboard import RunDashboard
from aa_parallel import (
    ProcessPoolSession,
    _ACTIVE_POOL,
    _CTX,
    _mp_pool,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    prepare_features_for_parallel_runtime,
    resolve_parallel_workers,
    resolve_pool_chunksize,
)
from aa_universe import apply_membership_filter_to_features


def resolve_shared_cache_root(cfg: BacktestConfig) -> Path:
    """Return shared cache root if configured, otherwise the run out_dir."""
    raw = str(getattr(cfg, "shared_cache_dir", "") or "").strip()
    if not raw:
        raw = os.environ.get("AA_SHARED_CACHE_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path(str(getattr(cfg, "out_dir", "model_output") or "model_output"))


def using_shared_cache_dir(cfg: BacktestConfig) -> bool:
    return bool(str(getattr(cfg, "shared_cache_dir", "") or "").strip() or os.environ.get("AA_SHARED_CACHE_DIR", "").strip())


def resolve_feature_cache_dir(cfg: BacktestConfig, n_tickers: int, out_dir: Path | str | None = None) -> Path:
    if using_shared_cache_dir(cfg):
        root = resolve_shared_cache_root(cfg)
        fp = _feature_build_fingerprint(cfg, n_tickers)
        return root / "features" / f"fp_{fp}"
    if out_dir is not None:
        return Path(out_dir)
    return resolve_shared_cache_root(cfg)


def resolve_price_cache_dir(cfg: BacktestConfig) -> Path:
    root = resolve_shared_cache_root(cfg)
    if using_shared_cache_dir(cfg):
        return root / "price"
    return root / "price_cache"


def _read_cache_meta_summary(meta_path: Path, *, price_ttl_hours: Optional[int] = None) -> str:
    if not meta_path.exists():
        return "missing"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return "meta_read_error"
    parts = [f"schema={meta.get('schema_version')}"]
    fp = str(meta.get("fingerprint", ""))
    if fp:
        parts.append(f"fp={fp[:12]}")
    created = meta.get("created_at_utc")
    if created:
        parts.append(f"created={created}")
    tickers = meta.get("tickers_loaded")
    if tickers is not None:
        parts.append(f"tickers={tickers}")
    rows = meta.get("rows")
    if rows is not None:
        parts.append(f"rows={rows}")
    if price_ttl_hours is not None and not _price_cache_is_fresh(meta, int(price_ttl_hours)):
        parts.append("TTL=stale")
    return ", ".join(parts)


def collect_cache_status_lines(cfg: BacktestConfig, out_dir: Path | str, *, n_tickers: int = 0) -> List[str]:
    """Summarize on-disk caches for an out_dir / shared-cache layout (no download)."""
    out_path = Path(out_dir)
    shared_root = resolve_shared_cache_root(cfg)
    feat_dir = resolve_feature_cache_dir(cfg, n_tickers, out_dir=out_path) if n_tickers > 0 else out_path
    if using_shared_cache_dir(cfg) and n_tickers <= 0:
        feat_glob = list((shared_root / "features").glob("fp_*/feature_cache_meta.json")) if (shared_root / "features").exists() else []
        feat_note = f"{len(feat_glob)} fingerprint dir(s)" if feat_glob else "no fingerprint dirs"
    else:
        feat_path, ret_path, meta_path = _feature_cache_paths(feat_dir)
        feat_note = _read_cache_meta_summary(meta_path)
        if n_tickers > 0:
            _pack, reject = _try_load_feature_cache(out_path, cfg, n_tickers)
            feat_note += f" | load={'ok' if _pack else reject}"

    price_dir = resolve_price_cache_dir(cfg)
    price_panel, price_meta = _price_cache_paths(price_dir)
    ttl = int(getattr(cfg, "price_cache_ttl_hours", 24) or 24)
    pred_meta = out_path / "prediction_cache_meta.json"
    pred_pkl = out_path / "prediction_cache.pkl"

    lines = [
        "Cache Status",
        "============",
        f"out_dir: {out_path.resolve()}",
        f"shared_cache: {shared_root.resolve() if using_shared_cache_dir(cfg) else '(off)'}",
        f"feature_cache ({feat_dir.resolve()}): {feat_note}",
        f"price_cache ({price_dir.resolve()}): panel={'yes' if price_panel.exists() else 'no'}; {_read_cache_meta_summary(price_meta, price_ttl_hours=ttl)}",
        f"prediction_cache ({out_path.resolve()}): pkl={'yes' if pred_pkl.exists() else 'no'}; {_read_cache_meta_summary(pred_meta)}",
        "flags:",
        f"  reuse_feature_cache={cfg.reuse_feature_cache} force_rebuild_features={cfg.force_rebuild_features}",
        f"  reuse_prediction_cache={cfg.reuse_prediction_cache} skip_download_if_cached={cfg.skip_download_if_cached}",
    ]
    if (out_path / "phase_timings.json").exists():
        lines.append(f"phase_timings: {out_path / 'phase_timings.json'}")
    return lines


def build_or_load_features(
    cfg: BacktestConfig,
    tickers: List[str],
    out_dir: Path,
    *,
    pool_session: ProcessPoolSession,
    dashboard: Optional[RunDashboard] = None,
    phase_timings: Optional["PhaseTimings"] = None,
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, bool]:
    """Load feature cache or download/build features, then bind the process pool for later phases.

    Returns (features, benchmark_close, returns, loaded_from_cache).
    """
    from aa_execution import PhaseTimings

    timings = phase_timings or PhaseTimings()
    cached_pack = None
    cache_reject_reason = None
    if getattr(cfg, "reuse_feature_cache", False):
        if getattr(cfg, "force_rebuild_features", False):
            if dashboard is not None:
                dashboard.ok("Feature-Cache wird ignoriert (--force-rebuild-features)")
        else:
            timings.start("feature_cache_load")
            cached_pack, cache_reject_reason = _try_load_feature_cache(out_dir, cfg, len(tickers))
            timings.stop("feature_cache_load")
            if cache_reject_reason and dashboard is not None:
                dashboard.warn(f"Feature-Cache ungültig ({cache_reject_reason}), Neubau …")
    if cached_pack is not None:
        features, bench_close, returns = cached_pack
        if dashboard is not None:
            dashboard.ok(f"Feature-Cache geladen: {len(features):,} Zeilen, {len(tickers)} Ticker")
            dashboard.complete_pipeline_step("features")
    else:
        timings.start("download")
        data = download_data(tickers, cfg.start, dashboard, cfg=cfg, out_dir=out_dir)
        timings.stop("download")
        timings.start("feature_build")
        features, bench_close, returns = build_feature_table(
            data, cfg.benchmark, cfg, dashboard, pool_session=pool_session
        )
        features = prepare_features_for_parallel_runtime(features, cfg)
        timings.stop("feature_build")
        if getattr(cfg, "write_feature_cache", True):
            timings.start("feature_cache_save")
            _save_feature_cache(out_dir, cfg, len(tickers), features, returns)
            timings.stop("feature_cache_save")
            if dashboard is not None:
                dashboard.ok("Feature-Cache für schnelle Wiederholungsläufe gespeichert")
    pool_session.load_backtest_state(features, returns)
    return features, bench_close, returns, cached_pack is not None


def download_data(
    tickers: List[str],
    start: str,
    dashboard: Optional[RunDashboard] = None,
    *,
    cfg: Optional[BacktestConfig] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, pd.DataFrame]:
    from aa_fictive_daily_data import download_fictive_data, is_fictive_price_source

    if is_fictive_price_source(cfg, os.environ):
        return download_fictive_data(tickers, start, dashboard, cfg=cfg, out_dir=out_dir)

    try:
        import yfinance as yf
    except ImportError as e:
        raise SystemExit("yfinance is not installed. Run: pip install -r requirements.txt") from e

    cache_dir = resolve_price_cache_dir(cfg) if cfg is not None else Path(out_dir or "model_output") / "price_cache"
    ttl_hours = int(getattr(cfg, "price_cache_ttl_hours", 24) or 24) if cfg is not None else 24
    if cfg is not None and bool(getattr(cfg, "skip_download_if_cached", False)):
        cached = _load_price_cache(cache_dir, tickers, start, ttl_hours)
        if cached is not None:
            if dashboard is not None:
                dashboard.ok(f"Preis-Cache geladen: {len(cached)} Ticker ab {start}")
            else:
                print(f"Loaded price cache: {len(cached)} tickers from {start}")
            return cached
        if dashboard is not None:
            dashboard.warn("Preis-Cache ungültig oder abgelaufen, Download …")

    if dashboard is not None:
        dashboard.start_phase("Marktdaten laden", total=1, step=f"{len(tickers)} Ticker ab {start}")
        dashboard.set_status(ticker=f"{len(tickers)} Symbole")
        from aa_ui_pump import pump_ui

        pump_ui(force=True)
    else:
        print(f"Downloading {len(tickers)} tickers from {start} ...")
    end = (date.today() + timedelta(days=1)).isoformat()
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    if raw.empty:
        raise RuntimeError("No data returned. Check tickers, start date, and internet connection.")

    data: Dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = raw.columns.get_level_values(0)
        for tk in tickers:
            if tk in level0:
                df = raw[tk].copy()
            else:
                continue
            if "Close" in df.columns and df["Close"].notna().sum() > 250:
                data[tk] = df[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]].dropna(how="all")
    else:
        # Single ticker case
        tk = tickers[0]
        data[tk] = raw[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]].dropna(how="all")

    missing = [tk for tk in tickers if tk not in data]
    if missing:
        msg = f"no usable data for {len(missing)} tickers: {missing[:10]}{'...' if len(missing) > 10 else ''}"
        if dashboard is not None:
            dashboard.warn(msg)
        else:
            print(f"Warning: {msg}")
    if dashboard is not None:
        dashboard.advance_phase(1, step=f"{len(data)} Datenreihen geladen")
        dashboard.finish_phase()
    if cfg is not None and bool(getattr(cfg, "write_price_cache", True)):
        try:
            _save_price_cache(cache_dir, tickers, start, data)
            if dashboard is not None:
                dashboard.ok(f"Preis-Cache gespeichert: {cache_dir}")
        except Exception as exc:
            if dashboard is not None:
                dashboard.warn(f"Preis-Cache konnte nicht gespeichert werden: {exc}")
    return data


def safe_rank_pct(s: pd.Series, ascending: bool = True) -> pd.Series:
    if s.notna().sum() <= 1:
        return pd.Series(0.5, index=s.index)
    return s.rank(pct=True, ascending=ascending).fillna(0.5)


def add_cross_sectional_rank_scores(g: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank score for one trading day (picklable for process pools)."""
    out = g.copy()
    if "in_universe" in out.columns:
        pool = out.loc[out["in_universe"].fillna(False)]
    else:
        pool = out
    if pool.empty:
        out["rank_score"] = 0.5
        return out

    def _rank_col(col: str, ascending: bool) -> pd.Series:
        scores = pd.Series(0.5, index=out.index, dtype=float)
        ranked = safe_rank_pct(pool[col], ascending=ascending)
        scores.loc[pool.index] = ranked.values
        return scores

    mom = _rank_col("mom_252_21", ascending=True)
    mom2 = _rank_col("mom_126_21", ascending=True)
    mom3 = _rank_col("mom_63_21", ascending=True)
    rev = _rank_col("rev_5", ascending=True)
    trend = 0.5 * out["trend_50"].fillna(0) + 0.5 * out["trend_200"].fillna(0)
    lowvol = _rank_col("vol_20", ascending=False)
    lowivol = _rank_col("idio_vol_63", ascending=False)
    relstr = _rank_col("rel_strength_63", ascending=True)
    sector_rel = _rank_col("sector_rel_strength_63", ascending=True)
    liq = _rank_col("adv_20_log", ascending=True)
    out["rank_score"] = (
        0.26 * mom + 0.17 * mom2 + 0.10 * mom3 + 0.08 * rev + 0.17 * trend
        + 0.14 * relstr + 0.04 * sector_rel + 0.02 * lowvol + 0.01 * lowivol + 0.01 * liq
    )
    return out


def _rank_score_date_chunk(groups: List[Tuple[Any, pd.DataFrame]]) -> List[pd.DataFrame]:
    _parallel_worker_bootstrap()
    ranked: List[pd.DataFrame] = []
    for dt, g in groups:
        out = add_cross_sectional_rank_scores(g)
        out["date"] = pd.Timestamp(dt)
        ranked.append(out)
    return ranked


def build_feature_by_date(features: pd.DataFrame) -> Dict[pd.Timestamp, pd.DataFrame]:
    """Build date-indexed feature snapshots once (read-only in workers)."""
    return {pd.Timestamp(k): v for k, v in features.groupby("date", sort=False)}


FEATURE_CACHE_SCHEMA_VERSION = 2


def _membership_file_fingerprint(cfg: BacktestConfig) -> str:
    path = Path(str(getattr(cfg, "membership_file", "ticker_membership.csv")))
    if not path.is_absolute():
        path = Path.cwd() / path
    digest = _hash_file(path)
    return digest[:16] if digest else "missing"


def _feature_build_fingerprint(cfg: BacktestConfig, n_tickers: int) -> str:
    payload = "|".join([
        str(FEATURE_CACHE_SCHEMA_VERSION),
        str(cfg.start),
        str(cfg.benchmark),
        str(getattr(cfg, "universe_mode", "")),
        str(getattr(cfg, "universe_top_n", "")),
        str(getattr(cfg, "universe_adv_lookback", "")),
        str(getattr(cfg, "universe_min_adv", "")),
        str(getattr(cfg, "universe_min_price", "")),
        str(getattr(cfg, "universe_min_history_days", "")),
        str(getattr(cfg, "ticker_source", "")),
        str(getattr(cfg, "ticker_snapshot_date", "")),
        str(getattr(cfg, "membership_mode", "")),
        _membership_file_fingerprint(cfg),
        str(getattr(cfg, "horizon", "")),
        str(n_tickers),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _feature_cache_paths(cache_dir: Path) -> Tuple[Path, Path, Path]:
    base = Path(cache_dir)
    return base / "feature_cache.parquet", base / "returns_cache.parquet", base / "feature_cache_meta.json"


def _try_load_feature_cache(
    out_dir: Path,
    cfg: BacktestConfig,
    n_tickers: int,
) -> Tuple[Optional[Tuple[pd.DataFrame, pd.Series, pd.DataFrame]], Optional[str]]:
    feat_path, ret_path, meta_path = _feature_cache_paths(resolve_feature_cache_dir(cfg, n_tickers, out_dir=out_dir))
    if not (feat_path.exists() and ret_path.exists() and meta_path.exists()):
        return None, "missing_files"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None, "meta_read_error"
    schema = meta.get("schema_version")
    if schema != FEATURE_CACHE_SCHEMA_VERSION:
        return None, f"schema_version (cached={schema!r}, expected={FEATURE_CACHE_SCHEMA_VERSION})"
    expected_fp = _feature_build_fingerprint(cfg, n_tickers)
    if str(meta.get("fingerprint", "")) != expected_fp:
        return None, "fingerprint_mismatch"
    try:
        features = pd.read_parquet(feat_path)
        returns = pd.read_parquet(ret_path)
        if "date" in features.columns:
            features["date"] = pd.to_datetime(features["date"])
        if not isinstance(returns.index, pd.DatetimeIndex):
            returns.index = pd.to_datetime(returns.index)
        bench_tk = normalize_yfinance_ticker(str(cfg.benchmark))
        if bench_tk in returns.columns and "close" in features.columns:
            bench_close = features.loc[features["ticker"].eq(bench_tk)].sort_values("date").set_index("date")["close"]
        else:
            bench_close = returns[bench_tk] if bench_tk in returns.columns else pd.Series(dtype=float)
        return (features, bench_close, returns), None
    except Exception:
        return None, "parquet_read_error"


def _load_feature_cache(out_dir: Path, cfg: BacktestConfig, n_tickers: int) -> Optional[Tuple[pd.DataFrame, pd.Series, pd.DataFrame]]:
    pack, _reject = _try_load_feature_cache(out_dir, cfg, n_tickers)
    return pack


def _save_feature_cache(
    out_dir: Path,
    cfg: BacktestConfig,
    n_tickers: int,
    features: pd.DataFrame,
    returns: pd.DataFrame,
) -> None:
    feat_path, ret_path, meta_path = _feature_cache_paths(resolve_feature_cache_dir(cfg, n_tickers, out_dir=out_dir))
    feat_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(feat_path, index=False)
    returns.to_parquet(ret_path)
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": FEATURE_CACHE_SCHEMA_VERSION,
                "fingerprint": _feature_build_fingerprint(cfg, n_tickers),
                "rows": int(len(features)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


PREDICTION_CACHE_SCHEMA_VERSION = 3
PRICE_CACHE_SCHEMA_VERSION = 1


def _prediction_cache_paths(out_dir: Path) -> Tuple[Path, Path]:
    base = Path(out_dir)
    return base / "prediction_cache.pkl", base / "prediction_cache_meta.json"


def _prediction_cluster_selection_fingerprint(cfg: BacktestConfig) -> str:
    """Cluster overlay settings that change Phase-A portfolio selection.

    Diagnostic-only overlays (static / dynamic_diagnostic with static_only caps)
    do not affect correlation_cluster used for selection and are excluded so
    prediction caches stay valid across reporting-only cluster mode changes.
    """
    mode = str(getattr(cfg, "cluster_mode", "static") or "static").lower().strip()
    constraint = str(getattr(cfg, "cluster_constraint_mode", "static_only") or "static_only").lower().strip()
    if mode in {"static", "dynamic_diagnostic"} and constraint == "static_only":
        return "cluster_selection_inactive"
    return "|".join([
        mode,
        constraint,
        str(getattr(cfg, "dynamic_cluster_window_short", "")),
        str(getattr(cfg, "dynamic_cluster_window_long", "")),
        str(getattr(cfg, "dynamic_cluster_corr_threshold", "")),
        str(getattr(cfg, "dynamic_cluster_min_overlap", "")),
    ])


def _prediction_config_fingerprint(cfg: BacktestConfig) -> str:
    """Model/portfolio settings that invalidate cached ML predictions when changed."""
    payload = "|".join([
        str(getattr(cfg, "alpha_model_mode", "")),
        str(getattr(cfg, "train_years", "")),
        str(getattr(cfg, "min_train_rows", "")),
        str(getattr(cfg, "horizon", "")),
        str(getattr(cfg, "rebalance_every", "")),
        str(getattr(cfg, "random_seed", "")),
        str(getattr(cfg, "top_k", "")),
        str(getattr(cfg, "max_position", "")),
        str(getattr(cfg, "max_sector", "")),
        str(getattr(cfg, "max_issuer", "")),
        str(getattr(cfg, "max_correlation_cluster", "")),
        str(getattr(cfg, "static_cluster_cap", "")),
        str(getattr(cfg, "dynamic_cluster_cap", "")),
        str(getattr(cfg, "cluster_constraint_mode", "")),
        str(getattr(cfg, "max_portfolio_beta", "")),
        str(getattr(cfg, "dynamic_beta_risk_off", "")),
        str(getattr(cfg, "dynamic_beta_normal", "")),
        str(getattr(cfg, "dynamic_beta_risk_on", "")),
        str(getattr(cfg, "dynamic_beta_strong", "")),
        str(getattr(cfg, "max_gross_exposure", "")),
        str(getattr(cfg, "good_regime_exposure", "")),
        str(getattr(cfg, "bad_regime_exposure", "")),
        str(getattr(cfg, "risk_on_exposure_floor", "")),
        str(getattr(cfg, "min_adv", "")),
        str(getattr(cfg, "max_ann_vol", "")),
        str(getattr(cfg, "min_edge", "")),
        str(getattr(cfg, "lcb_z", "")),
        str(getattr(cfg, "lcb_scale", "")),
        str(getattr(cfg, "exposure_controller", "")),
        str(getattr(cfg, "risk_regime_mode", "")),
        _prediction_cluster_selection_fingerprint(cfg),
        str(getattr(cfg, "beta_cap_mode", "")),
        str(getattr(cfg, "cash_filler_mode", "")),
        str(getattr(cfg, "cash_filler_max_position", "")),
        str(getattr(cfg, "cash_filler_min_score", "")),
        str(getattr(cfg, "benchmark_completion_ticker", "")),
        str(getattr(cfg, "benchmark_completion_max_weight", "")),
        str(getattr(cfg, "low_beta_filler_max_position", "")),
        str(getattr(cfg, "low_beta_filler_beta_max", "")),
        str(getattr(cfg, "low_beta_filler_min_score", "")),
        str(getattr(cfg, "low_beta_filler_max_vol_63", "")),
        str(getattr(cfg, "exposure_recovery_policy", "")),
        str(getattr(cfg, "risk_off_selection_mode", "")),
        str(getattr(cfg, "risk_off_momentum_variant", "")),
        str(getattr(cfg, "risk_off_momentum_weight", "")),
        str(getattr(cfg, "risk_off_gate_mode", "")),
        str(getattr(cfg, "risk_off_momentum_rescue_quantile", "")),
        str(getattr(cfg, "risk_off_force_exit_enabled", False)),
        str(getattr(cfg, "ml_retrain_every", 1)),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _prediction_build_fingerprint(
    cfg: BacktestConfig,
    n_tickers: int,
    rebalance_dates: List[pd.Timestamp],
) -> str:
    rbs = [pd.Timestamp(d) for d in rebalance_dates[:-1]]
    first_rb = str(rbs[0]) if rbs else ""
    last_rb = str(rbs[-1]) if rbs else ""
    payload = "|".join([
        str(PREDICTION_CACHE_SCHEMA_VERSION),
        _feature_build_fingerprint(cfg, n_tickers),
        _prediction_config_fingerprint(cfg),
        str(len(rbs)),
        first_rb,
        last_rb,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _try_load_prediction_cache(
    out_dir: Path,
    cfg: BacktestConfig,
    n_tickers: int,
    rebalance_dates: List[pd.Timestamp],
) -> Tuple[Optional[Dict[pd.Timestamp, Dict[str, Any]]], Optional[str], List[pd.Timestamp]]:
    """Load cached predictions. Returns (cache, reject_reason, missing_rebalances_for_incremental)."""
    cache_path, meta_path = _prediction_cache_paths(out_dir)
    if not (cache_path.exists() and meta_path.exists()):
        return None, "missing_files", []
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None, "meta_read_error", []
    if meta.get("schema_version") != PREDICTION_CACHE_SCHEMA_VERSION:
        return None, f"schema_version (cached={meta.get('schema_version')!r}, expected={PREDICTION_CACHE_SCHEMA_VERSION})", []

    required = [pd.Timestamp(d) for d in rebalance_dates[:-1]]
    feature_fp = _feature_build_fingerprint(cfg, n_tickers)
    config_fp = _prediction_config_fingerprint(cfg)
    legacy_fp = _prediction_build_fingerprint(cfg, n_tickers, rebalance_dates)
    cached_legacy_fp = str(meta.get("fingerprint", ""))
    cached_config_fp = str(meta.get("config_fingerprint", "") or "")
    cached_feature_fp = str(meta.get("feature_fingerprint", "") or "")

    if cached_config_fp:
        if cached_config_fp != config_fp:
            return None, "config_mismatch", []
        if cached_feature_fp and cached_feature_fp != feature_fp:
            return None, "data_mismatch", []
    elif cached_legacy_fp != legacy_fp:
        return None, "fingerprint_mismatch", []

    try:
        with cache_path.open("rb") as f:
            raw = pickle.load(f)
        results: Dict[pd.Timestamp, Dict[str, Any]] = {}
        for key, value in raw.items():
            results[pd.Timestamp(key)] = value
    except Exception:
        return None, "pickle_read_error", []

    missing = [rb for rb in required if rb not in results]
    if not missing:
        bad_status = [
            str(rb.date())
            for rb in required
            if str(results[rb].get("status", "")) not in {"ok", "forwarded_ml_retrain"}
        ]
        if bad_status:
            return None, f"invalid_cache_status ({bad_status[0]})", []
        return results, None, []

    if not results:
        return None, "data_mismatch", []

    last_cached = max(results)
    if all(rb > last_cached for rb in missing):
        subset = {rb: results[rb] for rb in required if rb in results}
        return subset, None, missing

    return None, "incomplete_coverage", missing


def _save_prediction_cache(
    out_dir: Path,
    cfg: BacktestConfig,
    n_tickers: int,
    rebalance_dates: List[pd.Timestamp],
    results: Dict[pd.Timestamp, Dict[str, Any]],
) -> None:
    cache_path, meta_path = _prediction_cache_paths(out_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {str(pd.Timestamp(k)): v for k, v in results.items()}
    with cache_path.open("wb") as f:
        pickle.dump(serializable, f, protocol=pickle.HIGHEST_PROTOCOL)
    required_rbs = [pd.Timestamp(d) for d in rebalance_dates[:-1]]
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": PREDICTION_CACHE_SCHEMA_VERSION,
                "fingerprint": _prediction_build_fingerprint(cfg, n_tickers, rebalance_dates),
                "config_fingerprint": _prediction_config_fingerprint(cfg),
                "feature_fingerprint": _feature_build_fingerprint(cfg, n_tickers),
                "rebalances": int(len(results)),
                "expected_rebalances": len(required_rbs),
                "expected_rebalance_dates": [str(d.date()) for d in required_rbs],
                "cached_rebalance_dates": sorted(str(pd.Timestamp(k).date()) for k in results),
                "coverage_status": "complete" if len(results) >= len(required_rbs) else "partial",
                "code_fingerprint": __import__("aa_run_provenance", fromlist=["code_fingerprint"]).code_fingerprint(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _price_cache_paths(cache_dir: Path) -> Tuple[Path, Path]:
    base = Path(cache_dir)
    return base / "ohlcv_panel.parquet", base / "price_cache_meta.json"


def _price_cache_fingerprint(tickers: List[str], start: str) -> str:
    payload = "|".join([str(PRICE_CACHE_SCHEMA_VERSION), str(start), ",".join(sorted(set(tickers)))])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _price_cache_is_fresh(meta: Dict[str, Any], ttl_hours: int) -> bool:
    if ttl_hours <= 0:
        return True
    created = str(meta.get("created_at_utc", "") or "")
    if not created:
        return False
    try:
        ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
        return age_hours <= float(ttl_hours)
    except Exception:
        return False


def _load_price_cache(cache_dir: Path, tickers: List[str], start: str, ttl_hours: int) -> Optional[Dict[str, pd.DataFrame]]:
    panel_path, meta_path = _price_cache_paths(cache_dir)
    if not (panel_path.exists() and meta_path.exists()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if meta.get("schema_version") != PRICE_CACHE_SCHEMA_VERSION:
        return None
    if str(meta.get("fingerprint", "")) != _price_cache_fingerprint(tickers, start):
        return None
    if not _price_cache_is_fresh(meta, ttl_hours):
        return None
    panel = pd.read_parquet(panel_path)
    if panel.empty or "ticker" not in panel.columns:
        return None
    if "date" in panel.columns:
        panel["date"] = pd.to_datetime(panel["date"])
        panel = panel.set_index("date")
    data: Dict[str, pd.DataFrame] = {}
    for tk, grp in panel.groupby("ticker", sort=False):
        df = grp.drop(columns=["ticker"], errors="ignore")
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        if cols:
            data[str(tk)] = df[cols].dropna(how="all")
    return data if data else None


def _ohlcv_dict_to_panel_rows(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []
    for tk, df in data.items():
        if df is None or df.empty:
            continue
        part = df.copy()
        part["ticker"] = str(tk)
        part.index.name = "date"
        rows.append(part.reset_index())
    if not rows:
        return pd.DataFrame()
    panel = pd.concat(rows, ignore_index=True)
    if "date" in panel.columns:
        panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    return panel


def _merge_ohlcv_panels(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        return incoming
    if incoming is None or incoming.empty:
        return existing
    combined = pd.concat([existing, incoming], ignore_index=True)
    if "date" in combined.columns:
        combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    if "ticker" in combined.columns:
        combined["ticker"] = combined["ticker"].astype(str)
        combined = combined.sort_values(["ticker", "date"])
        combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
    return combined.reset_index(drop=True)


def _yf_download_to_ohlcv_dict(raw: pd.DataFrame, tickers: List[str]) -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    if raw.empty:
        return data
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = raw.columns.get_level_values(0)
        for tk in tickers:
            if tk not in level0:
                continue
            df = raw[tk].copy()
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if cols and df["Close"].notna().sum() > 0:
                data[tk] = df[cols].dropna(how="all")
    else:
        tk = tickers[0]
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
        if cols:
            data[tk] = raw[cols].dropna(how="all")
    return data


def merge_recent_ohlcv_into_price_cache(
    cache_dir: Path,
    tickers: List[str],
    *,
    lookback_days: int = 30,
    batch_size: int = 40,
) -> Optional[date]:
    """Append recent daily bars for tickers (fixes bulk-download calendar gaps)."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    clean = sorted({str(t).upper().strip() for t in tickers if str(t).strip()})
    if not clean:
        return None

    end = (date.today() + timedelta(days=1)).isoformat()
    start = (date.today() - timedelta(days=max(int(lookback_days), 7))).isoformat()
    panel_path, _meta_path = _price_cache_paths(cache_dir)
    existing = pd.DataFrame()
    if panel_path.is_file():
        try:
            existing = pd.read_parquet(panel_path)
        except Exception:
            existing = pd.DataFrame()

    merged_frames: Dict[str, pd.DataFrame] = {}
    batch_n = max(int(batch_size), 1)
    for offset in range(0, len(clean), batch_n):
        batch = clean[offset : offset + batch_n]
        raw = yf.download(
            batch,
            start=start,
            end=end,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        merged_frames.update(_yf_download_to_ohlcv_dict(raw, batch))

    if not merged_frames:
        return None

    incoming = _ohlcv_dict_to_panel_rows(merged_frames)
    panel = _merge_ohlcv_panels(existing, incoming)
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(panel_path, index=False)
    latest_date = None
    if "date" not in panel.columns or panel.empty:
        return None
    latest = pd.to_datetime(panel["date"], errors="coerce").max()
    if pd.isna(latest):
        return None
    latest_date = latest.date()
    _touch_price_cache_meta(cache_dir, latest_date=latest_date)
    return latest_date


def _touch_price_cache_meta(cache_dir: Path, *, latest_date: Optional[date] = None) -> None:
    """Refresh meta TTL after tail merge so price_cache_operational accepts the panel."""
    _, meta_path = _price_cache_paths(cache_dir)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {}
    if meta_path.is_file():
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    payload["schema_version"] = PRICE_CACHE_SCHEMA_VERSION
    payload["created_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if latest_date is not None:
        payload["latest_session_date"] = latest_date.isoformat()
    meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _save_price_cache(cache_dir: Path, tickers: List[str], start: str, data: Dict[str, pd.DataFrame]) -> None:
    panel_path, meta_path = _price_cache_paths(cache_dir)
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    incoming = _ohlcv_dict_to_panel_rows(data)
    existing = pd.DataFrame()
    if panel_path.is_file():
        try:
            existing = pd.read_parquet(panel_path)
        except Exception:
            existing = pd.DataFrame()
    panel = _merge_ohlcv_panels(existing, incoming)
    panel.to_parquet(panel_path, index=False)
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": PRICE_CACHE_SCHEMA_VERSION,
                "fingerprint": _price_cache_fingerprint(tickers, start),
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "tickers_loaded": int(len(data)),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _feature_engineering_initializer(
    bench_close: pd.Series,
    bench_features: pd.DataFrame,
    sector_index: Dict[str, pd.Series],
    cfg: BacktestConfig,
) -> None:
    _parallel_worker_bootstrap()
    _CTX.feat_bench_close = bench_close
    _CTX.feat_bench_features = bench_features
    _CTX.feat_sector_index = sector_index
    _CTX.feat_cfg = cfg


def _compute_single_ticker_features(item: Tuple[str, pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Build one ticker's feature frame (picklable worker for multiprocessing.Pool)."""
    if _CTX.feat_bench_close is None or _CTX.feat_bench_features is None or _CTX.feat_cfg is None:
        raise RuntimeError("Feature-engineering worker was not initialized.")
    tk, df = item
    cfg = _CTX.feat_cfg
    bench_close = _CTX.feat_bench_close
    bench_features = _CTX.feat_bench_features
    sector_index = _CTX.feat_sector_index or {}
    if "Close" not in df.columns or "Volume" not in df.columns:
        return None
    close = df["Close"].dropna()
    volume = df["Volume"].reindex(close.index).fillna(0)
    ret = close.pct_change()
    bench_ret = bench_close.pct_change()
    bench_ret_aligned = bench_ret.reindex(close.index)
    beta_252 = ret.rolling(252).cov(bench_ret_aligned) / bench_ret_aligned.rolling(252).var()
    resid = ret - beta_252 * bench_ret_aligned
    feat = pd.DataFrame(index=close.index)
    feat["ticker"] = tk
    feat["sector"] = ticker_to_sector(tk)
    feat["issuer"] = ticker_to_issuer(tk)
    feat["correlation_cluster"] = ticker_to_correlation_cluster(tk, feat["sector"].iloc[0] if len(feat) else None)
    feat["close"] = close
    feat["mom_252_21"] = close.shift(21) / close.shift(252) - 1.0
    feat["mom_126_21"] = close.shift(21) / close.shift(126) - 1.0
    feat["mom_63_21"] = close.shift(21) / close.shift(63) - 1.0
    feat["rev_5"] = -(close / close.shift(5) - 1.0)
    feat["rev_10"] = -(close / close.shift(10) - 1.0)
    # 1-day momentum signal for the daily-alpha benchmark (mom_1_*). Most recent
    # completed 1-day return as of the decision date; traded at rb+1 (no look-ahead).
    # NOT added to FEATURE_COLUMNS on purpose -> the ML model is unaffected.
    feat["mom_1"] = close / close.shift(1) - 1.0
    feat["trend_50"] = (close > close.rolling(50).mean()).astype(float)
    feat["trend_200"] = (close > close.rolling(200).mean()).astype(float)
    feat["vol_20"] = ret.rolling(20).std() * math.sqrt(252)
    feat["vol_63"] = ret.rolling(63).std() * math.sqrt(252)
    feat["rel_vol_20_63"] = feat["vol_20"] / feat["vol_63"]
    feat["beta_252"] = beta_252
    feat["idio_vol_63"] = resid.rolling(63).std() * math.sqrt(252)
    asset_ret_63 = close / close.shift(63) - 1.0
    bench_ret_63 = (bench_close / bench_close.shift(63) - 1.0).reindex(close.index)
    feat["rel_strength_63"] = asset_ret_63 - bench_ret_63
    sec = ticker_to_sector(tk)
    if sec in sector_index:
        sec_idx = sector_index[sec].reindex(close.index).ffill()
        sec_ret_63 = sec_idx / sec_idx.shift(63) - 1.0
        feat["sector_mom_63"] = sec_ret_63
        feat["sector_rel_strength_63"] = asset_ret_63 - sec_ret_63
    else:
        feat["sector_mom_63"] = np.nan
        feat["sector_rel_strength_63"] = np.nan
    med_vol = volume.rolling(60).median()
    feat["volume_ratio"] = volume / med_vol.replace(0, np.nan)
    dollar_volume = close * volume
    adv_20 = dollar_volume.rolling(20).mean()
    universe_adv = dollar_volume.rolling(max(int(cfg.universe_adv_lookback), 1)).mean()
    feat["adv_20"] = adv_20
    feat["universe_adv"] = universe_adv
    feat["universe_history_days"] = close.notna().expanding().sum()
    feat["adv_20_log"] = np.log1p(adv_20)
    entry = close.shift(-1)
    exit_ = close.shift(-(cfg.horizon + 1))
    asset_fwd = exit_ / entry - 1.0
    bench_entry = bench_close.shift(-1).reindex(close.index)
    bench_exit = bench_close.shift(-(cfg.horizon + 1)).reindex(close.index)
    bench_fwd = bench_exit / bench_entry - 1.0
    roundtrip_cost = effective_alpha_target_roundtrip_decimal(cfg)
    feat["target"] = asset_fwd - bench_fwd - roundtrip_cost
    feat = feat.join(bench_features, how="left")
    feat["date"] = feat.index
    return feat.reset_index(drop=True)


def build_feature_table(
    data: Dict[str, pd.DataFrame],
    benchmark: str,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
    pool_session: Optional[ProcessPoolSession] = None,
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if benchmark not in data:
        raise ValueError(f"Benchmark {benchmark} not found in downloaded data.")

    bench_close = data[benchmark]["Close"].dropna()
    bench_ret = bench_close.pct_change()
    bench_features = pd.DataFrame(index=bench_close.index)
    bench_features["market_trend_200"] = (bench_close > bench_close.rolling(200).mean()).astype(float)
    bench_features["market_ret_63"] = bench_close / bench_close.shift(63) - 1.0
    bench_features["market_vol_20"] = bench_ret.rolling(20).std() * math.sqrt(252)

    # Build equal-weighted sector return streams from the tradable universe itself.
    # This is not a fundamentals database; it is a robust price-only approximation
    # used for sector-relative strength and sector-adjusted alpha targets.
    non_tradable = non_tradable_benchmark_tickers(cfg)
    close_panel = pd.DataFrame({tk: df["Close"] for tk, df in data.items() if tk not in non_tradable and "Close" in df.columns})
    ret_panel = close_panel.pct_change()
    sector_returns: Dict[str, pd.Series] = {}
    sector_index: Dict[str, pd.Series] = {}
    for sec in sorted({ticker_to_sector(tk) for tk in close_panel.columns}):
        names = [tk for tk in close_panel.columns if ticker_to_sector(tk) == sec]
        if len(names) >= 3 and sec != "Unknown":
            sr = ret_panel[names].mean(axis=1, skipna=True)
            sector_returns[sec] = sr
            sector_index[sec] = (1.0 + sr.fillna(0.0)).cumprod()

    all_rows: List[pd.DataFrame] = []
    feature_items = [(tk, df) for tk, df in data.items() if tk not in non_tradable]
    n_jobs_feat = resolve_parallel_workers(cfg, backend="process")
    if dashboard is not None:
        dashboard.start_phase(
            "Feature Engineering",
            total=len(feature_items),
            step=f"Preis-, Volumen- und Alpha-Features je Ticker ({n_jobs_feat} Worker)" if n_jobs_feat > 1 else "Preis-, Volumen- und Alpha-Features je Ticker",
        )
    if parallel_execution_enabled(cfg, backend="process") and len(feature_items) > 1:
        chunksize = resolve_pool_chunksize(len(feature_items), n_jobs_feat, cfg)
        if pool_session is not None:
            pool_session.load_feature_engineering_state(bench_close, bench_features, sector_index)
        else:
            _feature_engineering_initializer(bench_close, bench_features, sector_index, cfg)
        # Reuse the session pool that was initialized with feature-engineering state.
        # Do not use the imported aa_parallel._ACTIVE_POOL name here: importing a mutable
        # module global copies the object reference at import time, so it can stay None
        # after ProcessPoolSession creates/replaces the actual pool.
        active_pool = getattr(pool_session, "_pool", None) if pool_session is not None else None
        if active_pool is not None:
            feat_iter = active_pool.imap_unordered(_compute_single_ticker_features, feature_items, chunksize=chunksize)
            for feat_df in feat_iter:
                if feat_df is not None:
                    all_rows.append(feat_df)
                if dashboard is not None:
                    dashboard.advance_phase(1, step="Features je Ticker (parallel)")
                    from aa_ui_pump import pump_ui

                    pump_ui(force=False)
        else:
            with _mp_pool(n_jobs_feat, _feature_engineering_initializer, (bench_close, bench_features, sector_index, cfg)) as pool:
                feat_iter = pool.imap_unordered(_compute_single_ticker_features, feature_items, chunksize=chunksize)
                for feat_df in feat_iter:
                    if feat_df is not None:
                        all_rows.append(feat_df)
                    if dashboard is not None:
                        dashboard.advance_phase(1, step="Features je Ticker (parallel)")
    elif parallel_execution_enabled(cfg, backend="thread") and len(feature_items) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        n_jobs_feat = resolve_parallel_workers(cfg, backend="thread")
        _feature_engineering_initializer(bench_close, bench_features, sector_index, cfg)
        with ThreadPoolExecutor(max_workers=n_jobs_feat) as ex:
            futs = [ex.submit(_compute_single_ticker_features, item) for item in feature_items]
            for fut in as_completed(futs):
                feat_df = fut.result()
                if feat_df is not None:
                    all_rows.append(feat_df)
                if dashboard is not None:
                    dashboard.advance_phase(1, step="Features je Ticker (Thread-Pool)")
                    from aa_ui_pump import pump_ui

                    pump_ui(force=False)
    else:
        _feature_engineering_initializer(bench_close, bench_features, sector_index, cfg)
        for tk, df in feature_items:
            if dashboard is not None:
                dashboard.set_status(step=f"Features berechnen: {tk}", ticker=tk)
            feat_df = _compute_single_ticker_features((tk, df))
            if feat_df is None:
                if dashboard is not None:
                    dashboard.advance_phase(1, step=f"übersprungen: {tk}", ticker=tk)
                continue
            all_rows.append(feat_df)
            if dashboard is not None:
                dashboard.advance_phase(1, step=f"Features fertig: {tk}", ticker=tk)

    if dashboard is not None:
        dashboard.finish_phase()

    if not all_rows:
        raise RuntimeError("No feature rows could be created. Check data coverage.")

    features = pd.concat(all_rows, ignore_index=True)
    features.replace([np.inf, -np.inf], np.nan, inplace=True)
    features.sort_values(["date", "ticker"], inplace=True)
    features.reset_index(drop=True, inplace=True)

    features = mark_universe_eligibility(features, cfg, dashboard)

    # Cross-sectional rank score per date (eligible universe only).
    date_groups = list(features.groupby("date", sort=False))
    n_rank_workers = resolve_parallel_workers(cfg, backend="process")
    if dashboard is not None:
        dashboard.start_phase(
            "Cross-Sectional Ranking",
            total=len(date_groups),
            step=f"Rank Score je Handelstag ({n_rank_workers} Worker)" if n_rank_workers > 1 else "Rank Score je Handelstag",
        )
    ranked_groups: List[pd.DataFrame] = []
    if parallel_execution_enabled(cfg, backend="process"):
        n_chunks = min(max(n_rank_workers * 2, 1), len(date_groups))
        chunk_size = max(1, (len(date_groups) + n_chunks - 1) // n_chunks)
        rank_chunks = [date_groups[i : i + chunk_size] for i in range(0, len(date_groups), chunk_size)]
        for chunk_out in _parallel_map_unordered(cfg, _rank_score_date_chunk, rank_chunks, backend="process"):
            ranked_groups.extend(chunk_out)
            if dashboard is not None:
                dashboard.advance_phase(len(chunk_out), step="Rank Score (parallel)")
    elif parallel_execution_enabled(cfg, backend="thread"):
        n_chunks = min(max(n_rank_workers * 2, 1), len(date_groups))
        chunk_size = max(1, (len(date_groups) + n_chunks - 1) // n_chunks)
        rank_chunks = [date_groups[i : i + chunk_size] for i in range(0, len(date_groups), chunk_size)]
        for chunk_out in _parallel_map_unordered(cfg, _rank_score_date_chunk, rank_chunks, backend="thread"):
            ranked_groups.extend(chunk_out)
            if dashboard is not None:
                dashboard.advance_phase(len(chunk_out), step="Rank Score (Thread-Pool)")
    else:
        for dt, g in date_groups:
            out = add_cross_sectional_rank_scores(g)
            out["date"] = pd.Timestamp(dt)
            ranked_groups.append(out)
            if dashboard is not None:
                dashboard.advance_phase(1, step="Rank Score je Handelstag", date=str(pd.Timestamp(dt).date()), candidates=len(g))
    if dashboard is not None:
        dashboard.finish_phase()
    features = pd.concat(ranked_groups, ignore_index=True)
    features.sort_values(["date", "ticker"], inplace=True)
    features.reset_index(drop=True, inplace=True)

    features = apply_membership_filter_to_features(features, cfg, dashboard)

    # Daily close-to-close returns for backtest.
    returns = pd.DataFrame({tk: df["Close"].pct_change() for tk, df in data.items() if "Close" in df.columns})
    returns.sort_index(inplace=True)

    return features, bench_close, returns



def mark_universe_eligibility(
    features: pd.DataFrame,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
) -> pd.DataFrame:
    """Mark in_universe before cross-sectional ranks (membership filter applied later)."""
    out = features.copy()
    out["in_universe"] = True
    out["universe_rank"] = np.nan
    mode = str(getattr(cfg, "universe_mode", "static")).lower()
    if mode == "static":
        out["universe_reason"] = "static"
        if dashboard is not None:
            dashboard.ok(f"Universe eligibility: static, rows={len(out):,}")
        return out
    if mode != "diy_pit_liquidity":
        raise ValueError(f"Unsupported universe_mode: {cfg.universe_mode}")

    top_n = int(max(getattr(cfg, "universe_top_n", 0), 1))
    min_adv = float(max(getattr(cfg, "universe_min_adv", 0.0), 0.0))
    min_price = float(max(getattr(cfg, "universe_min_price", 0.0), 0.0))
    min_history = int(max(getattr(cfg, "universe_min_history_days", 0), 0))
    base_ok = (
        pd.to_numeric(out.get("universe_adv"), errors="coerce").notna()
        & (pd.to_numeric(out.get("universe_adv"), errors="coerce") >= min_adv)
        & (pd.to_numeric(out.get("close"), errors="coerce") >= min_price)
        & (pd.to_numeric(out.get("universe_history_days"), errors="coerce") >= min_history)
    )
    out["in_universe"] = False
    out["universe_reason"] = "filtered"
    if dashboard is not None:
        dashboard.start_phase("DIY-PIT-Universum", total=1, step=f"Top {top_n} markieren")
    eligible = out.loc[base_ok, ["date", "universe_adv"]].copy()
    liq_rank = eligible.groupby("date", sort=False)["universe_adv"].rank(ascending=False, method="first")
    selected_idx = eligible.index[liq_rank <= float(top_n)]
    out.loc[selected_idx, "in_universe"] = True
    out.loc[selected_idx, "universe_rank"] = liq_rank.loc[selected_idx].astype(float)
    out.loc[selected_idx, "universe_reason"] = "diy_pit_liquidity"
    if dashboard is not None:
        dashboard.advance_phase(1, step=f"{int(out['in_universe'].sum()):,} Zeilen zugelassen")
        dashboard.finish_phase()
    return out


def apply_universe_filter(features: pd.DataFrame, cfg: BacktestConfig, dashboard: Optional[RunDashboard] = None) -> pd.DataFrame:
    """Apply membership filter after universe eligibility (see mark_universe_eligibility)."""
    out = features.copy()
    if "in_universe" not in out.columns:
        out = mark_universe_eligibility(out, cfg, dashboard=None)
    mode = str(getattr(cfg, "universe_mode", "static")).lower()
    if mode == "static":
        if dashboard is not None:
            dashboard.start_phase("Universum filtern", total=2, step="statisches Tickeruniversum")
            dashboard.advance_phase(1, step=f"{len(out):,} Zeilen im statischen Universum")
            dashboard.ok(f"Universe filter: static, rows={len(out):,}")
            dashboard.set_status(step="Membership-Filter anwenden")
        out = apply_membership_filter_to_features(out, cfg, dashboard)
        if dashboard is not None:
            dashboard.advance_phase(1, step="Membership-Filter fertig")
            dashboard.finish_phase()
        return out
    if mode != "diy_pit_liquidity":
        raise ValueError(f"Unsupported universe_mode: {cfg.universe_mode}")
    if dashboard is not None:
        dashboard.start_phase("Universum filtern", total=2, step="Membership-Filter anwenden")
        dashboard.ok(f"Universe filter: {int(out['in_universe'].sum()):,}/{len(out):,} Zeilen zugelassen")
    out = apply_membership_filter_to_features(out, cfg, dashboard)
    if dashboard is not None:
        dashboard.advance_phase(1, step="Membership-Filter fertig")
        dashboard.finish_phase()
    return out

