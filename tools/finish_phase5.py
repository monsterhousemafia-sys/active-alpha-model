"""Re-extract aa_* modules from monolith backup and build active_alpha_model wrapper."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "active_alpha_model_monolith_backup.py"
lines = BACKUP.read_text(encoding="utf-8").splitlines()

COMMON = "from __future__ import annotations\n\n"

RANGES = {
    "aa_constants.py": [(263, 469)],
    "aa_config.py": [(469, 1060), (1062, 1094), (4605, 4617)],
    "aa_universe.py": [(1097, 1763)],
    "aa_features.py": [(1765, 2424)],
    "aa_models.py": [(2426, 2523)],
    "aa_parallel.py": [(2533, 2772)],
    "aa_backtest_ml.py": [(2775, 2958)],
    "aa_portfolio.py": [(2960, 4802), (4849, 4909)],
    "aa_reporting.py": [(4804, 4847), (5050, 5438), (6327, 6469)],
    "aa_execution.py": [(5440, 5854)],
    "aa_backtest.py": [(4912, 5048), (5856, 6326)],
    "aa_runtime.py": [(6471, 6996)],
}


def extract(name: str, ranges: list[tuple[int, int]]) -> None:
    chunks: list[str] = []
    for start, end in ranges:
        chunks.extend(lines[start - 1 : end])
    (ROOT / name).write_text(COMMON + "\n".join(chunks) + "\n", encoding="utf-8")
    print("extracted", name)


PARALLEL_CTX = '''
@dataclass
class ParallelRunContext:
    """Mutable singleton for Windows-spawn worker state (features, returns, cfg)."""

    features: Optional[pd.DataFrame] = None
    feature_by_date: Optional[Dict[pd.Timestamp, pd.DataFrame]] = None
    dates: Optional[List[pd.Timestamp]] = None
    cfg: Optional[BacktestConfig] = None
    returns: Optional[pd.DataFrame] = None
    feat_bench_close: Optional[pd.Series] = None
    feat_bench_features: Optional[pd.DataFrame] = None
    feat_sector_index: Optional[Dict[str, pd.Series]] = None
    feat_cfg: Optional[BacktestConfig] = None
    boot_strategy: Optional[pd.Series] = None
    boot_bench: Optional[Dict[str, Optional[pd.Series]]] = None


_CTX = ParallelRunContext()
_ACTIVE_POOL: Optional[mp.pool.Pool] = None


def _set_prediction_worker_state(
    features: pd.DataFrame,
    dates: List[pd.Timestamp],
    cfg: BacktestConfig,
) -> None:
    from aa_features import build_feature_by_date

    _CTX.features = features
    _CTX.dates = [pd.Timestamp(d) for d in dates]
    _CTX.cfg = cfg
    _CTX.feature_by_date = build_feature_by_date(features)


def _set_combined_worker_state(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    dates: List[pd.Timestamp],
    cfg: BacktestConfig,
) -> None:
    _set_prediction_worker_state(features, dates, cfg)
    _CTX.returns = returns
'''

IMPORTS = {
    "aa_constants.py": """
from typing import Optional

import pandas as pd
""",
    "aa_config.py": """
import argparse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional

from aa_constants import (
    CORRELATION_CLUSTER_MAP,
    DEFAULT_TICKERS,
    FEATURE_COLUMNS,
    ISSUER_MAP,
    SECTOR_MAP,
    VALIDATION_TOL,
    deduplicate_dataframe_columns,
    ticker_to_correlation_cluster,
    ticker_to_issuer,
    ticker_to_sector,
)
from aa_dashboard import RunDashboard
""",
    "aa_universe.py": """
import urllib.request
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from aa_config import BacktestConfig, normalize_yfinance_ticker
from aa_dashboard import RunDashboard
""",
    "aa_parallel.py": """
import multiprocessing as mp
import os
import platform
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
""",
    "aa_features.py": """
import hashlib
import json
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
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
""",
    "aa_models.py": """
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS
""",
    "aa_backtest_ml.py": """
