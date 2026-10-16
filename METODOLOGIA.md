# Metodologia

Este documento existe para explicar **por que** cada peça do projeto é como é —
não só como usá-la. O `README.md` é o manual de operação; este aqui é o registro
do raciocínio, com os erros do caminho incluídos, porque foram eles que
definiram boa parte das decisões.

Última revisão: 2026-08-23.

---

## 1. Por que o projeto existe

O material bruto são transcrições automáticas de aulas gravadas de medicina
metabólica: 246 arquivos, 2,45 milhões de palavras, cada um uma **única linha
corrida** de até 30 mil palavras, sem parágrafo, sem marcação de quem fala, com
erros de reconhecimento de fala em termos técnicos.

Esse formato é hostil de duas maneiras opostas:

- **Grande demais para ler.** Encontrar "qual a dose de testosterona em implante"
  significa varrer 246 arquivos na mão.
- **Ruidoso demais para confiar.** O ASR erra nome de fármaco e corrompe número.
  Uma resposta que não deixe conferir a fonte é pior que nenhuma resposta.

O objetivo é um sistema que responda a uma pergunta clínica **citando a aula de
origem com URL verificável**. A citação não é enfeite: é o que torna o ruído do
ASR tolerável. O sistema recupera e resume o que o professor disse; quem decide
se está certo é você, na fonte.

Isso explica uma decisão que atravessa o projeto inteiro: **o `lesson_url` foi
guardado desde a primeira raspagem**, antes de existir qualquer RAG. E explica
por que as aulas de origem local ficam fora do índice — elas não têm URL, logo
não têm como ser citadas de forma conferível.

---

## 2. A linha do tempo

### 2.1 Coleta e casamento difuso

O ponto de partida foram pastas com nomes de arquivo inconsistentes: acentos,
espaços, `.docx.txt`, sufixos de vídeo. Nenhuma relação explícita com o catálogo
do site. Um matcher difuso casou arquivo com aula combinando três sinais: número
da aula, similaridade de título e posição na sequência do curso.

**O erro:** o matcher travou deslocado em um. Casou a aula 1 com o arquivo 2, a 2
com o 3, e assim por diante — e cada casamento individual parecia plausível,
porque títulos de aulas vizinhas do mesmo curso se parecem. O erro não aparece
olhando um par; aparece olhando a sequência.

**A lição:** quando um processo casa itens de duas listas ordenadas, o erro
provável não é aleatório, é sistemático. Verificar por amostra aleatória não
pega deslocamento; verificar a sequência inteira pega.

### 2.2 Banco relacional com histórico

O catálogo do site foi para um DuckDB, com uma decisão estrutural: **nada é
sobrescrito**. Cada raspagem vira uma linha em `scrape_runs` e um retrato
append-only em `course_snapshots` / `lesson_snapshots`. Aula que sai do ar vira
`is_active = false` e continua consultável.

Isso custa espaço e não custa mais nada, e paga quando o site muda um título ou
reordena um curso — dá para ver quando mudou, em vez de descobrir que mudou.

### 2.3 Reorganização por identificador

O matcher foi **aposentado**, não melhorado. Cada arquivo passou a se chamar pelo
`lesson_uid` (`transcripts/lsn_3521413.txt`), que vem da chave de banco da
plataforma. Deixou de haver algo a casar: o nome do arquivo *é* o identificador.

O resultado do matcher continua no banco (`transcripts.source_path`,
`match_confidence`, `match_signals`) e em `data/matched_map.json`, como
procedência histórica. Nenhum script lê esses campos.

**A lição:** a melhor correção para um processo heurístico frágil costuma ser
eliminar a necessidade dele, não afiná-lo.

### 2.4 Perfil de qualidade

`profile_corpus.py` mede cada transcrição e grava em `lesson_quality`. A
separação central: **medida é fato, julgamento é heurística**.

Contagem de palavras, frases, interrogações, muletas de fala e riqueza lexical
são números. `truncation_suspect` e `domain` são regras com limiar arbitrário,
gravadas para serem revisadas — e a view `v_quality_review` existe exatamente
para expor as duas dúzias de casos que merecem olho humano.

O que o perfil revelou e que redirecionou o RAG:

| medida | valor (mediana) | consequência |
|---|---|---|
| palavras por frase | 8 | é fala, não texto — frases curtas, raciocínio longo |
| interrogações por 1k palavras | 17,3 | há Q&A embutido, sem marcação de locutor |
| muletas de fala | 4,3% | «né», «então», «tipo», «gente» |
| riqueza lexical (TTR) | 0,180 | vocabulário repetitivo |
| quebras de linha | **zero** | não há fronteira natural nenhuma |

A última linha é a mais importante do projeto: **não existe parágrafo para
aproveitar**. Isso fez do chunking o gargalo real, e é a razão de haver três
estratégias em vez de uma.

### 2.5 Curadoria

Três tipos de decisão que uma máquina não deveria tomar sozinha: o que é
duplicata, o que é clínico, o que sai do corpus. Todas ficam em
`data/curation.json`, versionado, e são aplicadas por `load_curation.py`.

