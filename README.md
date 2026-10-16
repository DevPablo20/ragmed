# ragmed

RAG sobre as transcrições das aulas do Avantgarde College. Você faz uma pergunta
clínica e recebe uma resposta fundamentada **citando a aula de origem com URL
verificável**.

Os metadados vivem num banco DuckDB; cada transcrição é um `.txt` nomeado pelo
identificador da aula.

O **como** está aqui. O **porquê** de cada escolha está em
[METODOLOGIA.md](METODOLOGIA.md), junto com o dicionário de dados completo.

```
ragmed.duckdb              fonte de verdade
transcripts/               246 .txt — transcripts/lsn_3521413.txt
indexes/                   índices BM25, um por estratégia (derivado, fora do git)
data/
├── snapshots/             uma raspagem do site por arquivo, nunca sobrescrito
├── curation.json          decisões humanas de curadoria — versionado
├── local_lessons.json     identidade das 20 aulas que nunca estiveram na vitrine
├── matched_map.json       procedência histórica (só arquivo, nada depende dele)
├── manifest.csv/.parquet  export de v_corpus, regenerado a cada sync
└── reports/               relatórios gerados (perfil do corpus)
scripts/
├── db.py                  esquema (DDL + views) e conexão
├── scrape_snippet.js      extrator para colar no console do DevTools
├── load_snapshot.py       snapshot do site → banco
├── load_local.py          aulas de origem local → banco
├── sync_transcripts.py    transcripts/ → banco, e export do manifest
├── profile_corpus.py      mede o corpus → lesson_quality + relatório
├── load_curation.py       aplica data/curation.json no banco
├── build_chunks.py        transcrições → tabela chunks (3 estratégias)
├── build_index.py         chunks → BM25 + embeddings
├── search.py              busca híbrida: BM25 + denso, RRF, rerank
├── ask.py                 busca + geração com citação da fonte
├── llm.py                 cliente Anthropic compartilhado
└── queries.sql            consultas prontas
```

Tudo roda com o Python do ambiente `medrag`:

```bash
alias pyr=~/.pyenv/versions/medrag/bin/python
```

---

## Perguntar ao corpus

```bash
pyr scripts/search.py "qual a dose de reposição de testosterona em implante?"
```

Não precisa de credencial nem de rede: recupera os trechos e mostra cada um com
início, fim e a URL da aula.

```bash
pyr scripts/ask.py "qual a dose de reposição de testosterona em implante?"
```

Mesma busca, mais a resposta gerada com citação `[n]` e o bloco `FONTES`. **Este
precisa de credencial da Anthropic** — veja abaixo.

Opções úteis nos dois:

| flag | efeito |
|---|---|
| `-k N` | quantos trechos retornar (padrão 10) |
| `--strategy fixed\|semantic\|qa_turn` | qual corte de chunk usar |
| `--course`, `--subject`, `--instructor` | pré-filtro por metadado, aplicado antes da busca |
| `--explain` (só `search.py`) | mostra a posição em cada lista antes da fusão |
| `--no-rerank` (só `search.py`) | pula o cross-encoder |
| `--show-context` (só `ask.py`) | imprime o que foi recuperado antes da resposta |

### Credencial

`ask.py` (e, mais adiante, o enriquecimento e a geração do conjunto de avaliação)
chama a API da Anthropic. Duas formas de fornecer a chave:

```bash
export ANTHROPIC_API_KEY=sk-ant-...              # no shell
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env       # arquivo local, já no .gitignore
```

Para validar sem gastar tokens de saída:

```bash
pyr scripts/llm.py
```

Ele usa `count_tokens`, que é gratuito, e imprime `credencial OK` quando está
tudo certo. Um erro `credit balance is too low` significa que a chave é válida
mas a conta não tem saldo — resolve-se em *Plans & Billing* no console.

> **Aviso de uso.** Isto recupera e resume o que os professores disseram em aula.
> Não é recomendação clínica, e o texto vem de transcrição automática, que erra
> termo e corrompe número. A citação existe para você conferir na fonte.

---

## Construir o índice

