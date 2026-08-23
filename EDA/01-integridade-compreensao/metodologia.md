# Metodologia — integridade e compreensão

**Status:** tópico fechado (skill v1 + varredura das 247 em 2026-08-23).

Pergunta: a transcrição está **inteira** e **compreensível o bastante** para
um RAG? Julgar **por aula**, não por chunk.

Fora deste tópico: tipo de aula, duplicata entre edições, `include_in_rag`,
tesauro, chunking.

O humano validou o critério numa amostra (14 `confirmado`, 1 `incerto`,
zero correções). O agente aplica o mesmo critério no corpus, **sem pedir
confirmação aula a aula**. Procedimento:
[`.cursor/skills/inspect-transcript-integrity/SKILL.md`](../../.cursor/skills/inspect-transcript-integrity/SKILL.md).

Varredura:

```bash
python .cursor/skills/inspect-transcript-integrity/scripts/inspect_corpus.py
```

Saída: [decisoes.csv](decisoes.csv). Âncoras humanas no script não são
sobrescritas. DuckDB não é escrito.

## Ordem de decisão

1. Notas/doses → `resumo_notas`
2. Começo no meio da fala → `truncada`
3. Fim em slide sem fato e sem desfecho → `truncada`
4. Welcome/intro **curta** (&lt; ~1200 pal.) com abertura → `inteira_curta`
5. ASR degradado (`usonioterapia`, `zoonoterapia`, `osioniz`, `E aí` repetido)
   com forma ok → `asr_ruidosa_util`
6. Abertura e/ou desfecho, ou aula longa para o curso → `inteira_clinica`
7. Sem desfecho e bem abaixo da mediana do **curso** → `truncada`

Mediana sempre por curso. `truncada` descreve forma, não “miolo inútil”.
