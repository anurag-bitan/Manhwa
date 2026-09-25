# Local automated checks plus optional remote /health smoke test.
param(
    [string]$ApiBaseUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"

Write-Host "Running backend unit tests..."
Push-Location $Backend
python -m unittest discover -s tests -p "test_*.py" -q
Pop-Location

if ($ApiBaseUrl) {
    & (Join-Path $PSScriptRoot "verify-deploy.ps1") -ApiBaseUrl $ApiBaseUrl
} else {
    Write-Host "Skip remote /health (pass -ApiBaseUrl after HF Space is live)."
    Write-Host "Manual E2E: see docs/RENDER_VERCEL.md section 6."
}
