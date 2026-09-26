# Print minified Firebase service account JSON for Render env var FIREBASE_SERVICE_ACCOUNT_JSON
param(
    [Parameter(Mandatory = $true)]
    [string]$JsonPath
)

$ErrorActionPreference = "Stop"
$resolved = Resolve-Path $JsonPath
$obj = Get-Content -Raw -Path $resolved | ConvertFrom-Json
$minified = $obj | ConvertTo-Json -Compress -Depth 100
Write-Host "Copy everything below into Render -> manhwa-api -> Environment -> FIREBASE_SERVICE_ACCOUNT_JSON"
Write-Host ""
Write-Host $minified
