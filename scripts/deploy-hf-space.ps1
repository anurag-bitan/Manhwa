# Legacy: Hugging Face Docker Space upload (requires HF Pro).
# Preferred backend host: Render — see docs/RENDER_VERCEL.md and render.yaml
param(
    [string]$SpaceId = "Gol-D0-Roger/manhwa-ai-api",
    [ValidateSet("cpu-basic", "cpu-upgrade")]
    [string]$Flavor = "cpu-basic"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"

Write-Host "Checking Hugging Face auth..."
hf auth whoami

Write-Host "Creating Space (ignored if exists): $SpaceId"
hf repos create $SpaceId --type space --space-sdk docker --flavor $Flavor --public --exist-ok

Write-Host "Uploading backend files to Space..."
hf upload $SpaceId $Backend --type space --exclude ".env" --exclude ".env.*" --exclude "__pycache__" --exclude ".pytest_cache" --exclude "tests" --commit-message "Deploy Manhwa AI API"

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open https://huggingface.co/spaces/$SpaceId/settings"
Write-Host "  2. Add secrets listed in docs/HF_SPACES_VERCEL.md"
Write-Host "  3. Wait for the Docker build to finish"
Write-Host "  4. Run: .\scripts\verify-deploy.ps1 -ApiBaseUrl https://<your-space>.hf.space"
