# Lotus Runner

Compact Windows runner for a MetaTrader 5 bridge and portable strategy bundles. It is designed for the 1 GB FXVPS server: no Docker, database server, dashboard, or historical backtest dataset.

## Safety model

- The HTTP service binds only to `127.0.0.1`.
- Execution is disabled by default and the included MT5 bridge is shadow/telemetry-only.
- A bundle is checked with SHA-256 before loading.
- V7 and V8 are intentionally disabled: their validated source is not present in this workspace. They return `hold` until imported, reviewed, tested, and explicitly enabled.
- Credentials never belong in the repository, artifact, strategy bundle, or MT5 inputs committed to Git.

## Local check

```powershell
py -m pip install -e . pytest
py -m pytest -q
py -m lotus_runner.main --check
```

## MT5 bridge

Compile `mt5/LotusRunnerBridge.mq5` in MetaEditor and attach it to the configured XAUUSD M5 chart. In MT5, add `http://127.0.0.1:1111` under **Tools → Options → Expert Advisors → Allow WebRequest for listed URL**.

The bridge only transmits an account heartbeat and a market snapshot. It deliberately refuses order execution in this release.

## GitHub Actions artifact

Every push to `main` produces `lotus-runner-windows-x64.zip`. It contains the runner, strategy bundles, bridge source, and installation helper. The `.mq5` file is source code and must be compiled in the installed MT5 MetaEditor, yielding the local `.ex5` file.

## Adding a strategy

1. Add a JSON bundle to `strategies/`.
2. Calculate the SHA-256 of the canonical JSON without the `sha256` field.
3. Add an audited implementation to the runner.
4. Add tests for inputs, risk controls, and fail-closed behavior.
5. Leave execution disabled through demo validation.

See `docs/strategy-validation.md` for the current source audit and non-negotiable promotion gate.
