---
name: inspect-transcript-integrity
description: >-
  Julga se transcrições ragmed (transcripts/*.txt) estão inteiras e
  compreensíveis o bastante para RAG: truncada vs curta de propósito, ASR
  ruidoso, notas vs fala. Usar ao varrer o corpus, inspecionar uma aula nova,
  ou fechar EDA/01-integridade-compreensao. Não pede confirmação aula a aula.
---

# Integridade das transcrições (ragmed) — v1

A forma de julgar foi **validada pelo humano** em 14 aulas (zero correções) e
1 `incerto` (miolo útil ≠ forma completa). A partir daí o agente **aplica
sozinho** no corpus. Não pedir concorda/discorda por aula.

Caderno:

- [metodologia.md](../../../EDA/01-integridade-compreensao/metodologia.md)
- [decisoes.md](../../../EDA/01-integridade-compreensao/decisoes.md) — calibração
- [decisoes.csv](../../../EDA/01-integridade-compreensao/decisoes.csv) — as 247
- [sinais.md](../../../EDA/01-integridade-compreensao/sinais.md)
- [exemplos.md](../../../EDA/01-integridade-compreensao/exemplos.md)

## Quando varrer o corpus

Rodar o script (não reler 247 arquivos no chat):

```bash
python .cursor/skills/inspect-transcript-integrity/scripts/inspect_corpus.py
```

Ele lê o DuckDB **só para metadados**, classifica cada `transcripts/<uid>.txt`,
preserva as âncoras humanas, e reescreve `decisoes.csv`. Não escreve no banco.

Se o usuário pedir o tópico 1 numa aula nova: classificar, **acrescentar uma
linha no CSV**, sem esperar confirmação. Só interromper o humano se um caso
**quebrar um sinal já validado** (ex.: welcome curto que está cortado de verdade).

## Regras

- Julgar a **aula inteira**, não o chunk.
- **Não** escrever no DuckDB, em `lessons`, nem `include_in_rag`.
- Mediana **do curso**, nunca a global.
- `truncada` = falta abertura e/ou desfecho. O miolo pode ser útil
  (`lsn_8875732`). Não significa “jogar fora”.
- Welcome / Introdução / Onboarding só é `inteira_curta` se for **curta**
  (≲ 1200 palavras) **e** tiver abertura. Aula 01 “Introdução” de 7k é
  `inteira_clinica`.
- “A gente fala do resto depois” em aula de série não é corte.
- Âncoras humanas no script (`GOLD`) não se sobrescrevem.

## Ordem de decisão

1. Notas/doses (listas, `→`, `mg`, título “resumo”), quase sem fala → `resumo_notas`.
2. Começo no meio da fala (recorte) → `truncada`.
3. Fim em ponteiro de slide sem fato (`tá aqui ó`) e sem desfecho → `truncada`.
4. Título de welcome/intro **e** &lt; ~1200 palavras **e** abertura → `inteira_curta`.
5. Termo ASR degradado (`usonioterapia`, `zoonoterapia`, `osioniz`, `E aí E aí E aí`)
   com forma utilizável → `asr_ruidosa_util`. Não usar `zoológico` sozinho
   (pode ser literal).
6. Abertura e/ou desfecho reconhecíveis, ou aula longa para o curso → `inteira_clinica`.
7. Sem desfecho **e** bem abaixo da mediana do curso, título não-intro → `truncada`.

Desfechos: “um abraço”, “obrigado”, “ficou claro”, “próximo assunto”,
“referências”, “palmas”, “conte com a gente”, “próxima aula”, “valeu a pena”.

Arquivo de uma linha: janelas de ~900 caracteres (início / meio / fim);
texto todo se `word_count` &lt; ~1200.

## Âncoras humanas (não mudar o rótulo)

| rótulo | uid |
|---|---|
| `inteira_curta` | `lsn_3520778` |
| `truncada` caso-tipo | `lsn_4303292` |
| fronteira curta | `lsn_6729442` (inteira) vs `lsn_6729443` (recorte) |
| `% baixo ≠ corte` | `lsn_7784275` |
| `resumo_notas` | `lsn_loc_a77b2dff` |
| `asr_ruidosa_util` | `lsn_7773605` |
| miolo útil | `lsn_8875732` (`incerto`, veredito `truncada`) |
