#!/usr/bin/env python3
"""Split active_alpha_model.py into aa_* modules (one-time refactor helper)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "active_alpha_model.py"
lines = SRC.read_text(encoding="utf-8").splitlines()

COMMON = '''from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
'''

# 1-based inclusive line ranges -> filename
RANGES: dict[str, list[tuple[int, int]]] = {
    "aa_dashboard.py": [(48, 261)],
    "aa_constants.py": [(263, 404), (406, 469)],
    "aa_config.py": [(471, 1060), (4605, 4617)],
    "aa_universe.py": [(1097, 1763)],
    "aa_features.py": [(1765, 2424)],
    "aa_models.py": [(2426, 2531)],
    "aa_parallel.py": [(2533, 2773)],
    "aa_backtest_ml.py": [(2775, 2958)],
    "aa_portfolio.py": [(2960, 4802)],
    "aa_reporting.py": [(4804, 5438), (6327, 6469)],
    "aa_execution.py": [(5440, 5854)],
    "aa_backtest.py": [(4912, 5050), (5856, 6326)],
    "aa_runtime.py": [(6471, 6996)],
}

IMPORTS: dict[str, str] = {
    "aa_dashboard.py": COMMON + "\nfrom collections import deque\nfrom pathlib import Path\nfrom time import monotonic\nfrom typing import Any, Dict, Optional\n",
    "aa_constants.py": COMMON + "\nfrom typing import Optional\n\nimport pandas as pd\n",
    "aa_config.py": COMMON + '''
import argparse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional

from aa_constants import FEATURE_COLUMNS, VALIDATION_TOL  # noqa: F401
from aa_dashboard import RunDashboard
''',
    "aa_universe.py": COMMON + '''
import urllib.request
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from aa_config import BacktestConfig
from aa_dashboard import RunDashboard
''',
    "aa_features.py": COMMON + '''
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
from aa_constants import FEATURE_COLUMNS
from aa_dashboard import RunDashboard
from aa_parallel import (
    ProcessPoolSession,
    _mp_pool,
    parallel_execution_enabled,
    resolve_parallel_workers,
    resolve_pool_chunksize,
)
from aa_universe import download_data  # noqa: F401
''',
    "aa_models.py": COMMON + '''
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS
''',
    "aa_parallel.py": COMMON + '''
import multiprocessing as mp
import os
import platform
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from aa_config import BacktestConfig
''',
    "aa_backtest_ml.py": COMMON + '''
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS
from aa_dashboard import RunDashboard
from aa_features import build_feature_by_date, prepare_features_for_parallel_runtime
from aa_models import fit_predict
from aa_parallel import (
    ProcessPoolSession,
    _ACTIVE_POOL,
    _mp_pool,
    _parallel_map_unordered,
    _parallel_prediction_initializer,
    _parallel_worker_bootstrap,
    resolve_parallel_workers,
    resolve_pool_chunksize,
)
''',
    "aa_portfolio.py": COMMON + '''
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
    ProcessPoolSession,
    _dynamic_cluster_date_task,
    _parallel_map_unordered,
    parallel_execution_enabled,
    resolve_parallel_workers,
)
''',
    "aa_reporting.py": COMMON + '''
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, parse_extra_benchmark_tickers
from aa_constants import normalize_yfinance_ticker
from aa_features import build_feature_by_date
''',
    "aa_execution.py": COMMON + '''
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
''',
    "aa_backtest.py": COMMON + '''
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS
from aa_dashboard import RunDashboard
from aa_execution import PhaseTimings, apply_buy_hold_spread, apply_min_trade_value_filter, estimate_backtest_rebalance_costs, fee_model_label, final_position_hygiene_metrics, enforce_hard_position_count
from aa_features import build_feature_by_date
from aa_models import fit_predict
from aa_parallel import ProcessPoolSession, parallel_execution_enabled, resolve_parallel_workers
from aa_portfolio import apply_dynamic_cluster_overlay, apply_tail_pruning, apply_trade_controls, deduplicate_dataframe_columns, portfolio_diagnostics, project_to_valid_by_blending, select_portfolio, trim_to_beta_cap, trim_to_exposure_cap, trim_to_group_caps, validate_weights
''',
    "aa_runtime.py": COMMON + '''
import argparse
import multiprocessing as mp
from pathlib import Path
from time import monotonic
from typing import Dict, List

import numpy as np
import pandas as pd

from aa_backtest import run_backtest, run_latest_signal, run_walkforward_pipeline
from aa_backtest_ml import precompute_backtest_predictions
from aa_config import BacktestConfig, apply_capital_curve_policy_to_config, enforce_reproducibility_inputs, parse_args
from aa_constants import FEATURE_COLUMNS
from aa_dashboard import RunDashboard
from aa_execution import PhaseTimings, write_run_manifest
from aa_features import (
    ProcessPoolSession,
    _save_feature_cache,
    _try_load_feature_cache,
    apply_dynamic_cluster_overlay,
    build_feature_table,
    data_quality_report,
    prepare_features_for_parallel_runtime,
)
from aa_parallel import ProcessPoolSession as _ProcessPoolSession  # noqa: F401
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
    write_constraint_binding_history,
    write_unknown_mapping_reports,
)
from aa_universe import download_data, load_tickers
''',
}


def extract(ranges: list[tuple[int, int]]) -> str:
    chunks: list[str] = []
    for start, end in ranges:
        chunks.extend(lines[start - 1 : end])
    return "\n".join(chunks) + "\n"


def main() -> None:
    backup = ROOT / "active_alpha_model_monolith_backup.py"
    if not backup.exists():
        backup.write_text(SRC.read_text(encoding="utf-8"), encoding="utf-8")
    for name, ranges in RANGES.items():
        out = ROOT / name
        header = IMPORTS.get(name, COMMON)
        body = extract(ranges)
        out.write_text(header + "\n" + body, encoding="utf-8")
        print("wrote", out.name, "lines", len(body.splitlines()))
    print("backup:", backup)


if __name__ == "__main__":
    main()
