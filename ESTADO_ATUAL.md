# Estado atual — retomada em nova sessão

Última atualização: 2026-08-23. Leia junto com o plano completo em
`/home/pablo/.claude/plans/elabore-um-plano-de-staged-crane.md`.

## Onde paramos

```
✓ Etapa 0  GPU + modelos            torch cu124, bge-m3 e bge-reranker-v2-m3 na RTX 4070 Ti Super
✓ Etapa 1  Curadoria fechada        206 aulas indexáveis, zero pendências
✓ Etapa 2  Chunking                 3 estratégias: fixed 6.556 · semantic 6.921 · qa_turn 7.974
✓ Etapa 3  Índice + busca híbrida   BM25 + denso → RRF k=60 → rerank → top 10
✓ Etapa 4  Geração                  MVP validado ponta a ponta em 2026-08-24
✗ Etapa 5  Enriquecimento por LLM   ~US$ 8,25, Batch API + claude-opus-5
✗ Etapa 6  Régua de avaliação       eval_questions / eval_runs / eval_results
✓ Docs     README + METODOLOGIA.md  dicionário de dados e passo a passo para estudo
```

## Etapa 4 validada (2026-08-24)

**Recuperação** — critério 4 do plano. Para *"qual a dose de reposição de
testosterona em implante hormonal?"*, o rank 1 é *Aula 16: Implantes Hormonais
II* (`Avançado de Saúde do homem`), com `lesson_url` real.

**Geração** — critério 5, com saldo na conta. Numa pergunta sobre causas e
tratamento de disfunção erétil, o modelo: sinalizou os erros de ASR em vez de
repeti-los como certos ("diasídicos", "canais de solo e potássio", números que
oscilam na fala); **declarou explicitamente o que os trechos não cobriam**
(PDE5, ondas de choque, doses); e descartou sozinho os trechos de infertilidade
por serem outro problema clínico. É o comportamento que o prompt pede.

**Um bug encontrado e corrigido nessa validação.** O bloco `FONTES` deduplicava
por `lesson_uid` guardando só o primeiro rank de cada aula. O modelo citou [5],
[7] e [10] — três chunks da *mesma* aula — e o bloco mostrava só o [5]. Quem
procurasse [7] não achava número nenhum. Citação irresolvível não é citação
verificável, que é a razão de ser do projeto. `imprimir_fontes()` em `ask.py`
agora agrupa por aula e lista todos os `[n]`: `[5] [7] [10] Aula 03: ...`.

## O score do reranker é um detector de fora-do-corpus calibrado

Controle negativo rodado em 2026-08-24: *"como configurar um roteador Cisco?"*.
O modelo recusou corretamente e ainda fez algo melhor do que recusar — encontrou
a única coincidência lexical do corpus (um "router de glicemia", que é um monitor
contínuo de 14 dias) e **explicou por que não serve**, em vez de ignorá-la em
silêncio ou usá-la como ponte.

Isso levantou a pergunta: dá para saber que a pergunta está fora do corpus *antes*
de chamar o modelo? Medido em 22 perguntas — 12 respondíveis pelo corpus, 10
claramente fora — usando o maior score de rerank do top-10:

| classe | n | menor | maior |
|---|---|---|---|
| **dentro** do corpus | 12 | 0,5763 | 0,9937 |
| **fora** do corpus | 10 | 0,00005 | 0,0077 |

**Separação de 75×, sem nenhuma sobreposição.** As duas distribuições não chegam
perto uma da outra; qualquer limiar entre ~0,01 e ~0,5 classifica os 22 casos
corretamente. O ponto médio em escala log fica em ~0,066.

Notas para quem for usar isso:

- Só vale **com rerank ligado**. Os scores de RRF ficam todos em ~0,016–0,03 e
  não separam nada — são posições, não relevância.
- A hipótese concorrente, "quando a pergunta está fora do corpus a recuperação se
  espalha entre muitas aulas", foi medida junto e **não se sustenta**: a pergunta
  da testosterona (dentro) espalhou por 8 aulas e 6 cursos, igual à do Cisco
  (fora, 8 aulas e 7 cursos). Dispersão não separa; score separa.

Não foi implementado nenhum portão em `ask.py` — ver a discussão em "próximos
passos". O que este número serve **hoje** é como coluna a gravar na Etapa 6:
confiança por pergunta, ao lado de recall e MRR.

