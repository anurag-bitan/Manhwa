# Deploy Cloud Run Job + API after images are built and env files exist.
# Prerequisites: bootstrap-manhwa-ai.ps1, Secret Manager supabase-service-role, api.env.yaml, worker.env.yaml

$ErrorActionPreference = "Stop"

$GcloudBin = "C:\Users\Anurag Bhattacharya\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
if (Test-Path $GcloudBin) { $env:Path = "$GcloudBin;$env:Path" }

$PROJECT_ID = "manhwa-ai-509114"
$REGION = "europe-west1"
$REPOSITORY = "manhwa"
$JOB = "manhwa-pipeline"
$API_SERVICE = "manhwa-api"
$API_SA = "manhwa-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
$WORKER_SA = "manhwa-worker-sa@$PROJECT_ID.iam.gserviceaccount.com"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiEnv = Join-Path $scriptDir "api.env.yaml"
$workerEnv = Join-Path $scriptDir "worker.env.yaml"

if (-not (Test-Path $apiEnv)) {
    Write-Host "Missing $apiEnv — copy from api.env.yaml.example and fill Supabase URL + CORS." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $workerEnv)) {
    Write-Host "Missing $workerEnv — copy from worker.env.yaml.example and fill Supabase URL." -ForegroundColor Red
    exit 1
}

$WORKER_IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/manhwa-worker:latest"
$API_IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/manhwa-api:latest"

gcloud config set project $PROJECT_ID | Out-Null

Write-Host "Deploying Cloud Run Job $JOB ..."
gcloud run jobs describe $JOB --region $REGION --project $PROJECT_ID 2>$null
if ($LASTEXITCODE -eq 0) {
    gcloud run jobs update $JOB `
        --image $WORKER_IMAGE `
        --region $REGION `
        --service-account $WORKER_SA `
        --tasks 1 `
        --parallelism 1 `
        --max-retries 0 `
        --task-timeout 7200s `
        --cpu 2 `
        --memory 4Gi `
        --env-vars-file $workerEnv `
        --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-service-role:latest" `
        --project $PROJECT_ID
} else {
    gcloud run jobs create $JOB `
        --image $WORKER_IMAGE `
        --region $REGION `
        --service-account $WORKER_SA `
        --tasks 1 `
        --parallelism 1 `
        --max-retries 0 `
        --task-timeout 7200s `
        --cpu 2 `
        --memory 4Gi `
        --env-vars-file $workerEnv `
        --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-service-role:latest" `
        --project $PROJECT_ID
}

gcloud run jobs add-iam-policy-binding $JOB `
    --region $REGION `
    --member "serviceAccount:$API_SA" `
    --role "roles/run.jobsExecutorWithOverrides" `
    --project $PROJECT_ID 2>$null | Out-Null

Write-Host "Deploying Cloud Run service $API_SERVICE ..."
gcloud run deploy $API_SERVICE `
    --image $API_IMAGE `
    --region $REGION `
    --service-account $API_SA `
    --allow-unauthenticated `
    --port 8080 `
    --min 0 `
    --max 1 `
    --concurrency 20 `
    --timeout 60s `
    --cpu 1 `
    --memory 512Mi `
    --env-vars-file $apiEnv `
    --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-service-role:latest" `
    --project $PROJECT_ID

Write-Host ""
Write-Host "API URL (set VITE_API_BASE_URL to this):" -ForegroundColor Green
gcloud run services describe $API_SERVICE --region $REGION --project $PROJECT_ID --format="value(status.url)"