**A duplicata que quase passou.** A detecção inicial comparou os textos **por
amostragem** — pegou trechos e mediu sobreposição. Falhou: duas aulas do curso de
Vitaminas pareciam distintas porque as amostras caíram em regiões diferentes.

A comparação completa mostrou o contrário. `lsn_3545587` ("Aula 05") **não é
aula**: é a "Aula 06" truncada. 97,6% dela está dentro da 06 palavra por palavra,
com desvio de alinhamento de ±11 ao longo de 8.800 palavras; termina no meio do
assunto, enquanto a 06 segue por mais ~3.100 palavras exclusivas e tem
encerramento real.

A hipótese anterior — "é uma recapitulação" — estava errada, e era confortável
demais para ser questionada sem medir.

**A lição:** amostragem responde "são parecidas?", não "uma está contida na
outra?". Para conteúdo, alinhamento completo; e a hipótese que não incomoda é a
que menos se verifica.

**O fio solto que não deu em nada — e isso é resultado.** O padrão "arquivo
cortado no meio de uma frase" sugeria problema sistemático de captura. Duas
investigações, registradas em `curation.json` → `resolved_notes`:

1. Um detector de truncamento por "termina sem pontuação final" foi implementado
   e **descartado**: zero das 246 transcrições termina sem pontuação, inclusive a
   Aula 05. O sinal simplesmente não existe neste corpus.
2. Todos os pares das 6 aulas de Vitaminas foram comparados. Só o 05/06 se
   sobrepõe. Caso isolado, não sistemático.

Hipótese descartada com evidência vale tanto quanto hipótese confirmada — e fica
escrita para ninguém gastar o mesmo dia de novo.

### 2.6 RAG

Chunking, índice híbrido e geração. Detalhados na seção 6.

---

## 3. Os princípios que atravessam tudo

**Medida separada de julgamento.** Colunas de contagem em `lesson_quality` são
fato. `truncation_suspect` e `domain` são heurísticas com regra documentada no
código-fonte que as produz. Uma view (`v_quality_review`) expõe os julgamentos
para revisão em vez de aplicá-los em silêncio.

**Julgamento humano tem precedência sobre heurística, e vive à parte.**
`lessons.domain_reviewed` (humano) vence `lesson_quality.domain` (heurística) na
view `v_rag_corpus`. Estão em tabelas diferentes para que reprocessar o perfil
nunca apague o veredito.

**Nada é deletado, só desativado.** Aula fora do ar vira `is_active = false`.
Duplicata vira `duplicate_of` apontando para a canônica — a transcrição continua
lá, ligada à aula, e só não entra no índice. Uma única transcrição foi de fato
removida do disco em todo o projeto (`lsn_loc_eb26fca9`), e o motivo está escrito
em `curation.json` → `removed`.

**Quem escreve em qual tabela é regra, não convenção.**

```
courses, lessons, *_snapshots   ← só load_snapshot.py e load_local.py
transcripts                     ← só sync_transcripts.py
lesson_quality                  ← só profile_corpus.py
domain_reviewed, duplicate_of   ← só load_curation.py
chunks                          ← só build_chunks.py
chunk_embeddings                ← só build_index.py
```

Rodar a raspagem de novo não pode sobrescrever nem apagar o que é seu. As duas
metades — catálogo do site e material local — só se encontram nas views.

**Decisão humana em arquivo versionável.** `data/curation.json` existe para que
uma reconstrução do banco do zero não apague o julgamento. O banco é derivado; o
JSON, não.

**Um critério, um lugar.** `v_rag_corpus` é a definição única do que entra no
índice. Nenhum script reimplementa o critério. E `v_rag_excluded` é o complemento
obrigatório: tudo que ficou de fora aparece lá **com o motivo**. Nada some em
silêncio.

**Exclusão é reversível e explícita.** `curation.json` → `rag_policy` registra as
três regras de exclusão com data e justificativa. Trocar `exclude_local_origin`
para `false` devolve 20 aulas ao índice.

---

## 4. Dicionário de dados

Banco: `ragmed.duckdb`. DDL único em [`scripts/db.py`](scripts/db.py) — as
constantes `SCHEMA` e `VIEWS`, aplicadas por `init()`, que é idempotente.

### Identificadores

| forma | exemplo | origem |
|---|---|---|
| `crs_<id do site>` | `crs_3521` | chave de banco da plataforma, imutável |
| `lsn_<id do site>` | `lsn_3521413` | idem |
| `crs_loc_<hash>` / `lsn_loc_<hash>` | `lsn_loc_d63788ea` | md5 do caminho original do arquivo |
| `<lesson_uid>::<estratégia>::<índice>` | `lsn_3521413::fixed::0007` | id de chunk |

O hash do material local deriva do caminho em `raw/`, pasta que não existe mais.
É estável porque esse caminho virou string histórica em
`transcripts.source_path`, não porque a pasta continue existindo.

**A estratégia entra no `chunk_uid` de propósito.** As três estratégias convivem
na mesma tabela; sem esse componente elas colidiriam na chave primária.

---

### `scrape_runs` — o eixo temporal

Uma linha por execução da raspagem. Escrita por `load_snapshot.py`.