## Achado que muda uma premissa da Etapa 6

**O prefixo contextual pode estar prejudicando a recuperação, não ajudando.**
Medido na mesma pergunta sobre disfunção erétil, cosseno de cada chunk contra a
pergunta, com e sem prefixo:

| rank | aula | cos(q,texto) | cos(q,prefixo+texto) | delta |
|---|---|---|---|---|
| 7 | **Disfunção Erétil** | 0,5753 | 0,5682 | **−0,0072** |
| 5 | **Disfunção Erétil** | 0,5611 | 0,5730 | +0,0119 |
| 10 | **Disfunção Erétil** | 0,5426 | 0,5307 | **−0,0119** |
| 1 | Fisiologia Causas Tratamento | 0,4798 | 0,5283 | **+0,0485** |
| 6 | Espermatogênese | 0,4909 | 0,5344 | **+0,0435** |
| 2 | Fisiologia Causas Tratamento | 0,5260 | 0,5537 | +0,0277 |

A única aula certa é a única que o prefixo prejudica; todo chunk fora do alvo
ganha. O mecanismo está visível no prefixo: a pergunta traz "causas" e
"tratamentos", e o curso errado se chama *"Avançado de Infertilidade e
**Tratamento** Pré Gestação"*, aula *"Fisiologia **Causas Tratamento**"*. O
prefixo virou ímã de palavra-chave para todos os ~500 chunks daquele curso,
independentemente do conteúdo.

**Ordenando só pelo texto, os três chunks da aula certa seriam 1º, 2º e 3º.**
Com prefixo caíram para 5º, 7º e 10º.

Limites do que foi medido, para não virar conclusão: é **uma** pergunta, e só a
metade densa — não o pipeline completo com BM25, RRF e reranker. No BM25 o efeito
tende a ser pior, porque "tratamento" e "causas" são tokens exatos no prefixo.
Isso não condena o prefixo; **eleva a comparação "com × sem prefixo" de
formalidade a pergunta em aberto** na Etapa 6.

Reprodução: `scripts/search.py` para o ranking, e comparar
`encode(text)` × `encode(context_prefix + text)` contra a pergunta.

## Sobre a credencial

Resolvido em 2026-08-24: havia saldo faltando, não problema de configuração.
Um `400 invalid_request_error: credit balance is too low` é billing; chave
inválida daria `401 authentication_error`.

Confirme com:

```bash
~/.pyenv/versions/medrag/bin/python scripts/llm.py   # count_tokens e gratuito
```

Deve imprimir `credencial OK`. Isso destrava as Etapas 4, 5 e 6 de uma vez.

## Comandos do pipeline

```bash
PY=~/.pyenv/versions/medrag/bin/python

# reconstrução completa do banco, do zero
$PY scripts/db.py
$PY scripts/load_snapshot.py data/snapshots/20260822T000000.json
$PY scripts/load_local.py
$PY scripts/sync_transcripts.py
$PY scripts/profile_corpus.py
$PY scripts/load_curation.py

# RAG
$PY scripts/build_chunks.py --all
$PY scripts/build_index.py --strategy fixed
$PY scripts/search.py "sua pergunta" -k 5 --explain
$PY scripts/ask.py "sua pergunta"          # precisa do .env
```

## Próximos passos, em ordem

1. ~~**Validar a Etapa 4**~~ — **fechada**, incluindo o controle negativo. Os dois
   critérios do plano passaram: citação verificável (depois da correção do
   `FONTES`) e recusa em vez de invenção.

   **Decisão em aberto, de produto e não de código:** vale pôr um portão em
   `ask.py` que recusa sem chamar o modelo quando o maior score de rerank fica
   abaixo de ~0,05? A medição acima diz que classificaria certo nas 22 perguntas
   testadas. Mas o argumento contra é forte: no teste do Cisco, **a recusa do
   modelo foi melhor do que qualquer mensagem enlatada seria** — ele achou o
   "router de glicemia" e explicou por que não servia. Um portão teria matado
   isso. E a economia é irrelevante: ~US$ 0,10 por pergunta fora do corpus, num
   uso de estudo.

   Recomendação: **não pôr o portão.** Em vez disso, exibir o score como sinal de
   confiança e gravá-lo na Etapa 6. Se um dia o `ask.py` for exposto a um volume
   maior de perguntas, a decisão se reabre com dados melhores.

