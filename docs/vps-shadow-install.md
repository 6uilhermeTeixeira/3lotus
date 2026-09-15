# Instalação na FXVPS — ZigZag V7 em shadow

Este procedimento instala somente o monitoramento em shadow. A execução exige
a configuração demo separada e continua bloqueada para contas reais.

## 1. Baixar e extrair o artefato

1. No GitHub, abra **Actions → Build Windows runner** e baixe o artefato
   `lotus-runner-windows-x64` mais recente.
2. Extraia o ZIP, por exemplo em `C:\Users\Administrator\Downloads`.
3. Abra o PowerShell como administrador, entre em `scripts` dentro da pasta
   extraída e execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

O pacote será instalado em `C:\LotusRunner`.

## 2. Configurar o runner

Abra `C:\LotusRunner\.env` no Bloco de Notas. Para o primeiro teste, mantenha:

```text
LOTUS_RUNNER_HOME=C:\LotusRunner
LOTUS_RUNNER_HOST=127.0.0.1
LOTUS_RUNNER_PORT=1111
LOTUS_RUNNER_ACTIVE_STRATEGY=zigzag-v7
LOTUS_RUNNER_EXECUTION_ENABLED=false
LOTUS_RUNNER_ALLOWED_ACCOUNT_LOGIN=0
LOTUS_RUNNER_MAX_LIVE_LOT=0.01
```

Não preencha senha de conta MT5 neste arquivo. Ela pertence somente ao terminal
MT5. O campo `LOTUS_RUNNER_API_KEY` pode ficar vazio neste primeiro teste,
porque o runner e o MT5 usam a mesma máquina e a porta aceita apenas conexões
locais.

## 3. Validar e iniciar o executável

No PowerShell como administrador:

```powershell
cd C:\LotusRunner
.\lotus-runner.exe --check
.\lotus-runner.exe
```

O primeiro comando deve exibir `zigzag-v7` e `execution_enabled: false`.
Deixe essa janela aberta durante o teste. Em outra janela do PowerShell, valide:

```powershell
Invoke-RestMethod http://127.0.0.1:1111/health
Invoke-RestMethod http://127.0.0.1:1111/ready
```

## 4. Compilar e configurar o bridge MT5

1. Abra o MT5 e pressione `F4` para abrir o MetaEditor.
2. Em **MQL5 → Experts**, copie `C:\LotusRunner\mt5\LotusRunnerBridge.mq5`.
3. Abra o arquivo no MetaEditor e pressione `F7` para compilar. O resultado
   deve ser `LotusRunnerBridge.ex5` sem erros.
4. No MT5, abra o gráfico **XAUUSD / M5** e arraste o EA para o gráfico.
5. Nas entradas do EA, mantenha:

```text
RunnerUrl=http://127.0.0.1:1111/decision
StrategyId=zigzag-v7
StrategySymbol=XAUUSD
StrategyTimeframe=M5
HistoryBars=3000
SendIntervalMilliseconds=50
HistoryRefreshSeconds=30
EnableOrderExecution=false
```

6. Em **Ferramentas → Opções → Expert Advisors**, adicione
   `http://127.0.0.1:1111` à lista **Allow WebRequest for listed URL**.
7. Confirme que o botão **Algo Trading** pode ficar ativado para permitir o
   WebRequest do EA; o bridge continua sem permissão de ordem.

## 5. Confirmar comunicação e aquecimento

Depois de anexar o EA, abra a aba **Experts** do MT5. Não deve haver erro de
WebRequest. No PowerShell, execute:

```powershell
Invoke-RestMethod http://127.0.0.1:1111/api/account
```

O campo `connected` deve ser `true` e a conta deve aparecer sem senha.

V7 exige aproximadamente 2.460 candles M5 completos para formar 205 candles
H1. Até o terminal baixar esse histórico, o runner responderá
`v7_h1_history_warmup`; isso é esperado e não deve ser contornado reduzindo o
histórico.

## 6. O que observar

- `v7_shadow_signal`: sinal de shadow registrado; nenhuma ordem é enviada.
- `v7_directional_block`: o filtro H1/EMA50/Estocástico bloqueou o candidato.
- `v7_structural_filter_block`: o regime de expansão ainda não completou os
  900 segundos de ticks, não recebeu book ou algum gate estrutural foi vetado.

## 7. Encerrar o teste

Remova o EA do gráfico ou feche o MT5. Para parar o runner, pressione `Ctrl+C`
na janela do PowerShell que o executa.

Não altere `LOTUS_RUNNER_EXECUTION_ENABLED` para `true`. Essa promoção depende
do replay independente e da validação forward em demo.
