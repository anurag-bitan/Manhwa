[CmdletBinding()]
param(
    [ValidatePattern("^[a-zA-Z0-9_-]+$")]
    [string]$Environment = "staging",
    [string]$AppRef = "backend/modal_app.py",
    [switch]$InstallDependencies,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Requirements = Join-Path $Root "backend/requirements-modal.txt"
$AppPath = Join-Path $Root $AppRef

function Invoke-Modal {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & python -m modal @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Modal command failed with exit code $LASTEXITCODE."
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is required. Install Python 3.10+, then run 'python -m pip install -r backend/requirements-modal.txt'."
}
if (-not (Test-Path $AppPath)) {
    throw "Modal app not found at $AppPath. Complete the Modal backend implementation before deploying."
}

Push-Location $Root
try {
    if ($InstallDependencies) {
        if (-not (Test-Path $Requirements)) {
            throw "Deployment requirements not found at $Requirements."
        }
        & python -m pip install -r $Requirements
        if ($LASTEXITCODE -ne 0) {
            throw "Installing Modal deployment dependencies failed."
        }
    }

    Invoke-Modal --version

    if (-not $SkipDeploy) {
        Write-Host "Building images, baking PaddleOCR models, and deploying to '$Environment'..."
        Invoke-Modal deploy --env $Environment $AppRef
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Deployment command completed for '$Environment'."
Write-Host "Copy the environment's modal.run URL from the output and validate it before changing Vercel."
Write-Host "Runbook: docs/MODAL_VERCEL.md"
