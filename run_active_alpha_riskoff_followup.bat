@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "AA_GUI=0"
set "AA_NONINTERACTIVE=1"
set "PYTHONUNBUFFERED=1"
if "%AA_CPU_CORES%"=="" set "AA_CPU_CORES=16"
if "%AA_RISKOFF_PARALLEL_JOBS%"=="" set "AA_RISKOFF_PARALLEL_JOBS=2"

echo ============================================================
echo Active Alpha - Risk-Off Follow-up (Cost Stress + Quantile)
echo ============================================================

.venv\Scripts\python.exe run_active_alpha_riskoff_followup.py --parallel-jobs %AA_RISKOFF_PARALLEL_JOBS% --cpu-cores %AA_CPU_CORES% %*
exit /b %ERRORLEVEL%