```bash
pyr scripts/build_chunks.py --all              # as três estratégias de corte
pyr scripts/build_index.py --strategy fixed    # BM25 + embeddings dessa estratégia
```

`build_chunks.py` corta as 206 aulas do corpus em chunks e grava na tabela
`chunks`. As três estratégias convivem, separadas pela coluna `strategy`:

| estratégia | como corta | chunks |
|---|---|---|
| `fixed` | ~360 palavras, 15% de overlap, encostando em pontuação final | 6.556 |
| `semantic` | corta onde a similaridade entre grupos de frases vizinhos despenca | 6.921 |
| `qa_turn` | usa as interrogações como fronteira de turno | 7.974 |

`build_index.py` roda **por estratégia** e produz duas coisas: o índice BM25 em
`indexes/bm25_<estratégia>/` e os vetores densos em `chunk_embeddings`. Na GPU
leva poucos minutos; sem CUDA, dezenas de minutos (ele avisa).

Hoje só `fixed` tem índice construído.

---

## O ciclo normal

### 1. Raspar o site

Logado em `ead.avantgardecollege.com.br/area/vitrine/home`, abra o DevTools
(F12) → Console, cole o conteúdo de [scripts/scrape_snippet.js](scripts/scrape_snippet.js)
e dê Enter. Leva ~40 s para os 35 cursos e baixa `snapshot_<timestamp>.json`.

Se o download for bloqueado, o snippet deixa o resultado na página de propósito:

```js
copy(JSON.stringify(window.__snapshot))
```

Mova o arquivo para `data/snapshots/` e carregue:

```bash
pyr scripts/load_snapshot.py data/snapshots/snapshot_20261101T093000.json
```

O loader imprime o diff: cursos e aulas novos, o que saiu do ar, títulos alterados.

### 2. Ver o que falta

```sql
SELECT * FROM v_pending_downloads;
```

A coluna `destino` já diz com que nome gravar o arquivo.

### 3. Transcrever e registrar

Salve o texto em `transcripts/<lesson_uid>.txt` e:

```bash
pyr scripts/sync_transcripts.py
```

Não há nada a casar — **o nome do arquivo é o identificador**. O sync recalcula
md5 e contagens, faz upsert do que mudou, remove do banco o que sumiu do disco,
e reclama de arquivo cujo nome não seja um `lesson_uid` conhecido.

Rode com `--check` para ver o que ele faria sem escrever.

### 4. Perfilar e curar

```bash
pyr scripts/profile_corpus.py     # mede tudo → lesson_quality + relatório
pyr scripts/load_curation.py      # aplica as decisões de data/curation.json
```

O perfil escreve `data/reports/corpus_profile.md` e grava as medidas em
`lesson_quality`. Depois, confira o que ele marcou:

```sql
SELECT * FROM v_quality_review;
```

Aula suspeita de truncamento ou classificada fora de `clinical` aparece aí. O
veredito é seu: registre em `data/curation.json` e rode `load_curation.py`.

### 5. Reindexar

```bash
pyr scripts/build_chunks.py --all
pyr scripts/build_index.py --strategy fixed
```

---

## Consultar o banco

Sem CLI do duckdb instalado, o caminho é o Python:

```bash
pyr -c "import duckdb; print(duckdb.connect('ragmed.duckdb').execute('SELECT * FROM v_pending_downloads').df())"
```

Ou, mais confortável, num notebook:

```python
import duckdb
con = duckdb.connect("ragmed.duckdb", read_only=True)
con.execute("SELECT * FROM v_rag_corpus").df()
```

Consultas prontas e comentadas em [scripts/queries.sql](scripts/queries.sql).

> **O DBeaver trava o banco.** DuckDB não aceita um segundo processo em escrita.
> Feche o DBeaver antes de rodar qualquer script que escreva. Para ler enquanto
> algo roda, copie o `.duckdb` para `/tmp` e abra a cópia.

### Views

