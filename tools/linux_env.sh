#!/usr/bin/env bash
# Fail-closed defaults for Linux/WSL compute (sourced by wsl_conductor.sh).
# Broker POSTs stay on Windows Marktanalyse.exe until explicitly re-armed.
export AA_LINUX_COMPUTE_HOST=1
export AA_EXECUTION_DRY_RUN=1
export AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION=1
export AA_NO_LIVE_ORDER_SUBMISSION=1
unset AA_LINUX_ALLOW_LIVE_ORDERS 2>/dev/null || true
