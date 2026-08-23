# Skill — histórico

A skill v1 (julgamento **autônomo** do corpus) está em
[`.cursor/skills/inspect-transcript-integrity/SKILL.md`](../../.cursor/skills/inspect-transcript-integrity/SKILL.md).

## Correções do humano (2026-08-23) — absorvidas

- 14 linhas confirmadas, zero `corrigido` → critério aceito; agent passa a
  aplicar sozinho nas demais.
- `lsn_8875732`: `incerto` / `truncada`. Miolo útil. Truncada ≠ inútil.
- `concordo` na tabela = `confirmado`.
- Welcome “Introdução” longo (aula 01 de 7k+) não é `inteira_curta`.
- `zoológico` sozinho não marca ASR (pode ser literal).

## Não fazer

- Não pedir confirmação aula a aula depois da calibração.
- Não usar mediana global.
- Não escrever no DuckDB.
- Não tratar `truncada` como exclusão do RAG.
