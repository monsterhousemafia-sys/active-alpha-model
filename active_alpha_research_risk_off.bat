@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem Research-Launcher R3 mit erweiterten Naive-Diagnostics (Produktion = gleiche R3-Parameter).
set "AA_RISK_OFF_SELECTION_MODE=mom_blend_blend"
set "AA_RISK_OFF_MOMENTUM_VARIANT=mom_blend_top12"
set "AA_RISK_OFF_MOMENTUM_WEIGHT=0.70"
set "AA_RISK_OFF_GATE_MODE=momentum_rescue"
set "AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE=0.70"
set "AA_RISK_OFF_FORCE_EXIT_ENABLED=0"
set "AA_SKIP_NAIVE_MOMENTUM_BASELINE=0"
set "AA_FORCE_REBUILD_PREDICTIONS=1"
set "AA_NAIVE_DETAILED_REPORTING=1"
set "AA_NAIVE_DETAILED_VARIANTS=mom_blend_top12,mom_63_top12,mom_blend_matched_controls"
set "AA_NAIVE_POSITION_CONTRIBUTIONS=0"

call "%~dp0run_active_alpha_model.bat"
exit /b %ERRORLEVEL%
