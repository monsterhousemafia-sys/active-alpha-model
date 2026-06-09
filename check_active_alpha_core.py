#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
MODEL = ROOT / "active_alpha_model.py"
ENGINE = ROOT / "paper_trading_engine.py"
CONTROL = ROOT / "active_alpha_control_center.py"

REQUIRED_FILES = [
    "active_alpha_model.py",
    "aa_constants.py",
    "aa_config.py",
    "aa_dashboard.py",
    "aa_universe.py",
    "aa_features.py",
    "aa_models.py",
    "aa_parallel.py",
    "aa_backtest_ml.py",
    "aa_portfolio.py",
    "aa_reporting.py",
    "aa_execution.py",
    "aa_backtest.py",
    "aa_runtime.py",
    "paper_trading_engine.py",
    "active_alpha_control_center.py",
    "run_active_alpha_model.bat",
    "run_paper_trading.bat",
    "run_active_alpha_control_center.bat",
    "active_alpha_settings.bat",
    "load_active_alpha_config.bat",
    "requirements_active_alpha.txt",
    "pytest.ini",
    "tests/conftest.py",
    "tests/test_feature_cache.py",
    "tests/test_prediction_cache.py",
    "tests/test_parallel_workers.py",
    "tests/test_allocator.py",
    "tests/test_operability.py",
    "tests/test_documentation_ops.py",
    "tests/test_config_validation.py",
    "tests/test_reporting_pipeline.py",
    "tests/test_pit_safety.py",
    "tests/test_research_pipeline.py",
    "PERFORMANCE.md",
    "ARCHITECTURE.md",
    "BASELINE.md",
    "run_robustness_tests.py",
    "tools/run_quality_gate.py",
    "run_quality_gate.bat",
    ".github/workflows/quality-gate.yml",
]

REQUIRED_MODEL_FLAGS = [
    "--mode", "--ticker-source", "--membership-file", "--membership-mode",
    "--universe-mode", "--universe-top-n", "--fee-model", "--backtest-capital",
    "--research-backtest-capital", "--trading212-policy", "--trading212-fx-bps",
    "--trading212-sec-fee-rate", "--trading212-finra-taf-per-share", "--slippage-bps",
    "--market-impact-bps", "--order-value-rounding", "--broker-min-remaining-position-value",
    "--execution-policy-mode", "--max-gross-exposure", "--out-dir",
    # Stage 2/3/5 research and portfolio logic
    "--alpha-model-mode", "--extra-benchmarks", "--naive-momentum-variants",
    "--bootstrap-iterations", "--n-jobs", "--cpu-cores", "--parallel-backtest-backend", "--system-ram-gb", "--parallel-profile", "--reuse-feature-cache", "--force-rebuild-features", "--no-feature-cache", "--no-naive-overlap", "--reuse-prediction-cache", "--force-rebuild-predictions", "--no-prediction-cache", "--skip-download-if-cached", "--price-cache-ttl-hours", "--shared-cache-dir", "--dry-run", "--cache-status",
    "--risk-regime-mode", "--exposure-controller",
    "--cash-filler-mode", "--benchmark-completion-ticker", "--benchmark-completion-max-weight", "--low-beta-filler-max-position", "--low-beta-filler-beta-max",
    "--low-beta-filler-min-score", "--low-beta-filler-max-vol-63", "--exposure-recovery-policy",
    "--beta-cap-mode", "--dynamic-beta-risk-off", "--dynamic-beta-normal",
    "--dynamic-beta-risk-on", "--dynamic-beta-strong", "--static-cluster-cap",
    "--dynamic-cluster-cap", "--cluster-constraint-mode", "--cluster-mode",
    "--dynamic-cluster-window-short", "--dynamic-cluster-window-long",
    "--dynamic-cluster-corr-threshold", "--dynamic-cluster-min-overlap",
    "--reproducibility-mode", "--fail-on-reporting-error", "--no-run-manifest",
]
REQUIRED_ENGINE_FLAGS = [
    "--mode", "--target-file", "--paper-dir", "--capital", "--fee-model",
    "--trading212-policy", "--trading212-fx-bps", "--capital-curve-policy",
    "--print-policy", "--min-trade-value", "--fractional", "--execute",
]
REQUIRED_CONTROL_FLAGS = [
    "--mode", "status", "preflight", "summary", "config", "--scope", "--json", "--self-test",
]
REQUIRED_MODEL_SYMBOLS = [
    "def choose_capital_curve_policy", "def apply_capital_curve_policy_to_config",
    "def apply_buy_hold_spread", "def estimate_backtest_trade_cost",
    "def summarize_backtest_diagnostics", "def write_run_manifest", "def maybe_plot", "def apply_benchmark_completion",
    "def resolve_n_jobs", "def precompute_backtest_predictions", "def _compute_rebalance_prediction_task",
    "def run_naive_momentum_baselines", "def compute_benchmark_comparison",
    "def compute_statistical_diagnostics", "def _numeric_series", "def _bool_series",
    "class PhaseTimings", "class ProcessPoolSession", "def load_backtest_state", "def load_feature_engineering_state", "def collect_cache_status_lines", "def build_or_load_features", "def build_feature_by_date", "def _try_load_feature_cache",
    "def _try_load_prediction_cache", "def _prediction_build_fingerprint", "prediction_cache.pkl", "price_cache",
    "phase_timings.json", "reporting_errors.txt", "reporting_errors.json", "reporting_progress.txt",
    "def from_args", "def write_reporting_errors_json", "class ReportingPipeline",     "def run_backtest_reporting", "def write_run_config_snapshot", "class ResearchPipelineResult", "def run_research_pipeline", "def write_backtest_core_outputs",
]
REQUIRED_ENGINE_SYMBOLS = [
    "def choose_capital_curve_policy", "def generate_orders", "def estimate_trade_cost",
    "def run_engine", "def policy_as_dict",
]
REQUIRED_CONFIG_KEYS = [
    "AA_BACKTEST_CAPITAL", "AA_RESEARCH_BACKTEST_CAPITAL", "AA_PAPER_CAPITAL",
    "AA_BETA_CAP_MODE", "AA_CASH_FILLER_MODE", "AA_BENCHMARK_COMPLETION_TICKER", "AA_BENCHMARK_COMPLETION_MAX_WEIGHT", "AA_LOW_BETA_FILLER_MAX_POSITION",
    "AA_CLUSTER_CONSTRAINT_MODE", "AA_STATIC_CLUSTER_CAP", "AA_DYNAMIC_CLUSTER_CAP",
    "AA_N_JOBS", "AA_CPU_CORES", "AA_PARALLEL_BACKTEST_BACKEND", "AA_SYSTEM_RAM_GB", "AA_PARALLEL_PROFILE",
    "AA_SHARED_CACHE_DIR", "AA_ROBUSTNESS_PARALLEL_JOBS",
]
FORBIDDEN_STRINGS = [
    "AA_CAPITAL",
    "ibkr",
]


