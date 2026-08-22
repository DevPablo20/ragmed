# ragmed

Corpus de transcrições das aulas do Avantgarde College. Os metadados vivem em um
banco DuckDB; cada transcrição é um arquivo nomeado pelo identificador da aula.

```
ragmed.duckdb              fonte de verdade
transcripts/               244 .txt — transcripts/lsn_3521413.txt
data/
├── snapshots/             um JSON por raspagem, nunca sobrescrito
├── manifest.csv/.parquet  export de v_corpus, para quem prefere CSV a SQL
├── local_lessons.json     registro das 21 aulas que nunca estiveram na vitrine
└── matched_map.json       procedência: de que arquivo veio cada transcrição
scripts/
├── db.py                  esquema (DDL + views) e conexão
├── scrape_snippet.js      extrator para colar no console do DevTools
├── load_snapshot.py       snapshot → banco, com relatório de diff
├── sync_transcripts.py    varre transcripts/, atualiza a tabela
└── queries.sql            consultas prontas
```

## O ciclo

**1. Raspar.** Logado em `/area/vitrine/home`, cole [scripts/scrape_snippet.js](scripts/scrape_snippet.js)
no console do DevTools. Ele baixa `snapshot_<timestamp>.json`.

```bash
~/.pyenv/versions/medrag/bin/python scripts/load_snapshot.py data/snapshots/snapshot_20261101T093000.json
```

O loader imprime o que mudou: cursos e aulas novos, o que saiu do ar, títulos
alterados.

**2. Ver o que falta.**

```sql
SELECT * FROM v_pending_downloads;
```

A coluna `destino` já diz com que nome gravar o arquivo.

**3. Transcrever e registrar.** Salve o texto como `transcripts/<lesson_uid>.txt` e:

```bash
~/.pyenv/versions/medrag/bin/python scripts/sync_transcripts.py
```

Não há casamento a fazer: **o nome do arquivo é o identificador**.

## Tabelas

| tabela | quem escreve | o que guarda |
|---|---|---|
| `scrape_runs` | loader | uma linha por raspagem: `scraped_at`, totais, deltas |
| `courses` | loader / migração | catálogo, `first_seen`/`last_seen`/`is_active`, `origin` |
| `lessons` | loader / migração | aulas, grupo, instrutor, slots de enriquecimento |
| `transcripts` | sync | `path`, `md5`, contagens, procedência |
| `course_snapshots`, `lesson_snapshots` | loader | append-only, o estado de cada raspagem |

**A separação entre `lessons` e `transcripts` é deliberada.** O loader nunca
escreve em `transcripts`, e o sync nunca escreve em `lessons` — re-raspar não
pode sobrescrever nem apagar o que é seu.

**Nada é deletado.** Aula que sai do ar vira `is_active = false` e continua
consultável, com `last_seen_at` marcando quando foi vista pela última vez e a
transcrição ainda ligada.

**`origin`** distingue as duas procedências: `site` (226 aulas, vindas da
vitrine) e `local` (21 transcrições que nunca estiveram lá — material extra e a
Imersão 2024, curso retirado antes da primeira raspagem).

## Identificadores

`crs_<id do site>` e `lsn_<id do site>` — imutáveis, porque vêm da chave de
banco da plataforma. Material de origem local usa `crs_loc_<hash>` / `lsn_loc_<hash>`,
derivado do caminho original do arquivo.

Chunk id para o RAG: `lsn_3521413::0007`.

## Views

- **`v_pending_downloads`** — aulas no ar sem transcrição, com o nome do arquivo a criar.
- **`v_new_lessons`** — o que apareceu na raspagem mais recente.
- **`v_removed_from_site`** — o que esteve no site e saiu, com a transcrição preservada.
- **`v_local_only`** — o que nunca esteve na vitrine.
- **`v_corpus`** — join achatado; é o que `data/manifest.csv` exporta.
- **`v_run_history`** — as raspagens e seus deltas.

Consultas prontas em [scripts/queries.sql](scripts/queries.sql).

## Estado atual

Raspagem de 2026-08-22 (execução 1): 35 cursos e 226 aulas na vitrine.
**244 transcrições** — 223 casadas com aulas do site, 21 de origem local.

**3 aulas aguardando transcrição:**

| gravar como | curso | aula |
|---|---|---|
| `transcripts/lsn_9073011.txt` | ORIGEM — Boas-vindas | ORIGEM — Boas-vindas |
| `transcripts/lsn_9354505.txt` | Pré-Imersão 2026 | Tríade Energética - Cortisol |
| `transcripts/lsn_7773605.txt` | Avançado de Doenças Autoimunes | Aula 05 - Dra Vivian Campos |

## Histórico

O corpus veio de pastas com nomes de arquivo inconsistentes (acentos, espaços,
`.docx.txt`, sufixos de vídeo), casadas com o site por um matcher difuso que
combinava número da aula, similaridade de título e posição. Esse matcher foi
aposentado na migração para identificadores: o resultado dele está preservado em
`data/matched_map.json` (com `match_confidence` de cada casamento, também no
banco), e não é mais necessário porque o arquivo passou a se chamar pelo `lesson_uid`.
