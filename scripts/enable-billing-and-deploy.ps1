# Run as anuragproffesional2@gmail.com after creating/linking an OPEN billing account.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\gcloud-env.ps1"

$PROJECT_ID = "manhwa-ai-509114"
$ACCOUNT = "anuragproffesional2@gmail.com"
$Gcloud = Get-GcloudExe

& $Gcloud config set account $ACCOUNT | Out-Null
& $Gcloud config set project $PROJECT_ID | Out-Null

$billing = (& $Gcloud billing projects describe $PROJECT_ID --format="value(billingEnabled)" 2>$null).Trim()
if ($billing -ne "True") {
    Write-Host "Billing is not active yet." -ForegroundColor Yellow
    Write-Host "1. Sign in to Google Cloud as $ACCOUNT"
    Write-Host "2. Create or reactivate billing:"
    Write-Host "   https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
    Write-Host "3. Press Enter here after billing shows ENABLED ..."
    Read-Host
}

$billing = (& $Gcloud billing projects describe $PROJECT_ID --format="value(billingEnabled)" 2>$null).Trim()
if ($billing -ne "True") {
    Write-Host "Billing still disabled. Cannot deploy Cloud Run." -ForegroundColor Red
    exit 1
}

Write-Host "Complete Application Default Credentials (required for Firebase CLI):" -ForegroundColor Cyan
Write-Host "  gcloud auth application-default login"
& $Gcloud auth application-default login
& $Gcloud auth application-default set-quota-project $PROJECT_ID

Write-Host "Add Firebase to GCP project (if not done in console) ..." -ForegroundColor Cyan
firebase projects:addfirebase $PROJECT_ID

& "$PSScriptRoot\deploy-all.ps1"
