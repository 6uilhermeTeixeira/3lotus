# Comandos rápidos da VPS

Execute estes comandos no PowerShell da VPS. O runner deve estar extraído em
`C:\LotusRunner` e o MT5 deve estar aberto na mesma máquina.

## Verificar instalação e configuração

```powershell
cd C:\LotusRunner
Get-Location
Test-Path .\lotus-runner.exe
Test-Path .\.env
.\lotus-runner.exe --check
```

## Iniciar o Lotus Runner

Mantenha esta janela aberta:

```powershell
cd C:\LotusRunner
.\lotus-runner.exe
```

Mensagem esperada:

```text
Lotus Runner listening on http://127.0.0.1:1111
```

## Testar a API local

Abra uma segunda janela do PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:1111/health
Invoke-RestMethod http://127.0.0.1:1111/ready
Invoke-RestMethod http://127.0.0.1:1111/api/strategies
Invoke-RestMethod http://127.0.0.1:1111/api/account
Invoke-RestMethod http://127.0.0.1:1111/api/market/status
Invoke-RestMethod http://127.0.0.1:1111/api/decisions/latest
Invoke-RestMethod http://127.0.0.1:1111/api/metrics
```

No endpoint `/api/account`, `connected : True` confirma que o EA já enviou o
último snapshot da conta.

`/api/market/status` confirma a idade do último tick e o total recebido.
`/api/decisions/latest` mostra o último motivo de sinal ou bloqueio e sua
latência. `/api/metrics` resume ticks, duplicatas, decisões e execuções.

## Verificar o processo e a porta

```powershell
Get-Process lotus-runner -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 1111 -State Listen
```

## Interpretar erros do EA

- `5203` sem status HTTP: o runner estava fechado, a URL está incorreta ou o
  WebRequest não foi autorizado no MT5.
- `status=422`: o runner foi alcançado, mas o payload foi rejeitado. Compile a
  versão mais recente de `LotusRunnerBridge.mq5` e anexe novamente o EA.
- Nenhuma mensagem depois de `Initialized in Shadow Mode`: normalmente indica
  que as chamadas retornaram `HTTP 200`; o EA só imprime falhas.

## Parar o runner

Na janela que está executando o processo, pressione:

```text
Ctrl+C
```

O procedimento desta página é shadow. Para execução, use exclusivamente a
configuração demo documentada em `docs/demo-execution.md`.
