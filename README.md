# 2lotus Runner

Compact Windows runner for versioned 4lotus strategy bundles and a MetaTrader 5 bridge. It is designed for the 1 GB FXVPS server: no Docker or external database server. SQLite stores the rolling tick context, durable telemetry outbox and local decision/execution audit.

The runner listens on `127.0.0.1:7772`. It sends best-effort event batches to 3lotus when `LOTUS_TELEMETRY_URL` and `LOTUS_TELEMETRY_TOKEN` are configured; loss of that connection never moves strategy evaluation off the VPS.

## Safety model

- The HTTP service binds only to `127.0.0.1`.
- Execution is disabled by default. Demo execution requires matching runner/EA guards; real accounts are rejected by both layers.
- A bundle is checked with SHA-256 before loading.
- ZigZag V7 remains provisional: its V1 path and canonical V2 structural gates can produce demo candidates, but real-account promotion remains prohibited until independent replay and forward validation are complete.
- Credentials never belong in the repository, artifact, strategy bundle, or MT5 inputs committed to Git.

## Local check

```powershell
py -m pip install -e . pytest
py -m pytest -q
py -m lotus_runner.main --check
```

## MT5 bridge

Compile `mt5/LotusRunnerBridge.mq5` in MetaEditor and attach it to the configured XAUUSD M5 chart. In MT5, add `http://127.0.0.1:7772` under **Tools → Options → Expert Advisors → Allow WebRequest for listed URL**.

The bridge collects every `OnTick`, batches ticks every 50 ms, refreshes 3,000 completed M5 candles every 30 seconds, and forwards order-book snapshots when the broker provides them. The runner keeps a 900-second rolling tick window. Shadow mode remains the default and execution requires the separate demo guard configuration.

An explicitly guarded demo-execution build is documented in
`docs/demo-execution.md`; it remains disabled unless both the runner and EA are
configured with the allowlisted demo login and risk limits.

V7's structural-expansion branch remains fail-closed until the 900-second tick window is ready and order book is available. The canonical thresholds are ported from 2Lotus, while real-account execution remains disabled.

## Runtime telemetry

```powershell
Invoke-RestMethod http://127.0.0.1:7772/api/market/status
Invoke-RestMethod http://127.0.0.1:7772/api/decisions/latest
Invoke-RestMethod http://127.0.0.1:7772/api/metrics
```

Runtime data is written under `C:\2Lotus\data` and rotating logs under `C:\2Lotus\logs` by default.

For the VPS procedure, see `docs/vps-shadow-install.md`.

For copy-and-paste PowerShell commands and error meanings, see
`docs/vps-command-reference.md`.

## GitHub Actions artifact

Every push to `main` produces `2lotus-runner-windows-x64.zip`. It contains the runner, strategy bundles, bridge source, and installation helper. The `.mq5` file is source code and must be compiled in the installed MT5 MetaEditor, yielding the local `.ex5` file. Use the latest artifact; earlier artifacts before commit `runner_entry.py` do not start correctly.

## Adding a strategy

1. Add a JSON bundle to `strategies/`.
2. Calculate the SHA-256 of the canonical JSON without the `sha256` field.
3. Add an audited implementation to the runner.
4. Add tests for inputs, risk controls, and fail-closed behavior.
5. Leave execution disabled through demo validation.

See `docs/strategy-validation.md` for the current source audit and non-negotiable promotion gate.
