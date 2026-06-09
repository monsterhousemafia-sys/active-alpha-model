"""Prepend standard imports to extracted aa_* modules."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEADERS = {
    "aa_constants.py": """
from typing import Optional

import pandas as pd
""",
    "aa_config.py": """
import argparse
from dataclasses import dataclass, replace
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

from aa_config import BacktestConfig
from aa_constants import normalize_yfinance_ticker
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
    _mp_pool,
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
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS
from aa_dashboard import RunDashboard
from aa_features import build_feature_by_date
from aa_models import fit_predict
from aa_parallel import (
    _ACTIVE_POOL,
    _PAR_CFG,
    _PAR_DATES,
    _PAR_FEATURE_BY_DATE,
    _PAR_FEATURES,
    _mp_pool,
    _parallel_prediction_initializer,
    prepare_features_for_parallel_runtime,
    resolve_parallel_workers,
    resolve_pool_chunksize,
)
from aa_portfolio import deduplicate_dataframe_columns, select_portfolio
""",
    "aa_portfolio.py": """
import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import VALIDATION_TOL
from aa_dashboard import RunDashboard
from aa_parallel import (
    _DYN_RETURNS,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    resolve_parallel_workers,
)
""",
    "aa_reporting.py": """
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, parse_extra_benchmark_tickers
from aa_constants import normalize_yfinance_ticker
from aa_features import build_feature_by_date
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
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS
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
from aa_parallel import ProcessPoolSession, parallel_execution_enabled, resolve_parallel_workers
from aa_portfolio import (
    apply_tail_pruning,
    apply_trade_controls,
    deduplicate_dataframe_columns,
    portfolio_diagnostics,
    project_to_valid_by_blending,
    select_portfolio,
    trim_to_beta_cap,
    trim_to_exposure_cap,
    trim_to_group_caps,
    validate_weights,
)
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
    apply_dynamic_cluster_overlay,
    build_feature_table,
    data_quality_report,
    prepare_features_for_parallel_runtime,
)
from aa_parallel import ProcessPoolSession, _configure_blas_threading
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
from aa_portfolio import write_constraint_binding_history, write_unknown_mapping_reports
from aa_universe import download_data, load_tickers
""",
}


def fix(name: str) -> None:
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    if "import pandas" in text.split("\n", 8)[2:10]:
        return
    header = HEADERS[name]
    if name == "aa_constants.py" and "def normalize_yfinance_ticker" not in text:
        text += """

def normalize_yfinance_ticker(symbol: str) -> str:
    tk = str(symbol).strip().upper()
    if not tk or tk in {"NAN", "NONE"}:
        return ""
    tk = tk.replace(".", "-")
    tk = tk.replace(" ", "")
    return tk
"""
    path.write_text(text.split("\n", 2)[0] + "\n" + header + "\n" + text.split("\n", 2)[2], encoding="utf-8")
    print("fixed", name)


if __name__ == "__main__":
    for fname in HEADERS:
        fix(fname)
