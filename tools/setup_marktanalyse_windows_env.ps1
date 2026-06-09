# Persist Marktanalyse / Live-Trading OS environment (User scope).
# Run once from elevated or normal PowerShell in the project root.
$vars = @{
    AA_RUN_MODE = "signal"
    AA_RUNTIME_PROFILE = "exe"
    AA_SIGNAL_REFRESH_ON_STALE_DATA = "1"
    AA_FAST_PATH = "1"
    AA_REUSE_FEATURE_CACHE = "1"
    AA_SKIP_DOWNLOAD_IF_CACHED = "1"
    AA_PARALLEL_BACKTEST_BACKEND = "thread"
}
foreach ($k in $vars.Keys) {
    [Environment]::SetEnvironmentVariable($k, $vars[$k], "User")
    Write-Host "Set User $k=$($vars[$k])"
}
Write-Host "Done. New terminals and Marktanalyse.exe inherit these variables."
