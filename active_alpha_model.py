#!/usr/bin/env python3
"""
Active Alpha Model - benchmark-aware active equity research system.

Thin compatibility wrapper; implementation lives in aa_* modules.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from aa_backtest import (  # noqa: F401
    ResearchPipelineResult,
    _accumulate_vectorized_period_returns,
    _naive_baseline_initializer,
    _naive_baseline_variant_task,
    _simulate_walkforward_portfolio_path,
    run_backtest,
    run_latest_signal,
    BaselineRunResult,
    run_naive_detailed_reporting,
    run_naive_momentum_baseline_full,
    write_naive_baseline_artifacts,
    run_naive_momentum_baseline,
    run_naive_momentum_baseline_detailed,
    run_naive_momentum_baselines,
    run_research_pipeline,
    run_walkforward_pipeline,
    write_backtest_core_outputs,
)
from aa_backtest_ml import (  # noqa: F401
    _compute_rebalance_prediction_task,
    precompute_backtest_predictions,
)
from aa_config import *  # noqa: F403,F401
from aa_constants import *  # noqa: F403,F401
from aa_dashboard import RunDashboard  # noqa: F401
from aa_execution import *  # noqa: F403,F401
from aa_features import *  # noqa: F403,F401
from aa_features import (  # noqa: F401
    FEATURE_CACHE_SCHEMA_VERSION,
    PREDICTION_CACHE_SCHEMA_VERSION,
    _feature_build_fingerprint,
    _feature_cache_paths,
    _prediction_build_fingerprint,
    _price_cache_fingerprint,
    _price_cache_is_fresh,
    _save_feature_cache,
    _save_prediction_cache,
    _try_load_feature_cache,
    _try_load_prediction_cache,
    build_feature_by_date,
    collect_cache_status_lines,
    resolve_feature_cache_dir,
    resolve_price_cache_dir,
    resolve_shared_cache_root,
    using_shared_cache_dir,
)
from aa_models import fit_predict, make_model  # noqa: F401
from aa_parallel import (  # noqa: F401
    ParallelRunContext,
    ProcessPoolSession,
    _CTX,
    _ACTIVE_POOL,
    _configure_blas_threading,
    _mp_pool,
    _parallel_map_unordered,
    _parallel_prediction_initializer,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    prepare_features_for_parallel_runtime,
    resolve_n_jobs,
    resolve_parallel_workers,
    resolve_pool_chunksize,
)
from aa_portfolio import *  # noqa: F403,F401
from aa_reporting import *  # noqa: F403,F401
from aa_runtime import main, print_dry_run_preview, run_self_tests  # noqa: F401
from aa_runtime_profile import apply_process_priority_from_env
from aa_universe import *  # noqa: F403,F401

if __name__ == "__main__":
    mp.freeze_support()
    _configure_blas_threading(1)
    apply_process_priority_from_env()
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)