2. **Etapa 6 antes da Etapa 5** — inversão recomendada, e o motivo é o achado do
   prefixo acima. O plano põe o enriquecimento primeiro porque ele deixa o
   prefixo contextual "bem mais informativo", com `Assunto:` preenchido. Mas se o
   prefixo estiver **prejudicando** a recuperação, enriquecê-lo aumenta o
   problema em vez de resolvê-lo — e são US$ 8,25 gastos para piorar. Construir a
   régua primeiro custa centavos e responde a pergunta antes de o dinheiro ser
   gasto.

   `build_eval_set.py` (~100 perguntas com aula-fonte anotada, validadas por
   humano) e `eval_retrieval.py` (recall@k, MRR, nDCG@10). Comparar as três
   estratégias de chunking, **com × sem prefixo contextual** (agora a comparação
   mais urgente das três), e denso × híbrido × híbrido+rerank.

3. **Etapa 5** — `enrich_lessons.py`: Batch API + `claude-opus-5` +
   `output_config.format` com JSON Schema → preenche `subject`, `topics[]`,
   `summary` nas 206 aulas. Revisar 10 antes de soltar o lote. Depois
   reconstruir os chunks.

   Vale notar que `subject` tem **dois** usos independentes: o prefixo contextual
   (sob suspeita) e o pré-filtro `--subject` do `search.py` (que não depende do
   prefixo e continua valendo). Mesmo que a régua condene o prefixo, o
   enriquecimento ainda se paga pelo segundo uso.
4. ~~**Docs**~~ — feito em 2026-08-23: `README.md` reescrito como manual de
   operação do pipeline completo, e `METODOLOGIA.md` com o porquê de cada
   escolha, a linha do tempo com os erros do caminho e o dicionário de dados
   coluna a coluna.

   Não conferido ainda: a Etapa 6 do `METODOLOGIA.md` descreve as tabelas
   `eval_*` como planejadas — elas ainda não existem em `db.py`. Quando forem
   criadas, o dicionário precisa ganhar a seção correspondente.

## Armadilhas já encontradas (não repetir)

- **DBeaver trava o banco.** O DuckDB não aceita segundo processo em escrita.
  Feche o DBeaver antes de qualquer script que escreva; para leitura, copiar o
  `.duckdb` para `/tmp` e abrir a cópia funciona.
- **`chunk_uid` inclui a estratégia** (`lsn_X::fixed::0007`). Sem isso as três
  estratégias colidem na chave primária.
- **Não julgue um chunk pelo começo.** Chunks têm ~366 palavras; um recorte de
  200 caracteres esconde a informação e já me fez condenar erroneamente a
  qualidade da busca e acusar o reranker sem motivo. O `search.py` mostra
  início e fim justamente por isso.
- **`bm25s` guarda id inteiro próprio.** O mapeamento índice→`chunk_uid` é
  nosso, em `indexes/bm25_<estratégia>/chunk_uids.json`.
- **Opus 5**: thinking ligado por padrão divide o teto de `max_tokens` com a
  resposta; e recusa vem como HTTP 200 com `stop_reason='refusal'`, não exceção.
  `llm.py` já trata os dois.
- **Vários chunks caem na mesma aula.** No teste de disfunção erétil, 10 chunks
  vieram de 5 aulas — uma delas com 3. Qualquer agregação por `lesson_uid` na
  saída precisa preservar todos os `[n]`, senão a citação deixa de resolver. Foi
  exatamente o bug do `FONTES`.
- **O `-k` importa mais do que parece.** Nesse mesmo teste, toda a substância da
  resposta veio dos ranks 5, 7 e 10. Com `-k 5` a resposta teria degradado muito.
  Não baixe o `-k` sem medir.

## Diagnóstico de qualidade da busca (medido, não achado)

Para *"qual a dose de reposição de testosterona em implante hormonal?"*, com
96 chunks no corpus contendo dose em mg + testosterona/implante:

| etapa | alvos no top-200 | primeiras posições |
|---|---|---|
| denso | 45 | 1, 2, 3, 5, 6, 9 |
| BM25 | 38 | 4, 7, 11, 14 |
| após fusão RRF | 56 | 1, 3, 5, 9, 12 |

16 alvos chegam ao rerank; 6 ficam no top-10 (contra 4 sem rerank). A
recuperação funciona — a régua da Etapa 6 é que vai dizer o quanto.