| coluna | tipo | o que é |
|---|---|---|
| `run_id` | BIGINT PK | sequência `seq_run_id` |
| `scraped_at` | TIMESTAMP | quando o snapshot saiu do site |
| `loaded_at` | TIMESTAMP | quando entrou no banco |
| `snapshot_path` | VARCHAR | o arquivo em `data/snapshots/` |
| `n_courses`, `n_lessons` | INTEGER | totais daquela raspagem |
| `n_courses_new`, `n_lessons_new` | INTEGER | apareceram nesta execução |
| `n_courses_gone`, `n_lessons_gone` | INTEGER | sumiram nesta execução |

### `courses` — catálogo de cursos

Escrita por `load_snapshot.py` (origem site) e `load_local.py` (origem local).

| coluna | tipo | o que é |
|---|---|---|
| `course_uid` | VARCHAR PK | `crs_<id>` ou `crs_loc_<hash>` |
| `origin` | VARCHAR | `site` \| `local` |
| `site_course_id` | VARCHAR | nulo quando `origin = 'local'` |
| `course_title` | VARCHAR | título na vitrine |
| `course_url` | VARCHAR | URL do curso |
| `course_kind` | VARCHAR | `produto` \| `aula` |
| `position_in_vitrine` | INTEGER | ordem na vitrine — usada para ordenar tudo |
| `group_count`, `lesson_count` | INTEGER | contagens do site |
| `first_seen_at` / `first_seen_run_id` | TIMESTAMP / BIGINT | primeira aparição |
| `last_seen_at` / `last_seen_run_id` | TIMESTAMP / BIGINT | última aparição |
| `is_active` | BOOLEAN | presente na raspagem mais recente |

### `lessons` — catálogo de aulas

Escrita pelos loaders. **Exceto** `domain_reviewed`, `subject`, `topics`,
`summary`, `enrichment_source`, `enriched_at`.

| coluna | tipo | o que é |
|---|---|---|
| `lesson_uid` | VARCHAR PK | `lsn_<id>` ou `lsn_loc_<hash>` |
| `course_uid` | VARCHAR | a que curso pertence |
| `origin` | VARCHAR | `site` \| `local` |
| `site_lesson_id` | VARCHAR | nulo quando local |
| `lesson_title` | VARCHAR | título na plataforma |
| `lesson_url` | VARCHAR | **a URL citável.** É por causa dela que o material local fica fora do índice |
| `site_group_id`, `group_title`, `group_index` | VARCHAR/INTEGER | módulo dentro do curso — desnormalizado, só 3 dos 35 cursos têm mais de um |
| `position_in_group`, `position_global` | INTEGER | ordem da aula |
| `instructor` | VARCHAR | heurística |
| `instructor_source` | VARCHAR | `site_title` \| `filename` — de onde a heurística tirou |
| `year` | INTEGER | heurística |
| `subject`, `topics[]`, `summary` | VARCHAR / VARCHAR[] / VARCHAR | **enriquecimento por LLM — hoje vazios (Etapa 5)** |
| `enrichment_source`, `enriched_at` | VARCHAR / TIMESTAMP | procedência do enriquecimento |
| `domain_reviewed` | VARCHAR | `clinical` \| `business`. **Veredito humano**, de `curation.json` |
| `first_seen_*`, `last_seen_*`, `is_active` | — | como em `courses` |

`instructor_source` é o padrão "medida com procedência" aplicado a um campo
heurístico: guardar de onde o valor veio permite desconfiar dele seletivamente.

### `transcripts` — 1:1 com `lessons`

Escrita **só** por `sync_transcripts.py`, exceto `duplicate_of`
(`load_curation.py`). Vive separada de `lessons` porque o ciclo de vida é outro:
o scrape do site nunca escreve aqui.

| coluna | tipo | o que é |
|---|---|---|
| `lesson_uid` | VARCHAR PK | a aula |
| `path` | VARCHAR | `transcripts/<lesson_uid>.txt` |
| `source_path` | VARCHAR | de onde o arquivo veio em `raw/` — procedência histórica |
| `md5` | VARCHAR | detecta mudança de conteúdo |
| `char_count`, `word_count`, `est_tokens`, `file_size_bytes` | BIGINT | medidas |
| `lang` | VARCHAR | idioma detectado |
| `match_confidence` | VARCHAR | `high` \| `medium` — legado do matcher aposentado |
| `match_signals` | VARCHAR | que sinais casaram — idem |
| `duplicate_of` | VARCHAR | aponta para a cópia canônica. **NULL = é a própria canônica** |
| `updated_at` | TIMESTAMP | último sync |

`duplicate_of` é a peça que permite excluir do índice sem perder nada: a aula
duplicada mantém a transcrição, não vira pendência de download, e simplesmente
não é indexada.

### `lesson_quality` — perfil, escrito por `profile_corpus.py`

