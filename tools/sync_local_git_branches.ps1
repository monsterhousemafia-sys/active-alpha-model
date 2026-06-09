# Sync all local branch refs to integration spine HEAD (no network).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$spine = "development/p10-p12-integration-spine"
$head = (git rev-parse $spine)
if (-not $head) { throw "Branch $spine not found" }

git branch -f main $head 2>$null
if ($LASTEXITCODE -ne 0) {
    git branch main $head
}

$branches = git for-each-ref --format="%(refname:short)" refs/heads/
foreach ($b in $branches) {
    if ($b -eq $spine) { continue }
    git branch -f $b $head
    Write-Host "[OK] $b -> $head"
}

Write-Host ""
Write-Host "All local branches now point to:" (git log -1 --oneline $spine)
