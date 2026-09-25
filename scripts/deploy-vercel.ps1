# Deploy frontend/ to Vercel (production). First run opens browser login.
param(
    [switch]$Preview
)

$ErrorActionPreference = "Stop"
$Frontend = Join-Path (Split-Path -Parent $PSScriptRoot) "frontend"

Push-Location $Frontend
try {
    if ($Preview) {
        npx --yes vercel
    } else {
        npx --yes vercel --prod
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Set VITE_* env vars in Vercel project settings before relying on production."
Write-Host "See docs/RENDER_VERCEL.md"
