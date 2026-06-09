"""Load Active Alpha BAT config into environment and build model argv."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from aa_frozen import apply_frozen_env_defaults

_AA_SET_QUOTED_RE = re.compile(
    r'^set\s+"(?P<key>AA_[^=]+)=(?P<val>[^"]*)"\s*$',
    re.IGNORECASE,
)
_AA_SET_BARE_RE = re.compile(
    r"^set\s+(?P<key>AA_\w+)=(?P<val>[^\s#]*)\s*$",
    re.IGNORECASE,
)

_COMMA_NUMERIC_KEYS = frozenset(
    {
        "AA_BACKTEST_CAPITAL",
        "AA_RESEARCH_BACKTEST_CAPITAL",
        "AA_PAPER_CAPITAL",
        "AA_MAX_GROSS_EXPOSURE",
        "AA_UNIVERSE_MIN_ADV",
        "AA_UNIVERSE_MIN_PRICE",
        "AA_MAX_POSITION",
        "AA_GOOD_REGIME_EXPOSURE",
        "AA_BAD_REGIME_EXPOSURE",
        "AA_RISK_ON_EXPOSURE_FLOOR",
        "AA_MIN_EDGE",
        "AA_LCB_Z",
        "AA_LCB_SCALE",
        "AA_COST_BPS",
        "AA_MAX_ANN_VOL",
        "AA_MAX_SECTOR",
        "AA_MAX_ISSUER",
        "AA_MAX_CORRELATION_CLUSTER",
        "AA_MAX_PORTFOLIO_BETA",
        "AA_DYNAMIC_BETA_RISK_OFF",
        "AA_DYNAMIC_BETA_NORMAL",
        "AA_DYNAMIC_BETA_RISK_ON",
        "AA_DYNAMIC_BETA_STRONG",
        "AA_STATIC_CLUSTER_CAP",
        "AA_DYNAMIC_CLUSTER_CAP",
        "AA_NO_TRADE_BAND",
        "AA_WEIGHT_SMOOTHING",
        "AA_MAX_TURNOVER",
        "AA_SLIPPAGE_BPS",
        "AA_MARKET_IMPACT_BPS",
        "AA_TRADING212_FX_BPS",
        "AA_TRADING212_SEC_FEE_RATE",
        "AA_TRADING212_FINRA_TAF_PER_SHARE",
        "AA_RESIDUAL_WEIGHT_FLOOR",
        "AA_RESIDUAL_SELL_MIN_VALUE",
        "AA_ORDER_VALUE_ROUNDING",
        "AA_BROKER_MIN_REMAINING_POSITION_VALUE",
        "AA_MAX_TAIL_REALLOCATION_PER_NAME",
        "AA_TAIL_REALLOCATION_STEP",
        "AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER",
        "AA_CASH_FILLER_MAX_POSITION",
        "AA_CASH_FILLER_MIN_SCORE",
        "AA_LOW_BETA_FILLER_MAX_POSITION",
        "AA_LOW_BETA_FILLER_BETA_MAX",
        "AA_LOW_BETA_FILLER_MIN_SCORE",
        "AA_LOW_BETA_FILLER_MAX_VOL_63",
        "AA_DYNAMIC_CLUSTER_CORR_THRESHOLD",
        "AA_DYNAMIC_CLUSTER_MIN_OVERLAP",
    }
)

_POLICY_DEFAULTS: Dict[str, str] = {
    "AA_SECTOR_REFERENCE_MODE": "auto",
    "AA_SECTOR_REFERENCE_FILE": "sector_reference.csv",
    "AA_SECTOR_REFERENCE_MAX_AGE_DAYS": "7",
    "AA_SECTOR_YFINANCE_FALLBACK": "1",
    "AA_SECTOR_YFINANCE_CACHE_FILE": "sector_yfinance_cache.json",
    "AA_BACKTEST_CAPITAL": "100000",
    "AA_PAPER_CAPITAL": "100",
    "AA_EXECUTION_POLICY_MODE": "capital_curve",
    "AA_TRADING212_POLICY": "threshold",
    "AA_FRACTIONAL": "J",
    "AA_REBALANCE_EVERY": "5",
    "AA_TOP_K": "15",
    "AA_MAX_POSITION": "0.12",
    "AA_MAX_ISSUER": "0.15",
    "AA_NO_TRADE_BAND": "0.010",
    "AA_MAX_TURNOVER": "0.35",
    "AA_ALPHA_MODEL_MODE": "ensemble",
    "AA_EXTRA_BENCHMARKS": "QQQ,RSP,MTUM,QUAL,VUG,VLUE,USMV,SMH",
    "AA_NAIVE_MOMENTUM_VARIANTS": "mom_63_top12,mom_126_top12,mom_252_21_top12,mom_blend_top12,sector_neutral_momentum,cluster_neutral_momentum",
    "AA_BOOTSTRAP_ITERATIONS": "0",
    "AA_SKIP_NAIVE_MOMENTUM_BASELINE": "1",
    "AA_SKIP_STATISTICAL_DIAGNOSTICS": "1",
    "AA_SKIP_CUSTOM_BENCHMARKS": "1",
    "AA_SKIP_FEATURE_PARQUET_WRITE": "1",
    "AA_NO_PLOT": "1",
    "AA_RISK_OFF_SELECTION_MODE": "mom_blend_blend",
    "AA_RISK_OFF_MOMENTUM_VARIANT": "mom_blend_top12",
    "AA_RISK_OFF_MOMENTUM_WEIGHT": "0.70",
    "AA_RISK_OFF_GATE_MODE": "momentum_rescue",
    "AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE": "0.70",
    "AA_RISK_OFF_FORCE_EXIT_ENABLED": "0",
    "AA_NAIVE_DETAILED_REPORTING": "0",
    "AA_NAIVE_DETAILED_VARIANTS": "mom_blend_top12,mom_63_top12",
    "AA_NAIVE_POSITION_CONTRIBUTIONS": "0",
    "AA_FORCE_REBUILD_PREDICTIONS": "0",
    "AA_PRICE_CACHE_TTL_HOURS": "168",
    "AA_PRICE_DATA_SOURCE": "auto",
    "AA_RANDOM_SEED": "42",
    "AA_RISK_REGIME_MODE": "normal",
    "AA_EXPOSURE_CONTROLLER": "gradual_alpha",
    "AA_CASH_FILLER_MODE": "benchmark_completion",
    "AA_CASH_FILLER_MAX_POSITION": "0.03",
    "AA_CASH_FILLER_MIN_SCORE": "0.0",
    "AA_BENCHMARK_COMPLETION_TICKER": "SPY",
    "AA_BENCHMARK_COMPLETION_MAX_WEIGHT": "0.25",
    "AA_LOW_BETA_FILLER_MAX_POSITION": "0.015",
    "AA_LOW_BETA_FILLER_BETA_MAX": "0.90",
    "AA_LOW_BETA_FILLER_MIN_SCORE": "-0.05",
    "AA_LOW_BETA_FILLER_MAX_VOL_63": "0.75",
    "AA_EXPOSURE_RECOVERY_POLICY": "cause_aware",
    "AA_BETA_CAP_MODE": "dynamic",
    "AA_DYNAMIC_BETA_RISK_OFF": "1.10",
    "AA_DYNAMIC_BETA_NORMAL": "1.25",
    "AA_DYNAMIC_BETA_RISK_ON": "1.40",
    "AA_DYNAMIC_BETA_STRONG": "1.50",
    "AA_STATIC_CLUSTER_CAP": "0.40",
    "AA_DYNAMIC_CLUSTER_CAP": "0.50",
    "AA_CLUSTER_CONSTRAINT_MODE": "static_only",
    "AA_CLUSTER_MODE": "static",
    "AA_DYNAMIC_CLUSTER_WINDOW_SHORT": "126",
    "AA_DYNAMIC_CLUSTER_WINDOW_LONG": "252",
    "AA_DYNAMIC_CLUSTER_CORR_THRESHOLD": "0.65",
    "AA_DYNAMIC_CLUSTER_MIN_OVERLAP": "0.50",
    "AA_REPRODUCIBILITY_MODE": "normal",
    "AA_TAIL_PRUNE_ENABLED": "J",
    "AA_RESIDUAL_WEIGHT_FLOOR": "0.005",
    "AA_RESIDUAL_SELL_MIN_VALUE": "0.01",
    "AA_ORDER_VALUE_ROUNDING": "1.0",
    "AA_BROKER_MIN_REMAINING_POSITION_VALUE": "1.0",
    "AA_MAX_N_POSITIONS_SOFT": "35",
    "AA_MAX_N_POSITIONS_HARD": "45",
    "AA_TAIL_PRUNE_REALLOCATE": "J",
    "AA_MAX_TAIL_REALLOCATION_PER_NAME": "0.01",
    "AA_TAIL_REALLOCATION_STEP": "0.0025",
    "AA_TAIL_REALLOCATION_ROUNDS": "10",
    "AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER": "0.02",
    "AA_N_JOBS": "auto",
    "AA_CPU_CORES": "16",
    "AA_PARALLEL_BACKTEST_BACKEND": "process",
    "AA_SYSTEM_RAM_GB": "64",
    "AA_PARALLEL_PROFILE": "high",
    "AA_RUNTIME_PROFILE": "research",
    "AA_RESERVE_CPU_CORES": "2",
    "AA_VALIDATION_PARALLEL_JOBS": "3",
    "AA_REUSE_FEATURE_CACHE": "1",
    "AA_REUSE_PREDICTION_CACHE": "1",
    "AA_SKIP_DOWNLOAD_IF_CACHED": "1",
    "AA_NO_NAIVE_OVERLAP": "0",
    "AA_SHARED_CACHE_DIR": r"robustness_results_trading212\_shared_cache",
}

_FORBIDDEN_BATCH_TOKENS = (
    "call ",
    "exit /b",
    "goto ",
    "start ",
    "powershell",
    "cmd /c",
    "del ",
    "rmdir ",
    "mkdir ",
)


class ConfigEnvError(ValueError):
    """Fail-closed config load error (invalid or corrupted AA_* values)."""


def _is_comment_or_noise(line: str) -> bool:
    lower = line.lower()
    if not line:
        return True
    if lower.startswith("rem ") or lower.startswith("rem\t"):
        return True
    if line.startswith("::"):
        return True
    if lower.startswith("@echo"):
        return True
    if line.startswith("@") and not lower.startswith("@rem"):
        return True
    return False


def _parse_set_line(line: str) -> tuple[str, str] | None:
    for pattern in (_AA_SET_QUOTED_RE, _AA_SET_BARE_RE):
        match = pattern.match(line)
        if match:
            key = match.group("key").strip()
            if not key.startswith("AA_"):
                return None
            return key, match.group("val").strip()
    lower = line.lower()
    for token in _FORBIDDEN_BATCH_TOKENS:
        if token in lower:
            raise ConfigEnvError(f"forbidden_batch_command_in_config:{line[:80]}")
    return None


def parse_aa_env_files(root: Path) -> Dict[str, str]:
    """Read AA_* variables from settings BAT files without spawning cmd.exe."""
    out: Dict[str, str] = {}
    for name in ("active_alpha_settings.bat", "active_alpha_user_config.bat"):
        path = root / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if _is_comment_or_noise(line):
                continue
            parsed = _parse_set_line(line)
            if parsed is None:
                continue
            key, val = parsed
            out[key] = val
    return out


def _normalize_commas(env: Dict[str, str]) -> None:
    for key in _COMMA_NUMERIC_KEYS:
        if key in env and env[key]:
            env[key] = env[key].replace(",", ".")


def _apply_policy_defaults(env: Dict[str, str]) -> None:
    if not env.get("AA_BACKTEST_CAPITAL"):
        env["AA_BACKTEST_CAPITAL"] = "100000"
    if not env.get("AA_PAPER_CAPITAL"):
        env["AA_PAPER_CAPITAL"] = "100"
    if not env.get("AA_RESEARCH_BACKTEST_CAPITAL"):
        env["AA_RESEARCH_BACKTEST_CAPITAL"] = env.get("AA_BACKTEST_CAPITAL", "100000")
    for key, default in _POLICY_DEFAULTS.items():
        if not str(env.get(key, "") or "").strip():
            env[key] = default


def _validate_fail_closed(env: Mapping[str, str]) -> None:
    for key in ("AA_BACKTEST_OUT_DIR", "AA_PAPER_MODEL_OUT_DIR"):
        val = str(env.get(key, "") or "").strip()
        if val.upper() == "T_DIR":
            raise ConfigEnvError(f"{key} corrupted (T_DIR)")
    out_dir = str(env.get("AA_BACKTEST_OUT_DIR", "") or "").strip()
    paper_dir = str(env.get("AA_PAPER_DIR", "") or "").strip()
    if not out_dir:
        raise ConfigEnvError("AA_BACKTEST_OUT_DIR missing after config load")
    if not paper_dir:
        raise ConfigEnvError("AA_PAPER_DIR missing after config load")


def finalize_aa_env(raw: Dict[str, str], *, validate: bool = True) -> Dict[str, str]:
    env = dict(raw)
    _apply_policy_defaults(env)
    _normalize_commas(env)
    if validate:
        _validate_fail_closed(env)
    return env


def load_aa_env(root: Path, *, check: bool = True) -> Dict[str, str]:
    """Load AA_* variables by parsing settings BAT files (no cmd.exe / batch execution)."""
    root = Path(root)
    if not (root / "active_alpha_settings.bat").is_file():
        return {}
    try:
        return finalize_aa_env(parse_aa_env_files(root), validate=check)
    except ConfigEnvError:
        if check:
            raise
        return {}


def resolve_launcher_env(root: Path, *, frozen: bool | None = None) -> Dict[str, str]:
    """Load AA_* for Marktanalyse.exe without cmd.exe."""
    if frozen is None:
        frozen = getattr(sys, "frozen", False)
    env = load_aa_env(root)
    if frozen:
        env = apply_frozen_env_defaults(env, force=True, root=root)
    return env


def _flag(name: str, value: str) -> List[str]:
    if value == "":
        return []
    return [name, value]


def _yes(env: Dict[str, str], key: str) -> bool:
    return env.get(key, "").strip().upper() in {"1", "J", "Y", "YES", "TRUE"}


def _append_env(argv: List[str], env: Dict[str, str], flag: str, key: str) -> None:
    val = env.get(key, "")
    if str(val).strip() != "":
        argv.extend([flag, str(val).strip()])


def build_backtest_argv(env: Dict[str, str]) -> List[str]:
    """Build active_alpha_model.py argv from AA_* environment (mirrors run_active_alpha_model.bat)."""
    argv = [
        "active_alpha_model.py",
        "--mode",
        env.get("AA_RUN_MODE", "backtest"),
        "--ticker-source",
        env.get("AA_BACKTEST_TICKER_SOURCE", "sp500_pit"),
        "--ticker-cache-dir",
        env.get("AA_TICKER_CACHE_DIR", "ticker_cache"),
        "--ticker-cache-max-age-days",
        env.get("AA_TICKER_CACHE_MAX_AGE_DAYS", "30"),
        "--membership-file",
        env.get("AA_MEMBERSHIP_FILE", ""),
        "--membership-mode",
        env.get("AA_BACKTEST_MEMBERSHIP_MODE", "pit"),
        "--asset-master-file",
        env.get("AA_ASSET_MASTER_FILE", ""),
        "--benchmark",
        env.get("AA_BENCHMARK", "SPY"),
        "--start",
        env.get("AA_START_DATE", "2010-01-01"),
        "--out-dir",
        env.get("AA_BACKTEST_OUT_DIR", "model_output"),
        "--fee-model",
        "trading212_us",
    ]
    numeric_flags = [
        ("--signal-lookback-years", "AA_SIGNAL_LOOKBACK_YEARS"),
        ("--horizon", "AA_HORIZON"),
        ("--rebalance-every", "AA_REBALANCE_EVERY"),
        ("--top-k", "AA_TOP_K"),
        ("--max-position", "AA_MAX_POSITION"),
        ("--good-regime-exposure", "AA_GOOD_REGIME_EXPOSURE"),
        ("--bad-regime-exposure", "AA_BAD_REGIME_EXPOSURE"),
        ("--risk-on-exposure-floor", "AA_RISK_ON_EXPOSURE_FLOOR"),
        ("--min-edge", "AA_MIN_EDGE"),
        ("--lcb-z", "AA_LCB_Z"),
        ("--lcb-scale", "AA_LCB_SCALE"),
        ("--cost-bps", "AA_COST_BPS"),
        ("--universe-mode", "AA_UNIVERSE_MODE"),
        ("--universe-top-n", "AA_UNIVERSE_TOP_N"),
        ("--universe-adv-lookback", "AA_UNIVERSE_ADV_LOOKBACK"),
        ("--universe-min-adv", "AA_UNIVERSE_MIN_ADV"),
        ("--universe-min-price", "AA_UNIVERSE_MIN_PRICE"),
        ("--universe-min-history-days", "AA_UNIVERSE_MIN_HISTORY_DAYS"),
        ("--min-adv", "AA_UNIVERSE_MIN_ADV"),
        ("--max-ann-vol", "AA_MAX_ANN_VOL"),
        ("--max-sector", "AA_MAX_SECTOR"),
        ("--max-issuer", "AA_MAX_ISSUER"),
        ("--max-correlation-cluster", "AA_MAX_CORRELATION_CLUSTER"),
        ("--max-portfolio-beta", "AA_MAX_PORTFOLIO_BETA"),
        ("--dynamic-beta-risk-off", "AA_DYNAMIC_BETA_RISK_OFF"),
        ("--dynamic-beta-normal", "AA_DYNAMIC_BETA_NORMAL"),
        ("--dynamic-beta-risk-on", "AA_DYNAMIC_BETA_RISK_ON"),
        ("--dynamic-beta-strong", "AA_DYNAMIC_BETA_STRONG"),
        ("--static-cluster-cap", "AA_STATIC_CLUSTER_CAP"),
        ("--dynamic-cluster-cap", "AA_DYNAMIC_CLUSTER_CAP"),
        ("--no-trade-band", "AA_NO_TRADE_BAND"),
        ("--weight-smoothing", "AA_WEIGHT_SMOOTHING"),
        ("--max-turnover", "AA_MAX_TURNOVER"),
        ("--residual-weight-floor", "AA_RESIDUAL_WEIGHT_FLOOR"),
        ("--residual-sell-min-value", "AA_RESIDUAL_SELL_MIN_VALUE"),
        ("--order-value-rounding", "AA_ORDER_VALUE_ROUNDING"),
        ("--broker-min-remaining-position-value", "AA_BROKER_MIN_REMAINING_POSITION_VALUE"),
        ("--max-n-positions-soft", "AA_MAX_N_POSITIONS_SOFT"),
        ("--max-n-positions-hard", "AA_MAX_N_POSITIONS_HARD"),
        ("--max-tail-reallocation-per-name", "AA_MAX_TAIL_REALLOCATION_PER_NAME"),
        ("--tail-reallocation-step", "AA_TAIL_REALLOCATION_STEP"),
        ("--tail-reallocation-rounds", "AA_TAIL_REALLOCATION_ROUNDS"),
        ("--tail-prune-min-exposure-buffer", "AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER"),
        ("--backtest-capital", "AA_BACKTEST_CAPITAL"),
        ("--research-backtest-capital", "AA_RESEARCH_BACKTEST_CAPITAL"),
        ("--slippage-bps", "AA_SLIPPAGE_BPS"),
        ("--market-impact-bps", "AA_MARKET_IMPACT_BPS"),
        ("--trading212-sec-fee-rate", "AA_TRADING212_SEC_FEE_RATE"),
        ("--trading212-finra-taf-per-share", "AA_TRADING212_FINRA_TAF_PER_SHARE"),
        ("--trading212-fx-bps", "AA_TRADING212_FX_BPS"),
        ("--max-gross-exposure", "AA_MAX_GROSS_EXPOSURE"),
        ("--train-years", "AA_TRAIN_YEARS"),
        ("--ml-retrain-every", "AA_ML_RETRAIN_EVERY"),
        ("--min-train-rows", "AA_MIN_TRAIN_ROWS"),
        ("--bootstrap-iterations", "AA_BOOTSTRAP_ITERATIONS"),
        ("--random-seed", "AA_RANDOM_SEED"),
        ("--n-jobs", "AA_N_JOBS"),
        ("--cpu-cores", "AA_CPU_CORES"),
        ("--system-ram-gb", "AA_SYSTEM_RAM_GB"),
        ("--price-cache-ttl-hours", "AA_PRICE_CACHE_TTL_HOURS"),
        ("--risk-off-momentum-weight", "AA_RISK_OFF_MOMENTUM_WEIGHT"),
        ("--risk-off-momentum-rescue-quantile", "AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE"),
        ("--cash-filler-max-position", "AA_CASH_FILLER_MAX_POSITION"),
        ("--cash-filler-min-score", "AA_CASH_FILLER_MIN_SCORE"),
        ("--benchmark-completion-max-weight", "AA_BENCHMARK_COMPLETION_MAX_WEIGHT"),
        ("--low-beta-filler-max-position", "AA_LOW_BETA_FILLER_MAX_POSITION"),
        ("--low-beta-filler-beta-max", "AA_LOW_BETA_FILLER_BETA_MAX"),
        ("--low-beta-filler-min-score", "AA_LOW_BETA_FILLER_MIN_SCORE"),
        ("--low-beta-filler-max-vol-63", "AA_LOW_BETA_FILLER_MAX_VOL_63"),
        ("--dynamic-cluster-window-short", "AA_DYNAMIC_CLUSTER_WINDOW_SHORT"),
        ("--dynamic-cluster-window-long", "AA_DYNAMIC_CLUSTER_WINDOW_LONG"),
        ("--dynamic-cluster-corr-threshold", "AA_DYNAMIC_CLUSTER_CORR_THRESHOLD"),
        ("--dynamic-cluster-min-overlap", "AA_DYNAMIC_CLUSTER_MIN_OVERLAP"),
    ]
    for flag, key in numeric_flags:
        if env.get(key, "").strip():
            argv.extend(_flag(flag, env[key]))

    choice_flags = [
        ("--beta-cap-mode", "AA_BETA_CAP_MODE"),
        ("--cluster-constraint-mode", "AA_CLUSTER_CONSTRAINT_MODE"),
        ("--execution-policy-mode", "AA_EXECUTION_POLICY_MODE"),
        ("--trading212-policy", "AA_TRADING212_POLICY"),
        ("--parallel-backtest-backend", "AA_PARALLEL_BACKTEST_BACKEND"),
        ("--parallel-profile", "AA_PARALLEL_PROFILE"),
        ("--alpha-model-mode", "AA_ALPHA_MODEL_MODE"),
        ("--risk-off-selection-mode", "AA_RISK_OFF_SELECTION_MODE"),
        ("--risk-off-momentum-variant", "AA_RISK_OFF_MOMENTUM_VARIANT"),
        ("--risk-off-gate-mode", "AA_RISK_OFF_GATE_MODE"),
        ("--risk-regime-mode", "AA_RISK_REGIME_MODE"),
        ("--exposure-controller", "AA_EXPOSURE_CONTROLLER"),
        ("--cash-filler-mode", "AA_CASH_FILLER_MODE"),
        ("--benchmark-completion-ticker", "AA_BENCHMARK_COMPLETION_TICKER"),
        ("--exposure-recovery-policy", "AA_EXPOSURE_RECOVERY_POLICY"),
        ("--cluster-mode", "AA_CLUSTER_MODE"),
        ("--reproducibility-mode", "AA_REPRODUCIBILITY_MODE"),
    ]
    for flag, key in choice_flags:
        _append_env(argv, env, flag, key)

    if env.get("AA_EXTRA_BENCHMARKS", "").strip():
        argv.extend(["--extra-benchmarks", env["AA_EXTRA_BENCHMARKS"].strip()])
    if env.get("AA_NAIVE_MOMENTUM_VARIANTS", "").strip():
        argv.extend(["--naive-momentum-variants", env["AA_NAIVE_MOMENTUM_VARIANTS"].strip()])
    if env.get("AA_NAIVE_DETAILED_VARIANTS", "").strip():
        argv.extend(["--naive-detailed-variants", env["AA_NAIVE_DETAILED_VARIANTS"].strip()])
    if env.get("AA_SHARED_CACHE_DIR", "").strip():
        argv.extend(["--shared-cache-dir", env["AA_SHARED_CACHE_DIR"].strip()])
    if _yes(env, "AA_REUSE_FEATURE_CACHE"):
        argv.append("--reuse-feature-cache")
    if _yes(env, "AA_REUSE_PREDICTION_CACHE"):
        argv.append("--reuse-prediction-cache")
    if _yes(env, "AA_SKIP_DOWNLOAD_IF_CACHED"):
        argv.append("--skip-download-if-cached")
    if _yes(env, "AA_FORCE_REBUILD_PREDICTIONS"):
        argv.append("--force-rebuild-predictions")
    if _yes(env, "AA_FORCE_REBUILD_FEATURES"):
        argv.append("--force-rebuild-features")
    if _yes(env, "AA_SKIP_NAIVE_MOMENTUM_BASELINE"):
        argv.append("--no-naive-momentum-baseline")
    if _yes(env, "AA_SKIP_STATISTICAL_DIAGNOSTICS"):
        argv.append("--no-statistical-diagnostics")
    if _yes(env, "AA_SKIP_CUSTOM_BENCHMARKS"):
        argv.append("--no-custom-benchmarks")
    if _yes(env, "AA_SKIP_FEATURE_PARQUET_WRITE"):
        argv.append("--skip-feature-parquet-write")
    if _yes(env, "AA_NO_PLOT"):
        argv.append("--no-plot")
    if _yes(env, "AA_NO_NAIVE_OVERLAP"):
        argv.append("--no-naive-overlap")
    if _yes(env, "AA_TAIL_PRUNE_ENABLED"):
        argv.append("--tail-prune-enabled")
    if env.get("AA_TAIL_PRUNE_REALLOCATE", "").strip().upper() == "N":
        argv.append("--no-tail-prune-reallocate")
    if _yes(env, "AA_RISK_OFF_FORCE_EXIT_ENABLED"):
        argv.append("--risk-off-force-exit-enabled")
    if _yes(env, "AA_NAIVE_DETAILED_REPORTING"):
        argv.append("--naive-detailed-reporting")
    if _yes(env, "AA_NAIVE_POSITION_CONTRIBUTIONS"):
        argv.append("--naive-position-contributions")
    if _yes(env, "AA_GUI"):
        argv.append("--gui")
    if _yes(env, "AA_PLAIN_PROGRESS"):
        argv.append("--plain-progress")
    if _yes(env, "AA_NO_GUI"):
        argv.append("--no-gui")
    extra = env.get("AA_ADDITIONAL_MODEL_ARGS", "").strip()
    if extra:
        argv.extend(extra.split())
    return argv
