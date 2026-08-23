# EDA — análise exploratória do corpus ragmed

Caderno da preparação para o RAG. O DuckDB continua a fonte do catálogo
(`courses`, `lessons`, `transcripts`); aqui vivem **metodologia e decisões**
para calibrar de novo no futuro, treinar o agente, e só então (passo seguinte)
automatizar.

Nada nesta pasta altera o banco.

## Tópicos

| pasta | pergunta | status |
|---|---|---|
| [01-integridade-compreensao/](01-integridade-compreensao/) | O texto está inteiro e compreensível? | fechado — skill v1 + 247 em decisoes.csv |
| 02-… | Tipo de aula (clínica vs. welcome vs. negócio) | ainda não |
| 03-… | Duplicatas entre edições | ainda não |
| 04-… | Tesauro (subject / topics) | ainda não |

Cada tópico segue o mesmo molde: `metodologia.md`, `decisoes.md`, `sinais.md`,
`exemplos.md`. A skill do tópico 1 está em
[`.cursor/skills/inspect-transcript-integrity/SKILL.md`](../.cursor/skills/inspect-transcript-integrity/SKILL.md)
e aponta de volta para estes arquivos.

## Como usar

1. Tópico 1: o veredito de cada aula está em
   [01-integridade-compreensao/decisoes.csv](01-integridade-compreensao/decisoes.csv).
   Recalibrar só se um caso novo quebrar um sinal.
2. Próximos tópicos: metodologia → decisões → sinais, no mesmo molde.
