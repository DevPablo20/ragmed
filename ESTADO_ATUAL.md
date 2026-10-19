# Estado atual — retomada em nova sessão

Última atualização: 2026-10-19. **O RAG está em produção.** O plano original
(`~/.claude/plans/elabore-um-plano-de-staged-crane.md`) não existe mais; o que
ele continha está neste arquivo, no `README.md` e no `METODOLOGIA.md`.

## Onde paramos

```
✓ Etapa 0  GPU + modelos            torch cu124, bge-m3 e bge-reranker-v2-m3 na RTX 4070 Ti Super
✓ Etapa 1  Curadoria fechada        206 aulas indexáveis, zero pendências
✓ Etapa 2  Chunking                 3 estratégias: fixed 6.556 · semantic 6.921 · qa_turn 7.974
✓ Etapa 3  Índice + busca híbrida   BM25 + denso → RRF k=60 → rerank → top 10
✓ Etapa 4  Geração                  MVP validado ponta a ponta em 2026-08-24
✓ Etapa 6  Régua de avaliação       25 perguntas, 5 configurações; vence fixed+prefixo+rerank
– Etapa 5  Enriquecimento por LLM   adiado: não é necessário para produção
✓ Produção Supabase + claude.ai     projeto Ragmed-sp (sa-east-1), conector MCP, 2026-10-19
```

## Produção (2026-10-19)

O médico pergunta num chat do **claude.ai**; um conector personalizado (MCP)
chama a Edge Function `ragmed-mcp`, que busca no Postgres do Supabase e devolve
15 trechos com curso, aula e link, junto com as regras de resposta. O Claude da
assinatura dele escreve a resposta. Sem servidor, sem API paga.

- **Projeto:** `Ragmed-sp`, ref `ttnafqswdmgxqfuhrhqy`, região `sa-east-1`, plano Pro.
- **Busca:** BM25 em SQL sobre índice invertido (`rag_postings`), sem embeddings.
  Medido com as 25 perguntas: aula certa em 96% no top-5 e **100% no top-10**;
  ~80 ms no banco, 0,35–0,66 s pelo conector.
- **Segurança:** tabelas com RLS e sem policy; o endereço do conector carrega um
  token secreto (`MCP_TOKEN`), sem ele a função responde 404.
- **Atualização (3x/ano):** ciclo normal → `build_chunks.py --all` →
  `publish_supabase.py`. Passo a passo no `README.md`, seção Produção.

Testado em 2026-10-19 pelo claude.ai: o conector sincroniza, as 3 ferramentas
respondem e a resposta sai no formato pedido (citação `[n]`, FONTES por aula com
link, erro de transcrição sinalizado).

## Etapa 6 (2026-10-16)

Régua automática — a aula certa aparece no topo? — com 25 perguntas escritas a
partir das aulas (`data/eval/perguntas_treino.json`):

| configuração | acerto@1 | acerto@5 |
|---|---|---|
| **fixed + prefixo + rerank** | **92%** | 96% |
| fixed sem prefixo + rerank | 88% | 92% |
| qa_turn + prefixo + rerank | 84% | 96% |
| semantic + prefixo + rerank | 80% | 92% |
| fixed + prefixo, sem rerank | 80% | 100% |
| só BM25 (base da produção) | 80% | 100% |

A suspeita de que o prefixo atrapalha (seção abaixo) **não generalizou**. O
teste de relevância para o médico (`data/eval/avaliacao_trechos.xlsx`, 40 trechos,
~1 h) foi enviado e não voltou preenchido; a decisão ficou com a régua
automática. Se as notas vierem: `eval_retrieval.py --grades <planilha>`.

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

Deve imprimir `credencial OK`. Desde a produção, a chave só serve ao `ask.py`
local — o claude.ai usa a assinatura de quem pergunta.

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

# avaliação
$PY scripts/eval_retrieval.py              # régua automática
$PY scripts/build_judging_set.py           # remonta o teste do médico

# produção
$PY scripts/publish_supabase.py            # DuckDB → Supabase
npx supabase functions deploy ragmed-mcp --no-verify-jwt --use-api
```

## Próximos passos

1. **Observar o uso real.** O ponto fraco conhecido: sem o score do reranker, a
   recusa de pergunta fora do corpus depende só do Claude (o BM25 sempre devolve
   algum trecho). Se ele começar a forçar resposta com trechos fracos, endurecer
   as regras em `supabase/functions/ragmed-mcp/index.ts` — vale na hora para
   todos, sem reconfigurar o conector.
2. **Perguntas reais do médico** viram a próxima rodada da régua: elas não têm o
   viés de vocabulário das 25 atuais, que favorece a busca lexical.
3. **Etapa 5, se fizer falta** — resumos e assunto por aula (filtro por assunto,
   uma ferramenta "quais aulas falam de X"). Reestimar custo com um modelo atual;
   não exige recalcular vetores, só regerar chunks e republicar.
4. **Se a busca lexical mostrar limite** com perguntas parafraseadas: embeddings
   por API numa Edge Function, medidos contra a mesma régua antes de trocar.

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
- **Região do Supabase só na criação.** A tela pode oferecer só "Americas" e
  escolher sozinha; use `npx supabase projects create ... --region sa-east-1`.
- **Supabase "Direct connection" é IPv6.** Use a string do Session pooler.
- **`.env` sem quebra de linha final** + `echo >>` = variável grudada na linha
  anterior. Edite o `.env` num editor.
- **`git filter-branch` apaga o arquivo da pasta** quando ele deixa de ser
  rastreado no commit reescrito — foi assim que o `ragmed.duckdb` sumiu e teve
  de ser restaurado do backup. Copie antes.
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
