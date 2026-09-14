# Lotus Runner

Compact Windows runner for the ZigZag V7 strategy and a MetaTrader 5 bridge. It is designed for the 1 GB FXVPS server: no Docker, database server, dashboard, or historical backtest dataset.

## Safety model

- The HTTP service binds only to `127.0.0.1`.
- Execution is disabled by default and the included MT5 bridge is shadow/telemetry-only.
- A bundle is checked with SHA-256 before loading.
- ZigZag V7 is intentionally disabled: its unified independent replay is still pending. It returns `hold` until reviewed, tested, and explicitly enabled.
- Credentials never belong in the repository, artifact, strategy bundle, or MT5 inputs committed to Git.

## Local check

```powershell
py -m pip install -e . pytest
py -m pytest -q
py -m lotus_runner.main --check
```

## MT5 bridge

Compile `mt5/LotusRunnerBridge.mq5` in MetaEditor and attach it to the configured XAUUSD M5 chart. In MT5, add `http://127.0.0.1:1111` under **Tools → Options → Expert Advisors → Allow WebRequest for listed URL**.

The bridge transmits an account heartbeat plus 3,000 completed M5 candles, which are required for the V7 H1 context. It deliberately refuses order execution in this release.

V7's structural-expansion branch remains fail-closed until its 900-second tick-context collector is ported and independently replayed. The V1/V4/V7 directional path is available only in shadow.

For the VPS procedure, see `docs/vps-shadow-install.md`.

For copy-and-paste PowerShell commands and error meanings, see
`docs/vps-command-reference.md`.

## GitHub Actions artifact

Every push to `main` produces `lotus-runner-windows-x64.zip`. It contains the runner, strategy bundles, bridge source, and installation helper. The `.mq5` file is source code and must be compiled in the installed MT5 MetaEditor, yielding the local `.ex5` file. Use the latest artifact; earlier artifacts before commit `runner_entry.py` do not start correctly.

## Adding a strategy

1. Add a JSON bundle to `strategies/`.
2. Calculate the SHA-256 of the canonical JSON without the `sha256` field.
3. Add an audited implementation to the runner.
4. Add tests for inputs, risk controls, and fail-closed behavior.
5. Leave execution disabled through demo validation.

See `docs/strategy-validation.md` for the current source audit and non-negotiable promotion gate.
