# Execução controlada na conta demo

Esta build mantém a execução desligada por padrão. Só habilite depois de
confirmar que a conta exibida pelo MT5 é a demo autorizada.

## Configurar o runner

No `C:\LotusRunner\.env`, use uma chave local forte e o login demo correto:

```text
LOTUS_RUNNER_API_KEY=troque-por-uma-chave-local
LOTUS_RUNNER_EXECUTION_ENABLED=true
LOTUS_RUNNER_ALLOWED_ACCOUNT_LOGIN=4006488
LOTUS_RUNNER_MAX_LIVE_LOT=0.01
```

O runner continua ligado somente em `127.0.0.1`. O valor da chave deve ser o
mesmo informado no campo `RunnerApiKey` do EA.

## Configurar o EA

Compile a versão mais recente de `mt5\LotusRunnerBridge.mq5` e use:

```text
RunnerUrl=http://127.0.0.1:1111/decision
RunnerApiKey=troque-por-uma-chave-local
StrategyId=zigzag-v7
StrategySymbol=XAUUSD
StrategyTimeframe=M5
HistoryBars=3000
PollIntervalSeconds=30
EnableOrderExecution=true
AllowedAccountLogin=4006488
MaxOrderLot=0.01
MaxOpenPositions=1
MaxDailyLossCurrency=5.0
```

O EA recusa inicializar se a conta não for demo, se o login não coincidir, se
o lote exceder 0,01, ou se os limites de risco forem alterados. Ele também
recusa novas ordens quando já existe uma posição própria no XAUUSD ou quando a
perda diária atingir 5 unidades da moeda da conta.

## Ativação

1. Pare o runner antigo.
2. Extraia o artefato mais recente em `C:\LotusRunner`.
3. Edite `.env` e configure a chave/login acima.
4. Inicie `.\lotus-runner.exe --check`; confirme `execution_enabled: true`.
5. Inicie `.\lotus-runner.exe`.
6. Compile o EA, anexe-o ao XAUUSD/M5 e confirme a mensagem `DEMO EXECUTION`.

Se qualquer etapa apresentar dúvida, mantenha `EnableOrderExecution=false` e
pare o runner. Esta build não deve ser usada em conta real.