| coluna | tipo | natureza | o que é |
|---|---|---|---|
| `lesson_uid` | VARCHAR PK | — | a aula |
| `word_count`, `sentence_count` | BIGINT | medida | contagens |
| `sentence_median_words` | DOUBLE | medida | fala fica ~7–8; texto escrito, 15–20 |
| `question_count`, `questions_per_1k` | BIGINT / DOUBLE | medida | proxy de Q&A embutido |
| `filler_pct` | DOUBLE | medida | muletas sobre o total de palavras |
| `type_token_ratio` | DOUBLE | medida | riqueza lexical; baixo = repetitivo |
| `course_median_words` | DOUBLE | medida | mediana do **próprio curso** |
| `length_ratio` | DOUBLE | medida | `word_count / course_median_words` |
| `clinical_score` | DOUBLE | medida | 0 = só negócios, 1 = só clínico |
| `truncation_suspect` | BOOLEAN | **julgamento** | `length_ratio < 0,30` |
| `domain` | VARCHAR | **julgamento** | `clinical` ≥ 0,70 · `business` ≤ 0,35 · senão `mixed` |
| `computed_at` | TIMESTAMP | — | quando o perfil rodou |

Duas escolhas com motivo:

- **A mediana é por curso, não do corpus.** Aula curta num curso curto não é
  anomalia. Comparar contra o corpus acusaria cursos inteiros.
- **`domain` classifica pelo texto, não pelo título.** "Gestão Integrada da
  Doença Cardiovascular" é aula clínica que casa com "gestão". Classificar por
  título erraria feio.

`truncation_suspect` é **suspeita, não veredito**: aberturas legítimas
("Bem-vindo(a)!", 157 palavras) caem no mesmo filtro. Dos 12 suspeitos atuais, a
maioria é abertura legítima.

### `chunks` — a unidade que o RAG recupera

Escrita por `build_chunks.py`.

| coluna | tipo | o que é |
|---|---|---|
| `chunk_uid` | VARCHAR PK | `<lesson_uid>::<estratégia>::<índice>` |
| `lesson_uid` | VARCHAR | de que aula veio |
| `chunk_index` | INTEGER | ordem dentro da aula |
| `text` | VARCHAR | o trecho |
| `context_prefix` | VARCHAR | `[Curso: … \| Aula: … \| Assunto: …]` — determinístico, sem LLM |
| `char_start`, `char_end` | BIGINT | offsets no arquivo de origem |
| `word_count`, `token_estimate` | INTEGER | medidas |
| `strategy` | VARCHAR | `fixed` \| `semantic` \| `qa_turn` |
| `created_at` | TIMESTAMP | quando foi cortado |

**`text` e `context_prefix` ficam separados de propósito.** O prefixo melhora a
recuperação, mas guardá-los concatenados impediria medir *quanto* ele melhora. A
view `v_chunk_corpus` oferece os dois e também `text_with_context` já colado.

**`char_start`/`char_end` são a garantia de rastreabilidade:** todo chunk recorta
exatamente aquele intervalo do arquivo original. Dá para conferir sem confiar.

### `chunk_embeddings` — vetores densos

Escrita por `build_index.py`.

| coluna | tipo | o que é |
|---|---|---|
| `chunk_uid` | VARCHAR PK | o chunk |
| `embedding` | FLOAT[1024] | `BAAI/bge-m3`, normalizado |
| `model` | VARCHAR | qual modelo produziu |
| `created_at` | TIMESTAMP | quando |

Guardados no próprio DuckDB, sem vector store separado — ver seção 6.3.

### `course_snapshots` / `lesson_snapshots` — append-only

O estado de cada curso/aula em cada execução: `(run_id, uid)` como chave, mais
título, posição e contagens daquele momento. É o que permite ver renomeação e
reordenação ao longo do tempo. Hoje há 1 execução registrada.

---

### Views

| view | para quê |
|---|---|
| `v_pending_downloads` | aulas no ar sem transcrição, com o nome do arquivo a criar |
| `v_new_lessons` | o que apareceu na raspagem mais recente |
| `v_removed_from_site` | o que saiu do ar, com a transcrição preservada |
| `v_local_only` | o que nunca esteve na vitrine |
| `v_corpus` | join achatado de tudo — é o que `data/manifest.csv` exporta |
| `v_quality_review` | as aulas que merecem olho humano antes de indexar |
| **`v_rag_corpus`** | **a definição única do que entra no índice** |
| **`v_rag_excluded`** | **o complemento, com o motivo de cada exclusão** |
| `v_chunk_corpus` | chunk + identidade da aula: a superfície que `search.py` consulta |
| `v_run_history` | as raspagens e seus deltas |

**`v_rag_corpus`** — uma aula entra se, e só se:

1. `origin = 'site'` — material local não tem URL, logo não é citável;
2. `duplicate_of IS NULL` — só a cópia canônica;
3. domínio clínico — `COALESCE(domain_reviewed, lesson_quality.domain) = 'clinical'`;
4. tem transcrição.

Estado atual: **206 aulas**, 33 cursos, 1.988.312 palavras.

**`v_rag_excluded`** — as 40 que ficaram de fora:

| motivo | quantas |
|---|---|
| origem local (fora por ora) | 20 |
| domínio `business` | 16 |
| cópia de outra aula | 4 |

(São 6 marcas de `duplicate_of` no banco; duas delas são de aulas locais, que já
aparecem na primeira linha. O motivo mostrado é o primeiro que se aplica.)

---

### Arquivos fora do banco

