# Adds Google Cloud SDK to PATH for this PowerShell session.
$GcloudBin = "C:\Users\Anurag Bhattacharya\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
if (Test-Path $GcloudBin) {
    $env:Path = "$GcloudBin;$env:Path"
}
function Get-GcloudExe {
    $cmd = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $GcloudBin "gcloud.cmd"
    if (Test-Path $fallback) { return $fallback }
    throw "Google Cloud SDK not found. Install: winget install Google.CloudSDK"
}
