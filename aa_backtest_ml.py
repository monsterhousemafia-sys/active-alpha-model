from __future__ import annotations

import os
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS, deduplicate_dataframe_columns
from aa_dashboard import RunDashboard
from aa_frozen import effective_parallel_backend
from aa_features import (
    _save_prediction_cache,
    _try_load_prediction_cache,
    build_feature_by_date,
)
from aa_models import fit_predict
import aa_parallel as _aa_parallel
from aa_parallel import (
    _CTX,
    _estimate_dataframe_gb,
    _mp_pool,
    _parallel_prediction_initializer,
    _parallel_profile,
    _resolve_cpu_cores,
    _resolve_system_ram_gb,
    _set_prediction_worker_state,
    prepare_features_for_parallel_runtime,
    resolve_parallel_workers,
    resolve_pool_chunksize,
)
from aa_portfolio import select_portfolio

_MU_PRED_COLS = (
    "mu_hat",
    "mu_elastic",
    "mu_gbm",
    "mu_rank",
    "mu_hat_raw",
    "alpha_lcb",
    "rank_score",
    "selection_score",
)


def resolve_forwarded_ml_prediction(
    res: Dict[str, Any],
    snapshot: Optional[pd.DataFrame],
    cfg: BacktestConfig,
) -> Dict[str, Any]:
    """Re-run portfolio selection on the current snapshot using forwarded ML predictions."""
    if str(res.get("status", "")) != "forwarded_ml_retrain":
        return res
    if snapshot is None or snapshot.empty:
        return {**res, "status": "skip", "reason": "missing_snapshot_forward"}
    old_ranked = res.get("ranked")
    if old_ranked is None or not isinstance(old_ranked, pd.DataFrame) or old_ranked.empty:
        return {**res, "status": "skip", "reason": "missing_forward_ranked"}
    pred_cols = [c for c in _MU_PRED_COLS if c in old_ranked.columns]
    if not pred_cols:
        return res
    snap = snapshot.copy()
    merge_df = old_ranked[["ticker"] + pred_cols].drop_duplicates("ticker")
    snap = snap.drop(columns=[c for c in pred_cols if c in snap.columns], errors="ignore")
    snap = snap.merge(merge_df, on="ticker", how="left")
    rmse = float(res.get("rmse", np.nan))
    target_weights, ranked = select_portfolio(snap, rmse, cfg)
    ranked = deduplicate_dataframe_columns(ranked)
    effective_beta_cap = float(getattr(cfg, "max_portfolio_beta", 0.0) or 0.0)
    if "effective_max_portfolio_beta" in ranked.columns and ranked["effective_max_portfolio_beta"].notna().any():
        effective_beta_cap = float(pd.to_numeric(ranked["effective_max_portfolio_beta"], errors="coerce").dropna().iloc[0])
    out = dict(res)
    out.update(
        {
            "status": "ok",
            "target_weights": target_weights,
            "ranked": ranked,
            "effective_beta_cap": float(effective_beta_cap),
            "ml_reused_from_refit": True,
            "snapshot_rows": int(len(snapshot)),
        }
    )
    return out


