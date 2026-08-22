# ragmed

Corpus de transcrições das aulas do Avantgarde College. Os metadados vivem em um
banco DuckDB; cada transcrição é um arquivo `.txt` nomeado pelo identificador da
aula.

```
ragmed.duckdb              fonte de verdade
transcripts/               247 .txt — transcripts/lsn_3521413.txt
data/
├── snapshots/             uma raspagem do site por arquivo, nunca sobrescrito
├── local_lessons.json     identidade das 21 aulas que nunca estiveram na vitrine
├── matched_map.json       procedência histórica (só arquivo, nada depende dele)
└── manifest.csv/.parquet  export de v_corpus, regenerado a cada sync
scripts/
├── db.py                  esquema (DDL + views) e conexão
├── scrape_snippet.js      extrator para colar no console do DevTools
├── load_snapshot.py       snapshot do site → banco
├── load_local.py          aulas de origem local → banco
├── sync_transcripts.py    transcripts/ → banco, e export do manifest
└── queries.sql            consultas prontas
```

Tudo roda com o Python do ambiente `medrag`:

```bash
alias pyr=~/.pyenv/versions/medrag/bin/python
```

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

---

## Consultar

O banco é a interface principal. Sem CLI do duckdb instalado, o caminho é o Python:

```bash
pyr -c "import duckdb; print(duckdb.connect('ragmed.duckdb').execute('SELECT * FROM v_pending_downloads').df())"
```

Ou, mais confortável, num notebook:

```python
import duckdb
con = duckdb.connect("ragmed.duckdb", read_only=True)
con.execute("SELECT * FROM v_corpus WHERE status = 'ok'").df()
```

Consultas prontas e comentadas em [scripts/queries.sql](scripts/queries.sql):
cobertura por curso, volume por instrutor, transcrições curtas demais para o
curso (candidatas a download truncado), trajetória de uma aula ao longo das
raspagens.

### Views

| view | para quê |
|---|---|
| `v_pending_downloads` | aulas no ar sem transcrição, com o nome do arquivo a criar |
| `v_new_lessons` | o que apareceu na raspagem mais recente |
| `v_removed_from_site` | o que esteve no site e saiu, com a transcrição preservada |
| `v_local_only` | o que nunca esteve na vitrine |
| `v_corpus` | join achatado — é o que `data/manifest.csv` exporta |
| `v_run_history` | as raspagens e seus deltas |

---

## Quais arquivos importam

Nem tudo em `data/` tem o mesmo peso. A distinção que interessa é: **o que é
insubstituível, o que é regenerável, e o que é só histórico.**

| arquivo | precisa? | atualiza quando? |
|---|---|---|
| `transcripts/*.txt` | **insubstituível** | você escreve |
| `ragmed.duckdb` | reconstruível (veja abaixo) | loaders e sync |
| `data/snapshots/*.json` | **insubstituível** | uma por raspagem, nunca sobrescrita |
| `data/local_lessons.json` | **insubstituível** | congelado na migração |
| `data/manifest.csv/.parquet` | descartável | todo `sync_transcripts.py` |
| `data/matched_map.json` | dispensável | congelado na migração |

**`manifest.csv` e `manifest.parquet`** são um export da view `v_corpus`, nada
mais. Existem para você abrir no pandas ou no Excel sem passar por SQL. Estão
sempre em dia porque o sync os reescreve; se apagar, voltam no próximo sync.
Não são fonte de nada.

**`local_lessons.json` é insubstituível**, e vale entender por quê. As 21
transcrições de origem local não aparecem em nenhum snapshot do site — são
material extra e a Imersão 2024, curso retirado da vitrine antes da primeira
raspagem. Os arquivos delas se chamam `lsn_loc_<hash>`, e esse hash foi derivado
do caminho original em `raw/`, pasta que não existe mais. Este JSON é o único
lugar fora do banco que sabe qual arquivo é qual aula. Sem ele, uma reconstrução
deixaria 21 arquivos órfãos.

**`matched_map.json` é só memória.** Registra de que arquivo de `raw/` veio cada
uma das 223 transcrições originais e com que confiança o matcher casou. Todo o
conteúdo já está no banco, nas colunas `source_path`, `match_confidence` e
`match_signals` de `transcripts` — conferido, sem divergência. Nenhum script lê
esse arquivo. Guardar ou apagar é indiferente; mantive por ser barato (47 KB) e
por documentar uma etapa que não dá para refazer.

Os dois JSONs de migração **não acompanham o sync de propósito** — eles descrevem
como o corpus chegou aqui, não como ele está agora. Ver a data deles parada é o
comportamento correto.

---

## Reconstruir o banco do zero

O banco é derivado. Se corromper, ou se você quiser refazê-lo com um esquema novo:

```bash
rm ragmed.duckdb
pyr scripts/db.py
pyr scripts/load_snapshot.py data/snapshots/<mais-recente>.json
pyr scripts/load_local.py
pyr scripts/sync_transcripts.py
```

Testado: reproduz 36 cursos, 247 aulas e 247 transcrições com md5 idêntico ao
banco atual, sem órfãos.

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
| `course_snapshots`, `lesson_snapshots` | `load_snapshot` | append-only, o estado de cada raspagem |

**A separação entre `lessons` e `transcripts` é deliberada.** Os loaders nunca
escrevem em `transcripts`, e o sync nunca escreve em `lessons` — re-raspar o site
não pode sobrescrever nem apagar o que é seu.

**Nada é deletado.** Aula que sai do ar vira `is_active = false` e continua
consultável, com `last_seen_at` marcando quando foi vista pela última vez e a
transcrição ainda ligada a ela.

**`origin`** separa as duas procedências: `site` (226 aulas da vitrine) e `local`
(21 que nunca estiveram lá).

### Identificadores

`crs_<id do site>` e `lsn_<id do site>` — imutáveis, porque vêm da chave de banco
da plataforma. Material local usa `crs_loc_<hash>` / `lsn_loc_<hash>`.

Id de chunk para o RAG: `lsn_3521413::0007`.

### Enriquecimento pendente

`lessons` tem `subject`, `topics`, `summary`, `enrichment_source` e `enriched_at`
vazios, reservados para uma passada de LLM sobre as transcrições. O site não
expõe assunto — só o título. Aulas ainda sem enriquecer:

```sql
SELECT l.lesson_uid, l.lesson_title, t.path, t.word_count
FROM lessons l JOIN transcripts t USING (lesson_uid)
WHERE l.subject IS NULL ORDER BY t.word_count DESC;
```

---

## Estado atual

247 transcrições — 226 casadas com aulas do site, 21 de origem local.
**Zero pendências.**

## Histórico

O corpus veio de pastas com nomes de arquivo inconsistentes (acentos, espaços,
`.docx.txt`, sufixos de vídeo), casadas com o site por um matcher difuso que
combinava número da aula, similaridade de título e posição. Esse matcher foi
aposentado na migração para identificadores: o resultado dele está no banco (e em
`data/matched_map.json`), e ele não é mais necessário porque o arquivo passou a se
chamar pelo `lesson_uid`.
