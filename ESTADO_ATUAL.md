# Estado atual — retomada em nova sessão

Última atualização: 2026-08-23. Leia junto com o plano completo em
`/home/pablo/.claude/plans/elabore-um-plano-de-staged-crane.md`.

## Onde paramos

```
✓ Etapa 0  GPU + modelos            torch cu124, bge-m3 e bge-reranker-v2-m3 na RTX 4070 Ti Super
✓ Etapa 1  Curadoria fechada        206 aulas indexáveis, zero pendências
✓ Etapa 2  Chunking                 3 estratégias: fixed 6.556 · semantic 6.921 · qa_turn 7.974
✓ Etapa 3  Índice + busca híbrida   BM25 + denso → RRF k=60 → rerank → top 10
◐ Etapa 4  Geração                  recuperação VERIFICADA; geração bloqueada por saldo
✗ Etapa 5  Enriquecimento por LLM   ~US$ 8,25, Batch API + claude-opus-5
✗ Etapa 6  Régua de avaliação       eval_questions / eval_runs / eval_results
✓ Docs     README + METODOLOGIA.md  dicionário de dados e passo a passo para estudo
```

## O que já passou da Etapa 4

A metade de **recuperação** passou no critério 4 do plano. Para *"qual a dose de
reposição de testosterona em implante hormonal?"*, o rank 1 é `Avançado de Saúde
do homem` → *Aula 16: Implantes Hormonais II*, com `lesson_url` real; os 5
primeiros vêm de 3 cursos distintos, todos sobre reposição/implante.

Falta a metade de **geração**: conferir que o modelo cita `[n]` corretamente e
recusa pergunta fora do corpus. Exige uma chamada real — daí o bloqueio de saldo.

## O único bloqueio

**A chave já está no `.env` e é válida — falta saldo na conta Anthropic.**
Testado em 2026-08-23: a autenticação passa e a API responde
`400 invalid_request_error: Your credit balance is too low`. Chave inválida daria
`401 authentication_error`, então o problema é billing, não configuração.

Adicione créditos em console.anthropic.com → Plans & Billing. US$ 10–15 cobrem
tudo: enriquecimento ~US$ 8,25 (Opus 5 em Batch), conjunto de avaliação centavos,
perguntas de teste ~US$ 0,10 cada.

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

1. **Validar a Etapa 4** (assim que houver saldo): rodar `ask.py` e conferir se a
   resposta cita `[n]` coerentes e recusa perguntas fora do corpus. Vale rodar
   uma pergunta claramente fora do domínio como controle negativo.
2. **Etapa 5** — `enrich_lessons.py`: Batch API + `claude-opus-5` +
   `output_config.format` com JSON Schema → preenche `subject`, `topics[]`,
   `summary` nas 206 aulas. Revisar 10 antes de soltar o lote. Depois
   reconstruir os chunks para o assunto entrar no prefixo contextual.
3. **Etapa 6** — `build_eval_set.py` (~100 perguntas com aula-fonte anotada,
   validadas por humano) e `eval_retrieval.py` (recall@k, MRR, nDCG@10).
   Comparar as três estratégias de chunking, com e sem prefixo contextual,
   denso × híbrido × híbrido+rerank.
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