| view | para quê |
|---|---|
| `v_pending_downloads` | aulas no ar sem transcrição, com o nome do arquivo a criar |
| `v_new_lessons` | o que apareceu na raspagem mais recente |
| `v_removed_from_site` | o que esteve no site e saiu, com a transcrição preservada |
| `v_local_only` | o que nunca esteve na vitrine |
| `v_corpus` | join achatado — é o que `data/manifest.csv` exporta |
| `v_quality_review` | as aulas que merecem olho humano antes de indexar |
| **`v_rag_corpus`** | **a definição única do que entra no índice** |
| **`v_rag_excluded`** | **o complemento: o que ficou de fora e por quê** |
| `v_chunk_corpus` | chunk + identidade da aula — o que `search.py` consulta |
| `v_run_history` | as raspagens e seus deltas |

`v_rag_corpus` e `v_rag_excluded` andam em par de propósito: **nada sai do índice
em silêncio.**

---

## Quais arquivos importam

A distinção que interessa: **o que é insubstituível, o que é regenerável, e o que
é só histórico.**

| arquivo | precisa? | atualiza quando? |
|---|---|---|
| `transcripts/*.txt` | **insubstituível** | você escreve |
| `data/snapshots/*.json` | **insubstituível** | uma por raspagem, nunca sobrescrita |
| `data/local_lessons.json` | **insubstituível** | congelado na migração |
| `data/curation.json` | **insubstituível** | você decide, à mão |
| `ragmed.duckdb` | reconstruível (veja abaixo) | os scripts |
| `indexes/` | reconstruível | `build_index.py` |
| `data/manifest.csv/.parquet` | descartável | todo `sync_transcripts.py` |
| `data/reports/` | descartável | todo `profile_corpus.py` |
| `data/matched_map.json` | dispensável | congelado na migração |

**`curation.json` é insubstituível** porque é julgamento humano, não medida.
Registra quais aulas são duplicatas de quais, quais são clínicas apesar de a
heurística achar o contrário, e as regras de inclusão no índice — cada uma com
justificativa e data. O banco é derivado; este arquivo, não.

**`local_lessons.json` é insubstituível** por um motivo específico: os arquivos
das aulas locais se chamam `lsn_loc_<hash>`, e esse hash foi derivado do caminho
original em `raw/`, pasta que não existe mais. É o único lugar fora do banco que
sabe qual arquivo é qual aula. Sem ele, uma reconstrução deixaria 20 arquivos
órfãos.

**`manifest.csv` e `manifest.parquet`** são um export da view `v_corpus`, nada
mais. Existem para você abrir no pandas ou no Excel sem passar por SQL, e voltam
no próximo sync se apagar. Não são fonte de nada.

**`matched_map.json` é só memória.** Registra de que arquivo de `raw/` veio cada
uma das 223 transcrições originais e com que confiança o matcher casou. Todo o
conteúdo já está no banco, em `source_path`, `match_confidence` e `match_signals`
— conferido, sem divergência. Nenhum script lê esse arquivo.

Os dois JSONs de migração **não acompanham o sync de propósito** — eles descrevem
como o corpus chegou aqui, não como ele está agora.

---

## Reconstruir o banco do zero

O banco é derivado. Se corromper, ou se quiser refazê-lo com um esquema novo:

```bash
rm ragmed.duckdb
pyr scripts/db.py
pyr scripts/load_snapshot.py data/snapshots/20260822T000000.json
pyr scripts/load_local.py
pyr scripts/sync_transcripts.py
pyr scripts/profile_corpus.py
pyr scripts/load_curation.py
```

Depois, para reconstruir o índice:

```bash
pyr scripts/build_chunks.py --all
pyr scripts/build_index.py --strategy fixed
```

**A ordem importa.** `load_curation.py` roda por último porque escreve em colunas
que os passos anteriores criam, e `profile_corpus.py` precisa das transcrições já
registradas.

Uma perda a saber: reconstruir com **um** snapshot recria o estado atual, mas o
histórico de execuções recomeça do zero. Para preservá-lo, carregue os snapshots
em ordem cronológica — é para isso que `data/snapshots/` nunca sobrescreve nada.

---

## Tabelas