| arquivo | natureza | atualiza quando |
|---|---|---|
| `transcripts/*.txt` | **insubstituível** | você escreve |
| `data/snapshots/*.json` | **insubstituível** | uma por raspagem, nunca sobrescrita |
| `data/local_lessons.json` | **insubstituível** | congelado na migração |
| `data/curation.json` | **insubstituível** | você decide, à mão |
| `ragmed.duckdb` | derivado | os scripts |
| `indexes/bm25_<estratégia>/` | derivado | `build_index.py` |
| `data/manifest.csv` / `.parquet` | descartável | todo `sync_transcripts.py` |
| `data/reports/corpus_profile.md` | descartável | todo `profile_corpus.py` |
| `data/matched_map.json` | histórico | congelado; nenhum script o lê |

`local_lessons.json` é insubstituível por um motivo específico: os arquivos das
aulas locais se chamam `lsn_loc_<hash>`, e esse hash veio do caminho original em
`raw/`, pasta que não existe mais. Este JSON é o único lugar fora do banco que
sabe qual arquivo é qual aula.

`indexes/` está no `.gitignore` — é derivado e pesa alguns MB por estratégia.

---

## 5. O pipeline de comandos

```bash
PY=~/.pyenv/versions/medrag/bin/python
```

### Reconstrução completa, do zero

```bash
rm ragmed.duckdb
$PY scripts/db.py                                              # esquema
$PY scripts/load_snapshot.py data/snapshots/20260822T000000.json
$PY scripts/load_local.py                                      # aulas sem vitrine
$PY scripts/sync_transcripts.py                                # transcripts/ → banco
$PY scripts/profile_corpus.py                                  # lesson_quality
$PY scripts/load_curation.py                                   # decisões humanas
```

Cada passo e o que produz:

| comando | escreve | produz |
|---|---|---|
| `db.py` | esquema | tabelas e views, idempotente |
| `load_snapshot.py` | `courses`, `lessons`, `*_snapshots`, `scrape_runs` | catálogo + diff impresso |
| `load_local.py` | `courses`, `lessons` (origem local) | as 20 aulas sem vitrine |
| `sync_transcripts.py` | `transcripts` | md5, contagens, e `data/manifest.*` |
| `profile_corpus.py` | `lesson_quality` | medidas + `data/reports/corpus_profile.md` |
| `load_curation.py` | `domain_reviewed`, `duplicate_of` | aplica `data/curation.json` |

**A ordem importa.** `load_curation.py` roda por último porque escreve em colunas
de tabelas que os anteriores criam. `profile_corpus.py` precisa das transcrições
já registradas.

### RAG

```bash
$PY scripts/build_chunks.py --all              # as três estratégias
$PY scripts/build_index.py --strategy fixed    # BM25 + embeddings
$PY scripts/search.py "sua pergunta" -k 5 --explain
$PY scripts/ask.py "sua pergunta"              # precisa de credencial
```

`build_index.py` roda **por estratégia**: cada uma tem seu índice BM25 em
`indexes/bm25_<estratégia>/` e seus vetores em `chunk_embeddings`.

### Ciclo normal (quando aparece aula nova)

1. Raspar o site com `scripts/scrape_snippet.js` no console do DevTools;
2. Mover o JSON para `data/snapshots/` e rodar `load_snapshot.py`;
3. `SELECT * FROM v_pending_downloads` — a coluna `destino` já diz o nome do arquivo;
4. Transcrever, salvar em `transcripts/<lesson_uid>.txt`, rodar `sync_transcripts.py`;
5. `profile_corpus.py`, depois `load_curation.py`;
6. `build_chunks.py` e `build_index.py` para a aula entrar no índice.

### Armadilhas operacionais

- **O DBeaver trava o banco.** DuckDB não aceita um segundo processo em escrita.
  Feche o DBeaver antes de qualquer script que escreva. Para leitura enquanto algo
  roda, copie o `.duckdb` para `/tmp` e abra a cópia.
- **`--check` existe em `sync_transcripts.py` e `profile_corpus.py`** e mostra o
  que aconteceria sem escrever.

---

## 6. Como o RAG funciona

```
                                  ┌─ BM25 (termo exato) ─┐
transcrição → chunks → índice ─── ┤                      ├─ RRF k=60 ─ top 50
                                  └─ denso (paráfrase) ──┘                │
                                                                          ▼
                    resposta ← LLM ← top 10 ←──────────────────────── rerank
```

### 6.1 Chunking — o gargalo real

Nenhuma fronteira natural existe neste corpus: uma linha corrida, frases de 8
palavras, zero quebras. Cortar por tamanho fixo é o pior caso — todo chunk nasce
partindo um raciocínio.

Três estratégias coexistem na tabela `chunks`, separadas pela coluna `strategy`:

| estratégia | como corta | chunks | palavras (mediana) |
|---|---|---|---|
| `fixed` | ~360 palavras, 15% de overlap, encostando na última pontuação final da cauda da janela | 6.556 | 366 |
| `semantic` | agrupa 4 frases, embeda cada grupo, corta onde a similaridade entre vizinhos cai abaixo do percentil 25 **daquela aula** | 6.921 | 238 |
| `qa_turn` | fecha depois de uma interrogação, quando o chunk já tem tamanho útil | 7.974 | 217 |

Detalhes que não são óbvios:

- **O limiar do `semantic` é relativo, não absoluto.** Cada aula tem seu próprio
  ritmo de mudança de assunto; um corte fixo de similaridade fatiaria demais uma
  aula densa e de menos uma dispersa.
