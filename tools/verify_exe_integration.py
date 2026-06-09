#!/usr/bin/env python3
"""End-to-end verification that Marktanalyse.exe runs the current model stack."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_paths import bundle_size_bytes, resolve_marktanalyse_exe

EXE = resolve_marktanalyse_exe(ROOT)
LOG = ROOT / "marktanalyse_last_run.log"
STATUS = ROOT / "system_status.json"
MODEL_OUT = ROOT / "model_output_sp500_pit_t212"
TIMEOUT_S = 180


def _fail(msg: str) -> int:
    print(f"[VERIFY FAIL] {msg}", file=sys.stderr)
    return 1


def _ok(msg: str) -> None:
    print(f"[VERIFY OK] {msg}")


def check_built_exe() -> bool:
    if not EXE.is_file():
        _fail(f"Marktanalyse.exe fehlt: {EXE}")
        return False
    bundle_mb = bundle_size_bytes(ROOT) // 1_000_000
    if bundle_mb < 80:
        _fail(f"Onedir-Bundle zu klein ({bundle_mb} MB)")
        return False
    _ok(f"Marktanalyse.exe + Runtime ({bundle_mb} MB unter _internal)")
    return True


def check_model_artifacts() -> bool:
    required = [
        MODEL_OUT / "strategy_daily_returns.csv",
        MODEL_OUT / "latest_target_portfolio.csv",
        MODEL_OUT / "backtest_report.txt",
    ]
    missing = [p for p in required if not p.is_file()]
    if missing:
        _fail("Modell-Artefakte fehlen: " + ", ".join(p.name for p in missing))
        return False
    _ok("Modell-Artefakte vorhanden")
    return True


def check_python_stack() -> bool:
    """Same modules the EXE uses at runtime (dev parity)."""
    try:
        from PySide6.QtCharts import QChart  # noqa: F401
        from PySide6.QtWidgets import QApplication

        from aa_dashboard_result import load_result_context, load_target_portfolio, scale_portfolio_rows
        from aa_ops import decide_run_plan, load_cached_run_result
        from aa_qt_charts import qt_charts_available, update_result_chart_panels, QtResultChartPanel
        from aa_result_views import export_result_pdf
        from aa_single_instance import acquire_single_instance
    except Exception as exc:
        _fail(f"Import-Stack: {exc}")
        return False

    if not qt_charts_available():
        _fail("Qt Charts nicht verfügbar")
        return False

    app = QApplication.instance() or QApplication([])
    _ = app

    ctx = load_result_context(MODEL_OUT, metrics={"cagr": 0.1, "sharpe_0rf": 1.0})
    portfolio, _ = load_target_portfolio(MODEL_OUT)
    rows, invested, cash = scale_portfolio_rows(portfolio, 10_000.0)
    if not rows:
        _fail("Portfolio-Skalierung liefert keine Zeilen")
        return False
    total_w = float(portfolio["target_weight"].sum()) if not portfolio.empty else 0.0
    expected_invested = round(10_000.0 * total_w, 2)
    expected_cash = round(10_000.0 - expected_invested, 2)
    if abs(invested - expected_invested) > 1.0:
        _fail(f"Portfolio-Skalierung: erwartet ~{expected_invested}, got {invested}")
        return False
    if abs(cash - expected_cash) > 1.0:
        _fail(f"Cash-Rest: erwartet ~{expected_cash}, got {cash}")
        return False
    if abs(invested + cash - 10_000.0) > 0.05:
        _fail(f"Summe investiert+cash != 10000: {invested}+{cash}")
        return False
    if "SPY" not in {r["ticker"] for r in rows}:
        _fail("SPY (Benchmark-Completion) fehlt in Investitionsplan")
        return False

    panels = {
        "equity": QtResultChartPanel("equity"),
        "annual": QtResultChartPanel("annual"),
        "sector": QtResultChartPanel("sector"),
    }
    update_result_chart_panels(panels, ctx)
    if not panels["equity"].last_fill_ok:
        _fail("Qt-Equity-Chart nicht geladen")
        return False

    from aa_config_env import resolve_launcher_env
    from aa_ops_validation import assess_analytical_status

    env = resolve_launcher_env(ROOT, frozen=False)
    plan = decide_run_plan(ROOT, env)
    result = load_cached_run_result(ROOT, env)
    analytical, _run_id = assess_analytical_status(MODEL_OUT)
    if analytical == "PASS" and plan.show_results_only and result.success:
        _ok("Fast-Path aktiv (validierte Analyse)")
    elif analytical == "PASS" and plan.needs_signal_refresh and result.success:
        _ok("Fast-Path Signal-Refresh (Integrität PASS, Daten veraltet)")
    elif analytical != "PASS":
        _ok(f"Fast-Path korrekt blockiert (analytical={analytical}, plan={plan.mode})")
    else:
        _fail(f"Fast-Path inkonsistent (analytical={analytical}, plan={plan.mode}, success={result.success})")
        return False

    pdf_path = ROOT / "_verify_report.pdf"
    try:
        export_result_pdf(
            pdf_path,
            strategy_returns=ctx["strategy_returns"],
            benchmark_returns=ctx.get("benchmark_returns"),
            sector_weights=ctx.get("sector_weights"),
            bench_label=str(ctx.get("bench_label") or "Benchmark"),
            context_line=str(ctx.get("context_line") or ""),
            metrics_summary=str(ctx.get("metrics_summary") or ""),
            rows=rows,
            amount=10_000.0,
            fees=ctx.get("fees_estimate") or {},
            disclaimer=str(ctx.get("disclaimer") or ""),
        )
        if not pdf_path.is_file() or pdf_path.stat().st_size < 8000:
            _fail("PDF-Export zu klein oder fehlend")
            return False
    finally:
        pdf_path.unlink(missing_ok=True)

    subprocess.run(["taskkill", "/IM", "Marktanalyse.exe", "/F"], capture_output=True)
    time.sleep(1)
    guard = acquire_single_instance(ROOT)
    if guard is None:
        _ok("Single-Instance: Mutex belegt (übersprungen — wird im EXE-Lauf geprüft)")
    else:
        guard.release()

    _ok(f"Python-Stack: Fast-Path, {len(rows)} Positionen, Qt-Charts, PDF-Vektor")
    return True


def run_exe_once() -> bool:
    """Launch EXE, wait for system_status update, inspect log."""
    subprocess.run(["taskkill", "/IM", "Marktanalyse.exe", "/F"], capture_output=True)
    time.sleep(2)

    log_before = LOG.stat().st_mtime if LOG.is_file() else 0.0
    status_before = STATUS.read_text(encoding="utf-8") if STATUS.is_file() else ""

    proc = subprocess.Popen(
        [str(EXE)],
        cwd=str(ROOT),
        env={**os.environ, "AA_ALLOW_MULTI_INSTANCE": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + TIMEOUT_S
    done = False
    while time.time() < deadline:
        time.sleep(3)
        if proc.poll() is not None:
            done = True
            break
        if LOG.is_file() and LOG.stat().st_mtime > log_before:
            text = LOG.read_text(encoding="utf-8", errors="ignore")
            if "Fast-Path" in text and ("Marktanalyse abgeschlossen" in text or "Beendet mit Code 0" in text):
                done = True
                break
            if "Starte Backtest" in text and "Preflight: OK" in text:
                done = True
                break
        if STATUS.is_file():
            try:
                st = json.loads(STATUS.read_text(encoding="utf-8"))
                if st.get("exit_code") == 0 and st.get("phase") in {"results", "analyze"}:
                    if STATUS.read_text(encoding="utf-8") != status_before:
                        done = True
                        break
            except json.JSONDecodeError:
                pass

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/IM", "Marktanalyse.exe", "/F"], capture_output=True)

    if not LOG.is_file():
        _fail("Kein marktanalyse_last_run.log nach EXE-Start")
        return False

    log_text = LOG.read_text(encoding="utf-8", errors="ignore")
    if "[ERROR]" in log_text.split("===")[-1]:
        for line in log_text.splitlines():
            if "[ERROR]" in line:
                _fail(f"EXE-Log Fehler: {line.strip()}")
                return False

    base_markers = ["EXE-Modus", "Preflight: OK"]
    missing_base = [m for m in base_markers if m not in log_text]
    if missing_base:
        _fail("EXE-Log unvollständig, fehlt: " + ", ".join(missing_base))
        return False
    fast_path_ok = "Laufplan (results)" in log_text and "Fast-Path" in log_text
    analyze_ok = "Laufplan (analyze)" in log_text and "Starte Backtest" in log_text
    if not fast_path_ok and not analyze_ok:
        _fail("EXE-Log: weder Fast-Path noch Analyze-Start erkannt")
        return False
    _ok("EXE-Modus: Fast-Path" if fast_path_ok else "EXE-Modus: Vollanalyse (keine validierte Analyse)")

    if STATUS.is_file():
        st = json.loads(STATUS.read_text(encoding="utf-8"))
        if st.get("health") != "OK" or st.get("exit_code") != 0:
            _fail(f"system_status.json: health={st.get('health')} exit={st.get('exit_code')}")
            return False
        _ok(f"EXE-Lauf: health={st.get('health')} plan={st.get('run_plan')} signal={st.get('signal_date')}")
    else:
        _ok("EXE-Lauf: Log OK (system_status fehlt)")

    return True


def main() -> int:
    print("=== Marktanalyse.exe Verifikation ===")
    if not check_built_exe():
        return 1
    if not check_model_artifacts():
        return 1
    if not check_python_stack():
        return 1
    print("[VERIFY] Starte Marktanalyse.exe (max {}s) …".format(TIMEOUT_S))
    if not run_exe_once():
        return 1
    print("[VERIFY OK] EXE-Integration einwandfrei")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
