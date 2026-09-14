# Estratégias: auditoria de fonte e gate de promoção

Data da auditoria: 2026-09-14.

## Resultado

O projeto ativo em `2Lotus` contém a implementação local da ZigZag V7. Ela é
mantida neste runner como única estratégia. O bundle está habilitado apenas
para shadow e nunca pode emitir ordens até concluir o replay independente; o
bridge também recusa ordem de forma explícita.

## Evidências encontradas no 2Lotus

| Variante | Evidência | Resultado | Estado |
| --- | --- | --- | --- |
| ZigZag V7 | `zigzag_v7.py` e `core-zigzag-v7-365.json` | 460 trades, PF 2,22, expectativa 0,4255R, DD máx. 9,66R; replay derivado da V5 | `provisional_shadow` |
| ZigZag V8 | `zigzag_v8.py` | filtro calendarizado derivado da V7.2; fora de escopo | não incluída |

O V3 ainda requer validação forward com ticks da corretora. O V4 não deve ser
usado como base de promoção: o estudo walk-forward registra explicitamente
`rejected_no_training_configuration_passed`.

## Gate obrigatório para V7

Uma versão só pode passar de `import-required` para executável quando todos os
itens abaixo existirem no mesmo pull request:

1. Fonte completa e versionada, com regras de entrada, saída e dimensionamento.
2. Dataset de origem, período, corretora, spread, slippage e comissões declarados.
3. Backtest reproduzível, incluindo lista de trades, PnL, PF, drawdown e número de operações.
4. Separação temporal entre seleção de parâmetros e holdout; nenhum parâmetro pode ser escolhido no holdout.
5. Testes unitários para sinal, bloqueio por spread, janela de sessão, posição existente e limite de risco.
6. Teste de integração com o payload real do bridge MT5.
7. Execução em `shadow`/demo antes de qualquer promoção. A conta real permanece sem execução.

## Próxima etapa

Regenerar o replay da V7 em uma única cadeia, com sinais, saídas, custos e
dimensionamento calculados diretamente da fonte. Depois, validar forward em
demo com ticks Fusion antes de permitir qualquer execução.