- **`qa_turn` fecha *depois* da pergunta**, não antes: a pergunta e a resposta
  precisam ficar no mesmo trecho para o chunk ser recuperável.
- **Trechos curtos são fundidos, não descartados** (`merge_tiny`). Descartar
  abriria buracos na cobertura do texto; como os spans são contíguos, fundir é só
  estender a fronteira. O piso é 50 palavras — abaixo disso é muleta de fala
  solta ("Perfeito.", "Exatamente.") e nunca será resposta útil.

**O prefixo contextual, versão barata.** *Contextual retrieval* na formulação
original custa uma chamada de LLM por chunk. Aqui não precisa: o prefixo sai
determinístico dos metadados que já estão no banco. Zero chamadas, e captura a
maior parte do ganho — situar o trecho na aula. É o que faz um trecho que diz
apenas "a dose costuma ser de 100 a 200" continuar recuperável por uma pergunta
sobre testosterona.

Fica em coluna separada justamente para dar para medir com e sem — e essa
separação já se pagou: a seção 7 traz a primeira medição, e ela **contraria** o
argumento deste parágrafo. Leia as duas.

### 6.2 Os dois índices erram de formas diferentes

| índice | acha | erra |
|---|---|---|
| **denso** (`bge-m3`, 1024 dims) | paráfrase — "como repor testosterona" alcança "reposição do hormônio masculino" | termo raro e número: o embedding dilui ambos |
| **BM25** (`bm25s`, stopwords pt) | termo exato e raro — nome de fármaco, dosagem, sigla | paráfrase: não sabe que dois termos significam o mesmo |

Um corpus de fala médica precisa dos dois: o clínico pergunta ora por conceito,
ora por nome de substância.

**Sobre `bm25s`:** ele atribui um id inteiro próprio a cada documento. O
mapeamento índice → `chunk_uid` é nosso, explícito, em
`indexes/bm25_<estratégia>/chunk_uids.json`. Depender do formato interno da
biblioteca já custou um bug aqui.

### 6.3 Por que não há vector store

Os vetores ficam em `chunk_embeddings`, no próprio DuckDB, e a busca é força
bruta com `array_cosine_similarity`. Com ~7 mil chunks isso responde em
milissegundos. Um índice HNSW só passaria a compensar uma ordem de grandeza
acima, e no DuckDB a persistência dele ainda é experimental. Menos peça móvel.

### 6.4 Fusão por RRF

*Reciprocal Rank Fusion* funde por **posição**, nunca por score: um score BM25 e
uma similaridade de cosseno vivem em escalas incomparáveis, e mediar os dois
produz um número sem significado. RRF só pergunta "em que lugar cada lista pôs
este chunk?" — `1/(k + posição)`, somado. A constante `k = 60` (valor canônico)
amortece o topo, de modo que o primeiro lugar de uma lista não atropele sozinho a
outra.

### 6.5 Rerank

`bge-reranker-v2-m3` é um **cross-encoder**: em vez de comparar dois vetores
calculados separadamente, lê a pergunta e o trecho **juntos** e pontua a relação.
É muito mais caro, por isso roda só sobre os 50 candidatos que sobreviveram à
fusão. É onde a precisão do topo se decide.

### 6.6 O que isso rende, medido

Para *"qual a dose de reposição de testosterona em implante hormonal?"*, com 96
chunks do corpus contendo dose em mg junto de testosterona/implante:

| etapa | alvos no top-200 | primeiras posições |
|---|---|---|
| denso | 45 | 1, 2, 3, 5, 6, 9 |
| BM25 | 38 | 4, 7, 11, 14 |
| após fusão RRF | 56 | 1, 3, 5, 9, 12 |

16 alvos chegam ao rerank; **6 ficam no top-10, contra 4 sem rerank**. Cada etapa
adiciona algo. O quanto exatamente é o que a régua da Etapa 6 vai dizer.

### 6.7 Pré-filtro por metadado

`search.py` aceita `--course`, `--subject` e `--instructor`, aplicados **antes**
da busca. Filtrar depois desperdiçaria as 50 vagas de candidato com chunks que
seriam descartados no fim.

O filtro por `--subject` só se torna útil depois da Etapa 5, que preenche
`lessons.subject`.

### 6.8 Geração

`ask.py` monta o prompt com os 10 trechos recuperados, cada um identificado por
curso, aula e instrutor, e instrui o modelo a:

- responder **somente** a partir dos trechos, sem completar com conhecimento próprio;
- dizer claramente quando os trechos não cobrem a pergunta, e parar;
- citar `[n]` para cada afirmação;
- **sinalizar valores e termos que pareçam inconsistentes**, porque o texto vem
  de ASR e números se corrompem;
- mostrar divergências entre trechos em vez de escolher um lado.

**As URLs não vêm do modelo.** O bloco `FONTES` é impresso pelo `ask.py` a partir
dos `lesson_url` do banco, sobre os chunks efetivamente recuperados. Um modelo
não tem como alucinar uma URL que ele nunca escreveu.

