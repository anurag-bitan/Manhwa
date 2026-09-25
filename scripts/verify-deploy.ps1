# Smoke-test a deployed API base URL (Hugging Face Space).
param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl
)

$ErrorActionPreference = "Stop"
$base = $ApiBaseUrl.TrimEnd("/")
$healthUrl = "$base/health"

Write-Host "GET $healthUrl"
$response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 120
Write-Host "Response: $($response | ConvertTo-Json -Compress)"

if (-not $response) {
    throw "Empty response from /health"
}

$status = $response.status
if ($status -and $status -ne "ok") {
    throw "Unexpected health status: $status"
}

Write-Host "OK: API is reachable."
