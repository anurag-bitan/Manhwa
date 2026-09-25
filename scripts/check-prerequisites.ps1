# Pre-flight checks before deploy-all.ps1
. "$PSScriptRoot\gcloud-env.ps1"
$PROJECT_ID = "manhwa-ai-509114"
$Gcloud = Get-GcloudExe

Write-Host "=== Deploy prerequisites ($PROJECT_ID) ===" -ForegroundColor Cyan

$billing = & $Gcloud billing projects describe $PROJECT_ID --format="value(billingEnabled)" 2>$null
if ($billing -ne "True") {
    Write-Host "[BLOCKED] Billing is not open on this project." -ForegroundColor Red
    Write-Host "  Fix: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
    Write-Host "  Your billing account 'My Billing Account' shows OPEN=False — reactivate or link a valid account."
    exit 1
}
Write-Host "[OK] Billing enabled" -ForegroundColor Green

$acct = (& $Gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null).Trim()
if ($acct -ne "anuragproffesional2@gmail.com") {
    Write-Host "[BLOCKED] Run: gcloud auth login anuragproffesional2@gmail.com" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] gcloud account: $acct" -ForegroundColor Green

if (-not $env:SUPABASE_SERVICE_ROLE_KEY) {
    Write-Host "[WARN] Set SUPABASE_SERVICE_ROLE_KEY before deploy, or paste when prompted." -ForegroundColor Yellow
}

Write-Host "Ready for: .\deploy-all.ps1" -ForegroundColor Green
