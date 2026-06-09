from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _offscreen_qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from aa_dashboard_qt_window import AppSession

        AppSession._instance = None
    except Exception:
        pass
    yield
    try:
        from aa_dashboard_qt_window import AppSession

        if AppSession._instance is not None:
            AppSession._instance.stop_timer()
        AppSession._instance = None
    except Exception:
        pass


def _require_qt():
    from aa_dashboard_qt import qt_available

    if not qt_available():
        pytest.skip("PySide6 not installed")


def test_qt_available_or_skip():
    _require_qt()


def test_dashboard_progress_updates():
    _require_qt()
    from aa_dashboard_qt import RunDashboardQt

    dash = RunDashboardQt(enabled=True, title="Test")
    dash.start(total_phases=5, out_dir=Path("."))
    dash.start_phase("Pfad-Simulation (Phase B)", total=100, step="Test")
    dash.advance_phase(50)
    assert dash._core.progress_pct() >= 50
    win = dash._session.window
    assert win._progress.value() > 0
    assert win._log_lines_shown > 0
    dash._session.stop_timer()


def test_refresh_paints_without_event_loop():
    """advance_phase must update widgets even when QTimer cannot fire."""
    _require_qt()
    from aa_dashboard_qt import RunDashboardQt

    dash = RunDashboardQt(enabled=True, title="Test")
    dash.start(total_phases=5, out_dir=Path("."))
    dash.start_phase("Feature Engineering", total=5, step="Ticker 1/5")
    for i in range(5):
        dash.advance_phase(1, step=f"Ticker {i + 1}/5")
    win = dash._session.window
    assert win._progress.value() == dash._core.progress_pct()
    assert "Ticker 5/5" in win._step_detail.text()
    dash._session.stop_timer()


def test_launcher_ui_startup_and_logs():
    _require_qt()
    from aa_dashboard_qt import LauncherUI

    with LauncherUI() as ui:
        ui.activate("env")
        ui.log("[TEST] Umgebung wird geprüft …")
        ui.done("env")
        win = ui._session.window
        assert win._mode == "launcher"
        assert win._log_lines_shown >= 2
        assert win._progress.value() >= 0
        ui._session.stop_timer()


def test_launcher_shows_single_step_counter():
    _require_qt()
    from aa_dashboard_qt import LauncherUI

    with LauncherUI() as ui:
        ui.activate("core")
        win = ui._session.window
        assert win._step_counter.text() == "Schritt 3 von 6"
        assert win._step_title.text() == "Core-Check"
        ui._session.stop_timer()


def test_launcher_finalize_fast_path_passes_result(monkeypatch):
    _require_qt()
    monkeypatch.setenv("AA_NONINTERACTIVE", "1")
    from aa_dashboard_qt import LauncherUI
    from aa_runtime import RunResult

    out = Path("model_output_sp500_pit_t212")
    if not (out / "strategy_daily_returns.csv").is_file():
        pytest.skip("model output missing")

    def _fake_load_result_context(*args, **kwargs):
        return {
            "metrics_summary": "cagr: 10%",
            "metrics_html": "",
            "context_line": "Signal test",
            "disclaimer": "",
            "portfolio": None,
            "chart_png": b"",
            "equity_chart_png": b"",
            "annual_chart_png": b"",
            "sector_chart_png": b"",
        }

    monkeypatch.setattr("aa_dashboard_result.load_result_context", _fake_load_result_context)

    result = RunResult(
        out_dir=out.resolve(),
        success=True,
        metrics={"cagr": 0.1, "sharpe_0rf": 1.0},
        signal_date="2026-05-29",
    )
    with LauncherUI() as ui:
        ui.handoff_to_backtest()
        ui.finalize(success=True, result=result)
        win = ui._session.window
        assert win._stack.currentWidget() == win._result_page
        assert win._mode == "backtest"
        ui._session.stop_timer()


def test_launcher_handoff_to_backtest():
    _require_qt()
    from aa_dashboard_qt import LauncherUI

    with LauncherUI() as ui:
        ui.activate("run")
        dash = ui.handoff_to_backtest()
        dash.start(total_phases=5, out_dir=Path("model_output"))
        dash.start_phase("Marktdaten laden", total=1, step="3 Ticker")
        dash.advance_phase(1, step="3 Datenreihen geladen")
        win = ui._session.window
        assert win._mode == "backtest"
        assert win._progress.value() > 0
        assert ui._session._sync_fn.__func__ is dash._paint.__func__
        ui._session.stop_timer()


def test_run_subprocess_with_ui_pumps():
    _require_qt()
    import sys

    from aa_dashboard_qt import LauncherUI, run_subprocess_with_ui

    with LauncherUI() as ui:
        ui.activate("env")
        before = ui._session.window._log_lines_shown
        run_subprocess_with_ui(
            [sys.executable, "-c", "import time; time.sleep(0.15)"],
            check=True,
        )
        ui.log("[TEST] Subprozess fertig")
        assert ui._session.window._log_lines_shown >= before
        ui._session.stop_timer()


def test_pump_ui_no_session_is_safe():
    from aa_ui_pump import pump_ui

    pump_ui(force=True)


def test_bootstrap_qt_native_windows_uses_round_dpi():
    import os

    from aa_qt_render import bootstrap_qt_native_windows

    bootstrap_qt_native_windows(force=True)
    assert "QT_OPENGL" not in os.environ
    assert "QSG_RHI_BACKEND" not in os.environ