**E todo `[n]` precisa resolver.** A primeira versão do `FONTES` agrupava por
`lesson_uid` guardando só o primeiro rank de cada aula — e quebrava de forma
invisível: numa resposta real o modelo citou [5], [7] e [10], três chunks da
*mesma* aula, e o bloco mostrava só o [5]. A URL estava lá, sob outro rótulo, mas
quem procurasse [7] não achava número nenhum.

A lição generaliza: **uma URL correta não basta se o leitor não consegue chegar
até ela pelo caminho que a resposta indicou.** Citação irresolvível é citação não
verificável. `imprimir_fontes()` agora lista todos os rótulos por aula:
`[5] [7] [10] Aula 03: Disfunção Erétil`.

`llm.py` centraliza o cliente Anthropic e trata duas particularidades do Opus 5:

1. **O *thinking* vem ligado por padrão** e divide o teto de `max_tokens` com o
   texto da resposta. Um `max_tokens` dimensionado só para a resposta trunca no
   meio. O default aqui é folgado.
2. **Recusa chega como HTTP 200 com `stop_reason = 'refusal'`**, não como
   exceção. Ler `response.content[0]` sem checar quebra. Conteúdo clínico é área
   em que recusa por falso positivo acontece, então o fallback server-side fica
   ligado: numa recusa a própria API reexecuta em outro modelo dentro da mesma
   chamada.

---

## 7. Como avaliar e iterar

### O que já dá para afirmar, e o que não

**Dá:** a recuperação funciona para a pergunta-teste — o chunk de rank 1 é a Aula
16 de Implantes Hormonais do curso "Avançado de Saúde do homem", com URL real. E
a geração faz o que o prompt pede: numa pergunta sobre disfunção erétil, o modelo
sinalizou os erros de ASR, declarou explicitamente o que os trechos não cobriam, e
descartou sozinho os trechos de infertilidade por serem outro problema clínico.

**Não dá:** dizer qual das três estratégias de chunking é melhor, nem quanto o
prefixo contextual e o rerank contribuem. Isso é olhômetro até existir régua.

### Uma evidência de que o prefixo contextual pode estar prejudicando

A seção 6.1 argumenta que o prefixo "captura a maior parte do ganho" de graça.
A primeira medição contra uma pergunta real põe isso em dúvida.

Para *"quais as principais causas da impotência sexual e quais os tratamentos"*,
o cosseno de cada chunk recuperado contra a pergunta, com e sem o prefixo:

| rank | aula | cos(q, texto) | cos(q, prefixo+texto) | delta |
|---|---|---|---|---|
| 7 | **Disfunção Erétil** | 0,5753 | 0,5682 | **−0,0072** |
| 5 | **Disfunção Erétil** | 0,5611 | 0,5730 | +0,0119 |
| 10 | **Disfunção Erétil** | 0,5426 | 0,5307 | **−0,0119** |
| 1 | Fisiologia Causas Tratamento | 0,4798 | 0,5283 | **+0,0485** |
| 6 | Espermatogênese | 0,4909 | 0,5344 | **+0,0435** |
| 2 | Fisiologia Causas Tratamento | 0,5260 | 0,5537 | +0,0277 |

A única aula certa é a única que o prefixo prejudica; todo chunk fora do alvo
ganha. **Ordenando só pelo texto, os três chunks da aula certa seriam 1º, 2º e
3º** — com prefixo caíram para 5º, 7º e 10º.

O mecanismo está visível nos prefixos: a pergunta traz "causas" e "tratamentos",
e o curso errado se chama *"Avançado de Infertilidade e **Tratamento** Pré
Gestação"*, com a aula *"Fisiologia **Causas Tratamento**"*. O prefixo, que
deveria **situar** o trecho, virou ímã de palavra-chave — e vale para todos os
chunks daquele curso, independentemente do conteúdo. É uma falha previsível em
retrospecto: metadado repetido em milhares de chunks compete com o conteúdo
deles.

**Os limites desta medição, para não virar conclusão:** é *uma* pergunta, e só a
metade densa — não o pipeline completo com BM25, RRF e reranker. No BM25 o efeito
tende a ser pior, porque "tratamento" e "causas" são tokens exatos no prefixo.

Isso não condena o prefixo. Faz duas coisas: eleva a comparação "com × sem
prefixo" de formalidade a **pergunta em aberto**, e sugere inverter a ordem das
etapas 5 e 6 — enriquecer o prefixo antes de saber se ele ajuda é gastar US$ 8,25
para talvez amplificar o problema.

Vale registrar por que a coluna `context_prefix` foi separada de `text` lá atrás:
foi exatamente para permitir esta medição. A decisão de projeto pagou antes de a
régua existir.

Um aviso que este projeto já pagou para aprender: **não julgue um chunk pelo
começo.** Chunks têm ~366 palavras, e um recorte de 200 caracteres esconde a
informação — já levou a condenar erroneamente a qualidade da busca e a acusar o
reranker sem motivo. Por isso `search.py` mostra o início **e** o fim de cada
trecho.

### Um sinal de confiança que caiu no colo

O controle negativo — *"como configurar um roteador Cisco?"* — passou: o modelo
recusou. Mas fez algo mais interessante que recusar. Encontrou a única
coincidência lexical do corpus, um "router de glicemia" (que é um monitor
contínuo de 14 dias), e **explicou por que não servia**. Não a ignorou em
silêncio, nem a usou como ponte para fabricar uma resposta.