def _compute_rebalance_prediction_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Heavy, state-independent part of one rebalance.

    ML + initial portfolio selection for one rebalance. Path-dependent execution
    runs in _simulate_walkforward_portfolio_path (Phase B of run_walkforward_pipeline).
    """
    if _CTX.features is None or _CTX.feature_by_date is None or _CTX.cfg is None:
        raise RuntimeError("Parallel prediction worker was not initialized.")
    cfg = _CTX.cfg
    features = _CTX.features
    feature_by_date = _CTX.feature_by_date
    rb = pd.Timestamp(task["rb"])
    next_rb = pd.Timestamp(task["next_rb"])
    train_start = pd.Timestamp(task["train_start"])
    train_end = pd.Timestamp(task["train_end"])
    n = int(task["n"])

    snapshot = feature_by_date.get(rb)
    if snapshot is None:
        return {"status": "skip", "reason": "missing_snapshot", "n": n, "rb": rb, "next_rb": next_rb, "train_rows": 0, "snapshot_rows": 0}

    train_parts: List[pd.DataFrame] = []
    if _CTX.dates is not None and feature_by_date is not None:
        for d in _CTX.dates:
            if d < train_start or d > train_end:
                continue
            chunk = feature_by_date.get(d)
            if chunk is not None and not chunk.empty:
                train_parts.append(chunk)
        train = pd.concat(train_parts, ignore_index=True) if train_parts else pd.DataFrame()
        if "in_universe" in train.columns:
            train = train[train["in_universe"].fillna(False).astype(bool)]
        train = train.dropna(subset=["target"])
    else:
        train_mask = (features["date"] >= train_start) & (features["date"] <= train_end)
        if "in_universe" in features.columns:
            train_mask &= features["in_universe"].fillna(False).astype(bool)
        train = features.loc[train_mask].dropna(subset=["target"])
    if len(train) < cfg.min_train_rows:
        return {"status": "skip", "reason": "too_few_train_rows", "n": n, "rb": rb, "next_rb": next_rb, "train_rows": int(len(train)), "snapshot_rows": int(len(snapshot))}

    pred, rmse = fit_predict(train, snapshot, FEATURE_COLUMNS, cfg)
    target_weights, ranked = select_portfolio(pred, rmse, cfg)
    ranked = deduplicate_dataframe_columns(ranked)
    effective_beta_cap = float(getattr(cfg, "max_portfolio_beta", 0.0) or 0.0)
    if "effective_max_portfolio_beta" in ranked.columns and ranked["effective_max_portfolio_beta"].notna().any():
        effective_beta_cap = float(pd.to_numeric(ranked["effective_max_portfolio_beta"], errors="coerce").dropna().iloc[0])
    return {
        "status": "ok",
        "n": n,
        "rb": rb,
        "next_rb": next_rb,
        "train_rows": int(len(train)),
        "snapshot_rows": int(len(snapshot)),
        "rmse": float(rmse) if np.isfinite(rmse) else np.nan,
        "target_weights": target_weights,
        "ranked": ranked,
        "effective_beta_cap": float(effective_beta_cap),
    }


def precompute_backtest_predictions(
    features: pd.DataFrame,
    dates: List[pd.Timestamp],
    rebalance_dates: List[pd.Timestamp],
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
    *,
    out_dir: Optional[Path] = None,
    n_tickers: Optional[int] = None,
) -> Dict[pd.Timestamp, Dict[str, Any]]:
    """Parallelize the expensive walk-forward prediction/training stage.

    The backtest is split into two phases:
      1. parallel, state-independent ML training/prediction/initial target construction;
      2. serial, path-dependent execution simulation and turnover controls.

    This preserves the portfolio path logic while allowing several rebalance
    predictions to train concurrently.
    """
    n_tk = int(n_tickers if n_tickers is not None else features["ticker"].nunique())
    cache_root = Path(out_dir or getattr(cfg, "out_dir", "model_output"))
    seed_results: Dict[pd.Timestamp, Dict[str, Any]] = {}
    missing_rbs: List[pd.Timestamp] = []
    if bool(getattr(cfg, "reuse_prediction_cache", False)) and not bool(getattr(cfg, "force_rebuild_predictions", False)):
        cached, reject_reason, missing_rbs = _try_load_prediction_cache(cache_root, cfg, n_tk, rebalance_dates)
        if cached is not None and not missing_rbs:
            if dashboard is not None:
                dashboard.ok(f"Prediction-Cache geladen: {len(cached):,} Rebalances")
            else:
                print(f"Loaded prediction cache: {len(cached):,} rebalances")
            return cached
        if cached is not None and missing_rbs:
            seed_results = dict(cached)
            if dashboard is not None:
                dashboard.ok(
                    f"Prediction-Cache teilweise gültig — {len(cached):,} Rebalances, "
                    f"{len(missing_rbs):,} neue werden berechnet …"
                )
        elif reject_reason and dashboard is not None:
            reason_txt = {
                "config_mismatch": "Einstellungen geändert",
                "data_mismatch": "Marktdaten/Universe geändert",
                "fingerprint_mismatch": "Cache veraltet",
            }.get(reject_reason, reject_reason)
            dashboard.warn(f"Prediction-Cache ungültig ({reason_txt}), Phase A Neubau …")
    elif bool(getattr(cfg, "force_rebuild_predictions", False)) and dashboard is not None:
        dashboard.ok("Prediction-Cache wird ignoriert (--force-rebuild-predictions)")

    profile = _parallel_profile(cfg)
    features_worker = prepare_features_for_parallel_runtime(features, cfg) if profile == "high" else features
    feature_table_gb = _estimate_dataframe_gb(features_worker)
    backend = effective_parallel_backend(cfg, getattr(cfg, "parallel_backtest_backend", "thread"))
    if backend not in {"thread", "process"}:
        backend = "thread"
    n_jobs = resolve_parallel_workers(cfg, feature_table_gb=feature_table_gb, backend=backend)

    date_positions = {pd.Timestamp(d): i for i, d in enumerate(dates)}
    tasks: List[Dict[str, Any]] = []
    for n, rb in enumerate(rebalance_dates[:-1]):
        next_rb = rebalance_dates[n + 1]
        rb_ts = pd.Timestamp(rb)
        train_end_idx = max(0, int(date_positions.get(rb_ts, 0)) - cfg.horizon - 1)
        train_end = pd.Timestamp(dates[train_end_idx])
        train_start = rb_ts - pd.DateOffset(years=cfg.train_years)
        tasks.append({"n": n, "rb": rb_ts, "next_rb": pd.Timestamp(next_rb), "train_start": train_start, "train_end": train_end})

    if missing_rbs:
        missing_set = {pd.Timestamp(rb) for rb in missing_rbs}
        tasks = [t for t in tasks if pd.Timestamp(t["rb"]) in missing_set]

    retrain_every = max(1, int(getattr(cfg, "ml_retrain_every", 1) or 1))
    all_tasks = list(tasks)
    if retrain_every > 1 and all_tasks:
        tasks = [t for t in all_tasks if int(t.get("n", 0)) % retrain_every == 0]

    phase_label = f"{n_jobs} Worker, Backend={backend}" if n_jobs > 1 else "seriell"
    if dashboard is not None:
        dashboard.start_phase(
            "Walk-forward ML (Phase A)",
            total=max(len(tasks), 1),
            step=phase_label,
        )
    elif n_jobs > 1:
        logical = max(1, os.cpu_count() or 1)
        print(
            f"Parallel prediction pipeline with {n_jobs} worker(s) on {_resolve_cpu_cores(cfg)} physical cores "
            f"({logical} logical), backend={backend}, profile={profile}, "
            f"feature_table={feature_table_gb:.2f} GB, ram={_resolve_system_ram_gb(cfg)} GB ..."
        )
    else:
        print(f"Serial prediction pipeline (Phase A), {len(tasks)} rebalance(s) to fit ...")

    results: Dict[pd.Timestamp, Dict[str, Any]] = dict(seed_results)
    completed = len(seed_results)

    def _store_prediction_result(res: Dict[str, Any]) -> None:
        nonlocal completed
        rb = pd.Timestamp(res.get("rb"))
        results[rb] = res
        completed += 1
        if dashboard is not None:
            dashboard.advance_phase(
                1,
                step=str(res.get("status", "done")),
                rebalance=f"{completed}/{len(tasks)}",
                date=str(rb.date()) if pd.notna(rb) else "",
                train_rows=f"{int(res.get('train_rows', 0) or 0):,}",
                candidates=int(res.get("snapshot_rows", 0) or 0),
            )
            from aa_ui_pump import pump_ui

            pump_ui(force=False)
        elif completed % 25 == 0 or completed == len(tasks):
            print(f"  predicted {completed}/{len(tasks)} rebalances")

    if n_jobs <= 1:
        _set_prediction_worker_state(features_worker, dates, cfg)
        for task in tasks:
            _store_prediction_result(_compute_rebalance_prediction_task(task))
    elif backend == "process":
        chunksize = resolve_pool_chunksize(len(tasks), n_jobs, cfg)
        active_pool = getattr(_aa_parallel, "_ACTIVE_POOL", None)
        if active_pool is not None:
            for res in active_pool.imap_unordered(_compute_rebalance_prediction_task, tasks, chunksize=chunksize):
                _store_prediction_result(res)
        else:
            with _mp_pool(n_jobs, _parallel_prediction_initializer, (features_worker, dates, cfg)) as pool:
                for res in pool.imap_unordered(_compute_rebalance_prediction_task, tasks, chunksize=chunksize):
                    _store_prediction_result(res)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        _set_prediction_worker_state(features_worker, dates, cfg)
        with ThreadPoolExecutor(max_workers=n_jobs) as ex:
            futs = [ex.submit(_compute_rebalance_prediction_task, t) for t in tasks]
            for fut in as_completed(futs):
                _store_prediction_result(fut.result())

    if dashboard is not None:
        dashboard.finish_phase()
        dashboard.ok(f"Parallel prediction pipeline completed: {len(results):,} rebalances cached")

    if retrain_every > 1 and all_tasks:
        for t in all_tasks:
            rb = pd.Timestamp(t["rb"])
            if rb in results:
                continue
            n = int(t.get("n", 0))
            best = None
            best_n = -1
            for ot in all_tasks:
                on = int(ot.get("n", 0))
                if on <= n and on % retrain_every == 0 and on > best_n:
                    orb = pd.Timestamp(ot["rb"])
                    if orb in results and str(results[orb].get("status", "")) == "ok":
                        best_n = on
                        best = orb
            if best is not None:
                fwd = dict(results[best])
                fwd["rb"] = rb
                fwd["next_rb"] = pd.Timestamp(t["next_rb"])
                fwd["n"] = n
                fwd["status"] = "forwarded_ml_retrain"
                results[rb] = fwd
            else:
                results[rb] = {
                    "status": "skip",
                    "reason": "no_refit_source_for_forward",
                    "rb": rb,
                    "next_rb": pd.Timestamp(t["next_rb"]),
                    "n": n,
                }
        if dashboard is not None:
            dashboard.ok(f"ML-Reuse: alle {retrain_every}. Rebalance — {len(results):,} Termine abgedeckt")

    required_rbs = [pd.Timestamp(d) for d in rebalance_dates[:-1]]
    missing_cov = [rb for rb in required_rbs if rb not in results]
    if missing_cov:
        raise RuntimeError(
            f"Prediction cache incomplete: missing {len(missing_cov)} rebalance(s), "
            f"first missing {missing_cov[0].date()}"
        )

    if bool(getattr(cfg, "write_prediction_cache", True)) and results:
        try:
            _save_prediction_cache(cache_root, cfg, n_tk, rebalance_dates, results)
            if dashboard is not None:
                dashboard.ok("Prediction-Cache für schnelle Policy-/Kosten-Wiederholungsläufe gespeichert")
        except Exception as exc:
            if dashboard is not None:
                dashboard.warn(f"Prediction-Cache konnte nicht gespeichert werden: {exc}")
    return results