def test_auto_run_mode_default_for_frozen(monkeypatch):
    from aa_qt_render import is_auto_run_mode

    monkeypatch.delenv("AA_AUTO_RUN", raising=False)
    monkeypatch.delenv("AA_NONINTERACTIVE", raising=False)
    monkeypatch.setattr("aa_qt_render.sys.frozen", True, raising=False)
    assert is_auto_run_mode() is True
    monkeypatch.setenv("AA_AUTO_RUN", "0")
    assert is_auto_run_mode() is False


def test_configure_cpu_compute_env_limits_blas_threads():
    import os

    from aa_qt_render import configure_cpu_compute_env

    configure_cpu_compute_env(launcher=True)
    assert os.environ.get("OMP_NUM_THREADS") == "1"
    assert os.environ.get("MPLBACKEND") == "Agg"


def test_cancellation_raises():
    from aa_cancellation import check_cancelled, clear_cancel, request_cancel

    clear_cancel()
    request_cancel()
    with pytest.raises(KeyboardInterrupt):
        check_cancelled("test")


def test_build_backtest_argv_from_env():
    from aa_config_env import build_backtest_argv

    argv = build_backtest_argv({"AA_BACKTEST_OUT_DIR": "model_output", "AA_BENCHMARK": "SPY", "AA_START_DATE": "2010-01-01"})
    assert "active_alpha_model.py" in argv[0] or argv[0].endswith("active_alpha_model.py")
    assert "--mode" in argv and argv[argv.index("--mode") + 1] == "backtest"
    assert "--out-dir" in argv


def test_frozen_env_uses_both_mode_for_portfolio():
    from aa_frozen import apply_frozen_env_defaults

    env = apply_frozen_env_defaults({}, force=True)
    assert env.get("AA_RUN_MODE") == "signal"


def test_build_backtest_argv_respects_run_mode():
    from aa_config_env import build_backtest_argv

    argv = build_backtest_argv({"AA_RUN_MODE": "both", "AA_BACKTEST_OUT_DIR": "out"})
    assert "--mode" in argv
    assert argv[argv.index("--mode") + 1] == "both"


def test_build_backtest_argv_passes_r3_and_tail_prune():
    from aa_config_env import build_backtest_argv

    env = {
        "AA_BACKTEST_OUT_DIR": "model_output_sp500_pit_t212",
        "AA_BENCHMARK": "SPY",
        "AA_START_DATE": "2012-01-01",
        "AA_RISK_OFF_SELECTION_MODE": "mom_blend_blend",
        "AA_RISK_OFF_GATE_MODE": "momentum_rescue",
        "AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE": "0.60",
        "AA_TAIL_PRUNE_ENABLED": "J",
        "AA_CLUSTER_MODE": "static",
        "AA_MAX_PORTFOLIO_BETA": "1.35",
    }
    argv = build_backtest_argv(env)
    assert "--risk-off-selection-mode" in argv
    assert "mom_blend_blend" in argv
    assert "--risk-off-momentum-rescue-quantile" in argv
    assert "0.60" in argv
    assert "--tail-prune-enabled" in argv
    assert "--cluster-mode" in argv
    assert "static" in argv
    assert "--max-portfolio-beta" in argv
    assert "1.35" in argv


def test_resolve_launcher_env_forces_thread_backend_when_frozen():
    from aa_config_env import resolve_launcher_env

    root = Path(__file__).resolve().parents[1]
    env = resolve_launcher_env(root, frozen=True)
    assert env.get("AA_PARALLEL_BACKTEST_BACKEND") == "thread"
    assert env.get("AA_SKIP_DOWNLOAD_IF_CACHED") == "1"
    assert env.get("AA_N_JOBS") == "auto"
    argv = __import__("aa_config_env", fromlist=["build_backtest_argv"]).build_backtest_argv({**env, "AA_GUI": "1"})
    idx = argv.index("--parallel-backtest-backend")
    assert argv[idx + 1] == "thread"


def test_frozen_parallel_uses_threads_not_processes(monkeypatch):
    from aa_frozen import apply_frozen_runtime_config, effective_parallel_backend
    from aa_parallel import parallel_execution_enabled, resolve_parallel_workers

    monkeypatch.setattr("aa_frozen.is_frozen_exe", lambda: True)
    monkeypatch.setattr("aa_parallel.is_frozen_exe", lambda: True)
    cfg = type("Cfg", (), {"n_jobs": "auto", "cpu_cores": 16, "system_ram_gb": 64, "parallel_profile": "high"})()
    apply_frozen_runtime_config(cfg)
    assert cfg.parallel_backtest_backend == "thread"
    assert effective_parallel_backend(cfg, "process") == "thread"
    assert parallel_execution_enabled(cfg, backend="thread") is True
    assert resolve_parallel_workers(cfg, backend="thread") > 1


def test_show_result_loads_chart_without_settext_error():
    _require_qt()
    from aa_dashboard_qt import RunDashboardQt

    model_out = Path(__file__).resolve().parents[1] / "model_output_sp500_pit_t212"
    if not (model_out / "strategy_daily_returns.csv").is_file():
        pytest.skip("model output missing")
    dash = RunDashboardQt(enabled=True, title="Test")
    dash.start(total_phases=5, out_dir=model_out)
    win = dash._session.window
    win.show_result(
        success=True,
        out_dir=str(model_out),
        metrics={"cagr": 0.265, "sharpe_0rf": 1.14, "max_drawdown": -0.27},
    )
    assert win._result_context_label.text()
    assert win._portfolio_table.rowCount() >= 0
    dash._session.stop_timer()


def test_load_aa_env_reads_config():
    from aa_config_env import load_aa_env

    import time

    root = Path(__file__).resolve().parents[1]
    start = time.monotonic()
    env = load_aa_env(root)
    assert time.monotonic() - start < 5.0
    assert isinstance(env, dict)
    assert env.get("AA_BACKTEST_OUT_DIR")