import os
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS, deduplicate_dataframe_columns
from aa_dashboard import RunDashboard
from aa_features import (
    _save_prediction_cache,
    _try_load_prediction_cache,
    build_feature_by_date,
)
from aa_models import fit_predict
from aa_parallel import (
    _ACTIVE_POOL,
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
""",
    "aa_portfolio.py": """
import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, _clip_float
from aa_constants import VALIDATION_TOL, deduplicate_dataframe_columns, ticker_to_correlation_cluster, ticker_to_issuer, ticker_to_sector
from aa_dashboard import RunDashboard
from aa_parallel import (
    _CTX,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    resolve_parallel_workers,
)
""",
    "aa_reporting.py": """
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, normalize_yfinance_ticker, parse_extra_benchmark_tickers
from aa_features import build_feature_by_date
from aa_parallel import (
    _CTX,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    resolve_parallel_workers,
)
from aa_portfolio import _momentum_score, _momentum_variant_label, _neutralized_momentum_candidates
""",
    "aa_execution.py": """
import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, round_half_up_to_increment
""",
    "aa_backtest.py": """
from dataclasses import replace
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_backtest_ml import precompute_backtest_predictions
from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS, deduplicate_dataframe_columns
from aa_dashboard import RunDashboard
from aa_execution import (
    PhaseTimings,
    apply_buy_hold_spread,
    apply_min_trade_value_filter,
    estimate_backtest_rebalance_costs,
    fee_model_label,
    final_position_hygiene_metrics,
    enforce_hard_position_count,
)
from aa_features import build_feature_by_date
from aa_models import fit_predict
from aa_parallel import (
    ProcessPoolSession,
    _CTX,
    _estimate_dataframe_gb,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    resolve_parallel_workers,
)
from aa_portfolio import (
    _momentum_score,
    _momentum_variant_label,
    _neutralized_momentum_candidates,
    allocate_with_caps,
    apply_tail_pruning,
    apply_trade_controls,
    determine_risk_on,
    parse_naive_momentum_variants,
    portfolio_diagnostics,
    project_to_valid_by_blending,
    select_portfolio,
    trim_to_beta_cap,
    trim_to_exposure_cap,
    trim_to_group_caps,
    validate_weights,
)
from aa_reporting import compute_benchmark_comparison, compute_custom_benchmark_returns
""",
    "aa_runtime.py": """
import argparse
import multiprocessing as mp
from pathlib import Path
from time import monotonic
from typing import Dict, List

import numpy as np
import pandas as pd

from aa_backtest import run_backtest, run_latest_signal, run_walkforward_pipeline
from aa_config import BacktestConfig, apply_capital_curve_policy_to_config, enforce_reproducibility_inputs, parse_args
from aa_dashboard import RunDashboard
from aa_execution import PhaseTimings, write_run_manifest
from aa_features import (
    _save_feature_cache,
    _try_load_feature_cache,
    build_feature_table,
)
from aa_parallel import ProcessPoolSession, _configure_blas_threading, prepare_features_for_parallel_runtime
from aa_portfolio import (
    apply_dynamic_cluster_overlay,
    data_quality_report,
    write_constraint_binding_history,
    write_unknown_mapping_reports,
)
from aa_reporting import (
    calculate_metrics,
    compute_benchmark_comparison,
    compute_custom_benchmark_returns,
    compute_factor_proxy_regression,
    compute_statistical_diagnostics,
    maybe_plot,
    summarize_backtest_diagnostics,
    target_portfolio_explained,
    write_report,
)
from aa_universe import download_data, load_tickers
""",
}


def prepend_imports(name: str) -> None:
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    body = text.split("\n", 2)[2] if text.startswith("from __future__") else text
    path.write_text("from __future__ import annotations\n" + IMPORTS[name] + "\n" + body, encoding="utf-8")


def patch_parallel() -> None:
    path = ROOT / "aa_parallel.py"
    text = path.read_text(encoding="utf-8")
    if "class ParallelRunContext" not in text:
        marker = "from aa_config import BacktestConfig\n"
        text = text.replace(marker, marker + PARALLEL_CTX + "\n", 1)

    text = text.replace(
        "def _combined_run_pool_initializer(\n    features: pd.DataFrame,\n    returns: pd.DataFrame,\n    dates: List[pd.Timestamp],\n    cfg: BacktestConfig,\n) -> None:\n    \"\"\"Load shared read-only tables once per worker (rank, cluster, ML, naive).\"\"\"\n    _parallel_worker_bootstrap()\n    global _PAR_FEATURES, _PAR_FEATURE_BY_DATE, _PAR_DATES, _PAR_CFG, _DYN_RETURNS\n    global _NAIVE_FEATURES, _NAIVE_RETURNS, _NAIVE_CFG\n    _PAR_FEATURES = features\n    _PAR_DATES = [pd.Timestamp(d) for d in dates]\n    _PAR_CFG = cfg\n    _PAR_FEATURE_BY_DATE = build_feature_by_date(features)\n    _DYN_RETURNS = returns\n    _NAIVE_FEATURES = features\n    _NAIVE_RETURNS = returns\n    _NAIVE_CFG = cfg",
        "def _combined_run_pool_initializer(\n    features: pd.DataFrame,\n    returns: pd.DataFrame,\n    dates: List[pd.Timestamp],\n    cfg: BacktestConfig,\n) -> None:\n    \"\"\"Load shared read-only tables once per worker (rank, cluster, ML, naive).\"\"\"\n    _parallel_worker_bootstrap()\n    _set_combined_worker_state(features, returns, dates, cfg)",
    )
    text = text.replace(
        "def _parallel_prediction_initializer(features: pd.DataFrame, dates: List[pd.Timestamp], cfg: BacktestConfig) -> None:\n    _parallel_worker_bootstrap()\n    global _PAR_FEATURES, _PAR_FEATURE_BY_DATE, _PAR_DATES, _PAR_CFG\n    _PAR_FEATURES = features\n    _PAR_DATES = [pd.Timestamp(d) for d in dates]\n    _PAR_CFG = cfg\n    _PAR_FEATURE_BY_DATE = build_feature_by_date(features)",
        "def _parallel_prediction_initializer(features: pd.DataFrame, dates: List[pd.Timestamp], cfg: BacktestConfig) -> None:\n    _parallel_worker_bootstrap()\n    _set_prediction_worker_state(features, dates, cfg)",
    )
    path.write_text(text, encoding="utf-8")


def patch_workers() -> None:
    # aa_backtest_ml
    p = ROOT / "aa_backtest_ml.py"
    t = p.read_text(encoding="utf-8")
    t = t.replace("_PAR_FEATURES is None or _PAR_FEATURE_BY_DATE is None or _PAR_CFG is None", "_CTX.features is None or _CTX.feature_by_date is None or _CTX.cfg is None")
    t = t.replace("cfg = _PAR_CFG\n    features = _PAR_FEATURES\n    feature_by_date = _PAR_FEATURE_BY_DATE", "cfg = _CTX.cfg\n    features = _CTX.features\n    feature_by_date = _CTX.feature_by_date")
    t = t.replace("if _PAR_DATES is not None and feature_by_date is not None:\n        for d in _PAR_DATES:", "if _CTX.dates is not None and feature_by_date is not None:\n        for d in _CTX.dates:")
    t = t.replace(
        "        global _PAR_FEATURES, _PAR_FEATURE_BY_DATE, _PAR_DATES, _PAR_CFG\n        _PAR_FEATURES = features_worker\n        _PAR_DATES = [pd.Timestamp(d) for d in dates]\n        _PAR_CFG = cfg\n        _PAR_FEATURE_BY_DATE = build_feature_by_date(features_worker)",
        "        _set_prediction_worker_state(features_worker, dates, cfg)",
    )
    p.write_text(t, encoding="utf-8")

    # aa_backtest naive workers
    p = ROOT / "aa_backtest.py"
    t = p.read_text(encoding="utf-8")
    t = t.replace(
        "_NAIVE_FEATURES: Optional[pd.DataFrame] = None\n_NAIVE_RETURNS: Optional[pd.DataFrame] = None\n_NAIVE_CFG: Optional[BacktestConfig] = None\n\n\ndef _naive_baseline_initializer(features: pd.DataFrame, returns: pd.DataFrame, cfg: BacktestConfig) -> None:\n    _parallel_worker_bootstrap()\n    global _NAIVE_FEATURES, _NAIVE_RETURNS, _NAIVE_CFG\n    _NAIVE_FEATURES = features\n    _NAIVE_RETURNS = returns\n    _NAIVE_CFG = cfg\n\n\ndef _naive_baseline_variant_task(variant: str) -> Tuple[str, List[str], List[float]]:\n    if _NAIVE_FEATURES is None or _NAIVE_RETURNS is None or _NAIVE_CFG is None:\n        raise RuntimeError(\"Naive-baseline worker was not initialized.\")\n    s = run_naive_momentum_baseline(_NAIVE_FEATURES, _NAIVE_RETURNS, _NAIVE_CFG, None, variant=variant)",
        "def _naive_baseline_initializer(features: pd.DataFrame, returns: pd.DataFrame, cfg: BacktestConfig) -> None:\n    _parallel_worker_bootstrap()\n    _CTX.features = features\n    _CTX.returns = returns\n    _CTX.cfg = cfg\n\n\ndef _naive_baseline_variant_task(variant: str) -> Tuple[str, List[str], List[float]]:\n    if _CTX.features is None or _CTX.returns is None or _CTX.cfg is None:\n        raise RuntimeError(\"Naive-baseline worker was not initialized.\")\n    s = run_naive_momentum_baseline(_CTX.features, _CTX.returns, _CTX.cfg, None, variant=variant)",
    )
    p.write_text(t, encoding="utf-8")

    # aa_portfolio dynamic cluster
    p = ROOT / "aa_portfolio.py"
    t = p.read_text(encoding="utf-8")
    t = t.replace(
        "_DYN_RETURNS: Optional[pd.DataFrame] = None\n\n\ndef _dynamic_cluster_initializer(returns: pd.DataFrame) -> None:\n    _parallel_worker_bootstrap()\n    global _DYN_RETURNS\n    _DYN_RETURNS = returns\n\n\ndef _dynamic_cluster_date_task(\n    payload: Tuple[pd.Timestamp, pd.DataFrame, str, int, int, float, float],\n) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:\n    if _DYN_RETURNS is None:\n        raise RuntimeError(\"Dynamic-cluster worker was not initialized.\")\n    d, snap, mode, w_short, w_long, threshold, min_overlap = payload\n    returns = _DYN_RETURNS",
        "def _dynamic_cluster_initializer(returns: pd.DataFrame) -> None:\n    _parallel_worker_bootstrap()\n    _CTX.returns = returns\n\n\ndef _dynamic_cluster_date_task(\n    payload: Tuple[pd.Timestamp, pd.DataFrame, str, int, int, float, float],\n) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:\n    if _CTX.returns is None:\n        raise RuntimeError(\"Dynamic-cluster worker was not initialized.\")\n    d, snap, mode, w_short, w_long, threshold, min_overlap = payload\n    returns = _CTX.returns",
    )
    p.write_text(t, encoding="utf-8")

    # aa_features ticker pool
    p = ROOT / "aa_features.py"
    t = p.read_text(encoding="utf-8")
    t = t.replace(
        "_FEAT_PAR_BENCH_CLOSE: Optional[pd.Series] = None\n_FEAT_PAR_BENCH_FEATURES: Optional[pd.DataFrame] = None\n_FEAT_PAR_SECTOR_INDEX: Optional[Dict[str, pd.Series]] = None\n_FEAT_PAR_CFG: Optional[BacktestConfig] = None\n\n\ndef _feature_engineering_initializer(\n    bench_close: pd.Series,\n    bench_features: pd.DataFrame,\n    sector_index: Dict[str, pd.Series],\n    cfg: BacktestConfig,\n) -> None:\n    _parallel_worker_bootstrap()\n    global _FEAT_PAR_BENCH_CLOSE, _FEAT_PAR_BENCH_FEATURES, _FEAT_PAR_SECTOR_INDEX, _FEAT_PAR_CFG\n    _FEAT_PAR_BENCH_CLOSE = bench_close\n    _FEAT_PAR_BENCH_FEATURES = bench_features\n    _FEAT_PAR_SECTOR_INDEX = sector_index\n    _FEAT_PAR_CFG = cfg\n\n\ndef _compute_single_ticker_features(item: Tuple[str, pd.DataFrame]) -> Optional[pd.DataFrame]:\n    \"\"\"Build one ticker's feature frame (picklable worker for multiprocessing.Pool).\"\"\"\n    if _FEAT_PAR_BENCH_CLOSE is None or _FEAT_PAR_BENCH_FEATURES is None or _FEAT_PAR_CFG is None:\n        raise RuntimeError(\"Feature-engineering worker was not initialized.\")\n    tk, df = item\n    cfg = _FEAT_PAR_CFG\n    bench_close = _FEAT_PAR_BENCH_CLOSE\n    bench_features = _FEAT_PAR_BENCH_FEATURES\n    sector_index = _FEAT_PAR_SECTOR_INDEX or {}",
        "def _feature_engineering_initializer(\n    bench_close: pd.Series,\n    bench_features: pd.DataFrame,\n    sector_index: Dict[str, pd.Series],\n    cfg: BacktestConfig,\n) -> None:\n    _parallel_worker_bootstrap()\n    _CTX.feat_bench_close = bench_close\n    _CTX.feat_bench_features = bench_features\n    _CTX.feat_sector_index = sector_index\n    _CTX.feat_cfg = cfg\n\n\ndef _compute_single_ticker_features(item: Tuple[str, pd.DataFrame]) -> Optional[pd.DataFrame]:\n    \"\"\"Build one ticker's feature frame (picklable worker for multiprocessing.Pool).\"\"\"\n    if _CTX.feat_bench_close is None or _CTX.feat_bench_features is None or _CTX.feat_cfg is None:\n        raise RuntimeError(\"Feature-engineering worker was not initialized.\")\n    tk, df = item\n    cfg = _CTX.feat_cfg\n    bench_close = _CTX.feat_bench_close\n    bench_features = _CTX.feat_bench_features\n    sector_index = _CTX.feat_sector_index or {}",
    )
    p.write_text(t, encoding="utf-8")

    # aa_reporting bootstrap workers
    p = ROOT / "aa_reporting.py"
    t = p.read_text(encoding="utf-8")
    t = t.replace(
        "_BOOT_STRATEGY: Optional[pd.Series] = None\n_BOOT_BENCH: Optional[Dict[str, Optional[pd.Series]]] = None\n\n\ndef _bootstrap_initializer(strategy: pd.Series, bench: Dict[str, Optional[pd.Series]]) -> None:\n    _parallel_worker_bootstrap()\n    global _BOOT_STRATEGY, _BOOT_BENCH\n    _BOOT_STRATEGY = strategy\n    _BOOT_BENCH = bench\n\n\ndef _bootstrap_batch_task(task: Dict[str, Any]) -> Tuple[str, List[Dict[str, float]]]:\n    if _BOOT_STRATEGY is None or _BOOT_BENCH is None:\n        raise RuntimeError(\"Bootstrap worker was not initialized.\")\n    label = str(task[\"label\"])",
        "def _bootstrap_initializer(strategy: pd.Series, bench: Dict[str, Optional[pd.Series]]) -> None:\n    _parallel_worker_bootstrap()\n    _CTX.boot_strategy = strategy\n    _CTX.boot_bench = bench\n\n\ndef _bootstrap_batch_task(task: Dict[str, Any]) -> Tuple[str, List[Dict[str, float]]]:\n    if _CTX.boot_strategy is None or _CTX.boot_bench is None:\n        raise RuntimeError(\"Bootstrap worker was not initialized.\")\n    label = str(task[\"label\"])",
    )
    t = t.replace("_BOOT_BENCH.get", "_CTX.boot_bench.get")
    t = t.replace("_BOOT_STRATEGY,", "_CTX.boot_strategy,")
    p.write_text(t, encoding="utf-8")


def write_wrapper() -> None:
    wrapper = '''#!/usr/bin/env python3
"""
Active Alpha Model - benchmark-aware active equity research system.

Thin compatibility wrapper; implementation lives in aa_* modules.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from aa_backtest import (  # noqa: F401
    _accumulate_vectorized_period_returns,
    _naive_baseline_initializer,
    _naive_baseline_variant_task,
    _simulate_walkforward_portfolio_path,
    run_backtest,
    run_latest_signal,
    run_naive_momentum_baseline,
    run_naive_momentum_baselines,
    run_walkforward_pipeline,
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
from aa_runtime import main, run_self_tests  # noqa: F401
from aa_universe import *  # noqa: F403,F401

if __name__ == "__main__":
    main()
'''
    (ROOT / "active_alpha_model.py").write_text(wrapper, encoding="utf-8")
    print("wrote active_alpha_model.py wrapper")


def main() -> None:
    for name, ranges in RANGES.items():
        extract(name, ranges)
    for name in IMPORTS:
        prepend_imports(name)
    patch_parallel()
    patch_workers()
    write_wrapper()


if __name__ == "__main__":
    main()