Isso levantou uma pergunta mensurável: dá para saber que a pergunta está fora do
corpus **antes** de chamar o modelo? Em 22 perguntas — 12 respondíveis pelo
corpus, 10 claramente fora — usando o maior score de rerank do top-10:

| classe | n | menor | maior |
|---|---|---|---|
| **dentro** do corpus | 12 | 0,5763 | 0,9937 |
| **fora** do corpus | 10 | 0,00005 | 0,0077 |

Separação de **75×, sem sobreposição**. Faz sentido: o cross-encoder lê pergunta
e trecho juntos e pontua a *relação* entre os dois — é a única etapa do pipeline
que pode dizer "isto não tem nada a ver". BM25 e busca densa sempre devolvem os
10 menos ruins, porque só sabem ordenar.

Duas ressalvas que a medição impõe:

- **Só vale com rerank ligado.** Os scores de RRF ficam todos em ~0,016–0,03 e
  não separam nada. São posições, não relevância.
- **A hipótese concorrente foi medida e caiu.** Parecia plausível que uma
  pergunta fora do corpus fizesse a recuperação se espalhar por muitas aulas.
  Não: a pergunta da testosterona (dentro) espalhou por 8 aulas e 6 cursos,
  igual à do Cisco (fora, 8 e 7). Dispersão não separa; score separa. Vale como
  lembrete de que a explicação plausível e a explicação certa não são a mesma —
  o mesmo erro da seção 2.5, em outra roupa.

**Por que isso não virou um portão em `ask.py`.** Seria fácil recusar sem chamar
o modelo quando o score fica abaixo de ~0,05, e classificaria certo nas 22
perguntas. Mas a economia é irrelevante num uso de estudo, e o custo é real: a
recusa do modelo foi *mais informativa* que qualquer mensagem enlatada — foi ela
que apontou o "router de glicemia". Trocar uma resposta que raciocina por uma
constante, para economizar centavos, é o tipo de otimização que piora o produto.

O lugar certo deste número é a régua: **confiança por pergunta**, gravada ao lado
de recall e MRR.

### A régua planejada (Etapa 6 — ainda não construída)

Três tabelas, a acrescentar em `db.py`:

| tabela | uma linha por | colunas centrais |
|---|---|---|
| `eval_questions` | pergunta | `question`, `expected_lesson_uid`, dificuldade, origem, quem validou |
| `eval_runs` | configuração testada | o JSON da config (estratégia, prefixo on/off, rerank on/off, k) |
| `eval_results` | (pergunta × run) | posição do esperado, `hit@k`, *reciprocal rank* |

`build_eval_set.py` gera ~100 candidatas: amostra chunks estratificados por curso
e pede ao LLM uma pergunta **respondível apenas por aquele trecho**. Você valida
num relatório Markdown — descartar uma pergunta ruim leva segundos, e **sem essa
passagem humana a régua não vale nada**: uma régua gerada e avaliada pela mesma
família de modelo mede a coerência dela consigo mesma, não a qualidade da busca.

`eval_retrieval.py` roda cada configuração e mede:

| métrica | responde |
|---|---|
| **recall@k** | a aula certa apareceu entre as k primeiras? |
| **MRR** | em que posição, em média? (1/posição — penaliza forte cair do 1º para o 3º) |
| **nDCG@10** | quão bem ordenado está o top-10, dando mais peso ao topo |

As três comparações que importam:

- chunk `fixed` × `semantic` × `qa_turn`;
- com × sem prefixo contextual;
- denso puro × híbrido × híbrido + rerank.

Aí a escolha vira experimento medido, não preferência.

### A ordem, e por que ela mudou

A recomendação inicial era "conjunto de avaliação primeiro". Foi revista: a régua
governa a **escolha entre estratégias**, não a **construção da primeira**.
Construir o pipeline com um chunking padrão sensato não depende dela — e você
pediu um MVP para testar.

Então: pipeline ponta a ponta primeiro, régua depois, comparação por último. É
mudança de sequência, não de convicção.

### Enriquecimento (Etapa 5 — ainda não construído)

`enrich_lessons.py` preenche `subject`, `topics[]` e `summary` nas 206 aulas, via
Batch API (metade do preço, e é trabalho sem pressa de latência) com saída
estruturada por JSON Schema — sem parsing frágil de texto. A maior aula tem ~43 k
tokens e a janela é de 1 M, então nenhuma precisa ser partida. Custo estimado:
**~US$ 8,25**, uma vez.

Habilita duas coisas concretas: o pré-filtro por assunto, e um prefixo contextual
bem mais informativo. Depois disso, **reconstruir os chunks** para o assunto
entrar no prefixo.

Antes de soltar o lote: revisar 10 aulas à mão.

### O teste de reprodutibilidade

Apagar `ragmed.duckdb` e rodar a sequência completa da seção 5 reproduz o mesmo
estado. Já passou duas vezes neste projeto, e a intenção é que continue passando
— é o que garante que o banco seja de fato derivado, e que o conhecimento esteja
nos arquivos versionados, não em algo que alguém digitou uma vez.
