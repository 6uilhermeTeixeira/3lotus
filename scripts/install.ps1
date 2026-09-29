$ErrorActionPreference = "Stop"
$installRoot = "C:\2Lotus"
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
if ($sourceRoot -ne $installRoot) {
    Copy-Item -Path (Join-Path $sourceRoot "*") -Destination $installRoot -Recurse -Force
}

if (-not (Test-Path "$installRoot\.env")) {
@'
LOTUS_RUNNER_HOME=C:\2Lotus
LOTUS_RUNNER_HOST=127.0.0.1
LOTUS_RUNNER_PORT=7772
LOTUS_RUNNER_ACTIVE_STRATEGY=zigzag-scalper-v2
LOTUS_RUNNER_EXECUTION_ENABLED=false
LOTUS_RUNNER_ALLOWED_ACCOUNT_LOGIN=0
LOTUS_RUNNER_MAX_LIVE_LOT=0.01
LOTUS_RUNNER_TICK_WINDOW_SECONDS=900
LOTUS_RUNNER_DECISION_DEBOUNCE_MS=50
LOTUS_RUNNER_MAX_SPREAD_POINTS=50
LOTUS_RUNNER_STRUCTURAL_CONTEXT_PIPS=1000
LOTUS_RUNNER_STRUCTURAL_EMA20_GAP_PIPS=900
LOTUS_RUNNER_STRUCTURAL_MAX_PIVOT_EXTENSION_PIPS=50
LOTUS_RUNNER_REQUIRE_ORDER_BOOK=true
LOTUS_RUNNER_AUDIT_RETENTION_DAYS=30
LOTUS_RUNNER_LOG_MAX_BYTES=5000000
LOTUS_RUNNER_LOG_BACKUP_COUNT=7
LOTUS_RUNNER_ID=2lotus-vps
LOTUS_TELEMETRY_URL=
LOTUS_TELEMETRY_TOKEN=
LOTUS_TELEMETRY_INTERVAL_SECONDS=10
'@ | Set-Content -Path "$installRoot\.env" -Encoding ascii
}

Write-Host "Installed at $installRoot. Existing local .env was preserved."
Write-Host "Execution remains disabled by design."
