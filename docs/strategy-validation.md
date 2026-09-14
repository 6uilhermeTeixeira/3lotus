# Estratégias: auditoria de fonte e gate de promoção

Data da auditoria: 2026-09-14.

## Resultado

Não existe implementação, bundle, backtest, branch ou tag chamada `ZigZag V7`,
`ZigZag V8`, `zigzag-v7` ou `zigzag-v8` nos repositórios privados disponíveis
da conta. Logo, os bundles V7 e V8 deste repositório ficam desabilitados e não
podem emitir ordens.

## Evidências encontradas no 2Lotus

| Variante | Evidência | Resultado | Estado |
| --- | --- | --- | --- |
| ZigZag V3 | `core-zigzag-v3-365.json` | 736 trades, PF 1,67, expectativa 0,3481R, DD máx. 12,9R | `promising_not_live` |
| ZigZag V4 | `zigzag_scalper_v4_microstructure.walkforward.json` | PF 0,409, PnL -US$ 1.366,57 em 76 trades | rejeitada |
| V7/V8 | pesquisa de código, branches e tags | nenhuma fonte encontrada | bloqueada |

O V3 ainda requer validação forward com ticks da corretora. O V4 não deve ser
usado como base de promoção: o estudo walk-forward registra explicitamente
`rejected_no_training_configuration_passed`.

## Gate obrigatório para V7 e V8

Uma versão só pode passar de `import-required` para executável quando todos os
itens abaixo existirem no mesmo pull request:

1. Fonte completa e versionada, com regras de entrada, saída e dimensionamento.
2. Dataset de origem, período, corretora, spread, slippage e comissões declarados.
3. Backtest reproduzível, incluindo lista de trades, PnL, PF, drawdown e número de operações.
4. Separação temporal entre seleção de parâmetros e holdout; nenhum parâmetro pode ser escolhido no holdout.
5. Testes unitários para sinal, bloqueio por spread, janela de sessão, posição existente e limite de risco.
6. Teste de integração com o payload real do bridge MT5.
7. Execução em `shadow`/demo antes de qualquer promoção. A conta real permanece sem execução.

## Próxima entrada necessária

Para implementar V7/V8, forneça o repositório, branch, arquivo exportado ou a
especificação formal de cada estratégia. Sem isso, qualquer regra seria uma
nova estratégia, e não uma validação das versões pedidas.
