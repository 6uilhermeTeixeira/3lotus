$ErrorActionPreference = "Stop"
$installRoot = "C:\LotusRunner"
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
if ($sourceRoot -ne $installRoot) {
    Copy-Item -Path (Join-Path $sourceRoot "*") -Destination $installRoot -Recurse -Force
}

@'
LOTUS_RUNNER_HOME=C:\LotusRunner
LOTUS_RUNNER_HOST=127.0.0.1
LOTUS_RUNNER_PORT=1111
LOTUS_RUNNER_ACTIVE_STRATEGY=zigzag-v7
LOTUS_RUNNER_EXECUTION_ENABLED=false
LOTUS_RUNNER_ALLOWED_ACCOUNT_LOGIN=0
LOTUS_RUNNER_MAX_LIVE_LOT=0.01
'@ | Set-Content -Path "$installRoot\.env" -Encoding ascii

Write-Host "Installed at $installRoot. Configure the local .env then run lotus-runner.exe."
Write-Host "Execution remains disabled by design."