def run_help(path: Path) -> str:
    proc = subprocess.run([sys.executable, str(path), "--help"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        print(f"[ERROR] {path.name} --help konnte nicht ausgefuehrt werden.")
        print(proc.stdout[-4000:])
        raise SystemExit(proc.returncode or 1)
    return proc.stdout


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def main() -> int:
    missing: list[str] = []
    for name in REQUIRED_FILES:
        if not (ROOT / name).exists():
            missing.append(f"required file {name}")
    if missing:
        print("[ERROR] Fehlende Projektdateien.")
        for item in missing:
            print(" - " + item)
        return 1

    model_help = run_help(MODEL)
    engine_help = run_help(ENGINE)
    control_help = run_help(CONTROL)

    missing += [f"model flag {x}" for x in REQUIRED_MODEL_FLAGS if x not in model_help]
    missing += [f"engine flag {x}" for x in REQUIRED_ENGINE_FLAGS if x not in engine_help]
    missing += [f"control flag {x}" for x in REQUIRED_CONTROL_FLAGS if x not in control_help]

    model_fee_segment = model_help.split("--fee-model", 1)[-1].split("--backtest-capital", 1)[0]
    engine_fee_segment = engine_help.split("--fee-model", 1)[-1].split("--slippage-bps", 1)[0]
    if "trading212_us" not in model_fee_segment or "ibkr" in model_fee_segment.lower():
        missing.append("model fee-model must be Trading-212-only")
    if "trading212_us" not in engine_fee_segment or "ibkr" in engine_fee_segment.lower():
        missing.append("engine fee-model must be Trading-212-only")

    model_text = read_text(MODEL)
    for module_path in sorted(ROOT.glob("aa_*.py")):
        model_text += "\n" + read_text(module_path)
    engine_text = read_text(ENGINE)
    control_text = read_text(CONTROL)
    config_text = read_text(ROOT / "active_alpha_settings.bat") + "\n" + read_text(ROOT / "load_active_alpha_config.bat")
    bat_text = "\n".join(read_text(p) for p in ROOT.glob("*.bat"))

    missing += [f"model symbol {s}" for s in REQUIRED_MODEL_SYMBOLS if s not in model_text]
    missing += [f"engine symbol {s}" for s in REQUIRED_ENGINE_SYMBOLS if s not in engine_text]
    missing += [f"config key {s}" for s in REQUIRED_CONFIG_KEYS if s not in config_text]

    # Legacy capital variable must be gone from batch/config/control. It is allowed nowhere in the current clean package.
    for token in FORBIDDEN_STRINGS:
        haystack = (model_text + "\n" + engine_text + "\n" + control_text + "\n" + config_text + "\n" + bat_text).lower()
        if token.lower() in haystack:
            missing.append(f"forbidden legacy/reference still present: {token}")

    if missing:
        print("[ERROR] Core-Kompatibilitaetspruefung fehlgeschlagen.")
        for item in missing:
            print(" - " + item)
        return 1
    print("[OK] Core-Kompatibilitaetspruefung bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