| tabela | quem escreve | o que guarda |
|---|---|---|
| `scrape_runs` | `load_snapshot` | uma linha por raspagem: `scraped_at`, totais, deltas |
| `courses` | `load_snapshot`, `load_local` | catálogo, `first_seen`/`last_seen`/`is_active`, `origin` |
| `lessons` | `load_snapshot`, `load_local` | aulas, grupo, instrutor, slots de enriquecimento |
| `transcripts` | `sync_transcripts` | `path`, `md5`, contagens, procedência |
| `lesson_quality` | `profile_corpus` | medidas por transcrição + dois julgamentos heurísticos |
| `chunks` | `build_chunks` | os trechos, com offsets no arquivo de origem |
| `chunk_embeddings` | `build_index` | um vetor `FLOAT[1024]` por chunk |
| `course_snapshots`, `lesson_snapshots` | `load_snapshot` | append-only, o estado de cada raspagem |

Duas colunas fogem à regra acima, porque são julgamento humano:
`lessons.domain_reviewed` e `transcripts.duplicate_of`, ambas escritas só por
`load_curation.py`.

O dicionário de dados coluna a coluna está em
[METODOLOGIA.md](METODOLOGIA.md#4-dicionário-de-dados).

**A separação entre `lessons` e `transcripts` é deliberada.** Os loaders nunca
escrevem em `transcripts`, e o sync nunca escreve em `lessons` — re-raspar o site
não pode sobrescrever nem apagar o que é seu.

**Nada é deletado.** Aula que sai do ar vira `is_active = false` e continua
consultável, com `last_seen_at` marcando quando foi vista pela última vez e a
transcrição ainda ligada a ela. Duplicata vira `duplicate_of` apontando para a
canônica: fica no banco, só não entra no índice.

**`origin`** separa as duas procedências: `site` (226 aulas da vitrine) e `local`
(20 que nunca estiveram lá).

### Identificadores

`crs_<id do site>` e `lsn_<id do site>` — imutáveis, porque vêm da chave de banco
da plataforma. Material local usa `crs_loc_<hash>` / `lsn_loc_<hash>`.

Id de chunk: `lsn_3521413::fixed::0007`. A estratégia entra no id porque as três
convivem na mesma tabela.

### Enriquecimento pendente

`lessons` tem `subject`, `topics`, `summary`, `enrichment_source` e `enriched_at`
vazios, reservados para uma passada de LLM sobre as transcrições. O site não
expõe assunto — só o título. Isso habilita o pré-filtro por `--subject` e deixa o
prefixo contextual dos chunks bem mais informativo.

---

## Estado atual

**Corpus.** 246 transcrições, 2.451.021 palavras — 226 casadas com aulas do site,
20 de origem local. Zero pendências de download.

**Índice do RAG.** 206 aulas, 33 cursos, 1.988.312 palavras. As 40 de fora:

| motivo | quantas |
|---|---|
| origem local — sem `lesson_url`, logo não citável | 20 |
| domínio `business` — marketing, vendas, gestão | 16 |
| cópia de outra aula | 4 |

**Pipeline.** Chunking, busca híbrida e geração prontos e **validados ponta a
ponta** (2026-08-24): a resposta cita aulas conferíveis, sinaliza os erros de
transcrição em vez de repeti-los, e recusa pergunta fora do corpus em vez de
inventar. Faltam o enriquecimento por LLM e a régua de avaliação — ver
[METODOLOGIA.md § 7](METODOLOGIA.md#7-como-avaliar-e-iterar) e `ESTADO_ATUAL.md`.

---

## Histórico

O corpus veio de pastas com nomes de arquivo inconsistentes (acentos, espaços,
`.docx.txt`, sufixos de vídeo), casadas com o site por um matcher difuso que
combinava número da aula, similaridade de título e posição. Esse matcher foi
aposentado na migração para identificadores: o resultado dele está no banco (e em
`data/matched_map.json`), e ele não é mais necessário porque o arquivo passou a se
chamar pelo `lesson_uid`.

Os erros do caminho — e o que cada um ensinou — estão em
[METODOLOGIA.md § 2](METODOLOGIA.md#2-a-linha-do-tempo).
