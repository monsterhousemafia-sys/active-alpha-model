@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "AA_GUI=0"
set "AA_NONINTERACTIVE=1"
set "PYTHONUNBUFFERED=1"
if "%AA_CPU_CORES%"=="" set "AA_CPU_CORES=16"
if "%AA_SYSTEM_RAM_GB%"=="" set "AA_SYSTEM_RAM_GB=64"
if "%AA_PARALLEL_PROFILE%"=="" set "AA_PARALLEL_PROFILE=high"
if "%AA_PARALLEL_BACKTEST_BACKEND%"=="" set "AA_PARALLEL_BACKTEST_BACKEND=process"
if "%AA_RISKOFF_PARALLEL_JOBS%"=="" set "AA_RISKOFF_PARALLEL_JOBS=2"

echo ============================================================
echo Active Alpha - Risk-Off Momentum Rescue Research Matrix
echo ============================================================
echo Output: research_riskoff_experiments\
echo Shared cache: robustness_results_trading212\_shared_cache (falls vorhanden)
echo.

.venv\Scripts\python.exe run_active_alpha_riskoff_experiments.py --parallel-jobs %AA_RISKOFF_PARALLEL_JOBS% --cpu-cores %AA_CPU_CORES% %*
exit /b %ERRORLEVEL%
