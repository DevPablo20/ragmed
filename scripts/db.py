#!/usr/bin/env python3
"""Esquema e conexao do ragmed.duckdb - fonte unica de verdade do DDL.

O banco guarda os metadados do site (cursos e aulas) com historico por execucao
de scrape, e liga cada aula a sua transcricao local.

Divisao deliberada de responsabilidade:

    courses / lessons / *_snapshots   escritos SO pelo loader do site
    transcripts                       escrito SO pelo build local

Isso existe para que rodar o scrape de novo nunca sobrescreva nem apague o que
e seu. As duas metades so se encontram nas views.

Nada e deletado: aula que sai do ar vira is_active = false e continua
consultavel, com last_seen_at dizendo quando foi vista pela ultima vez.

Uso:
    python scripts/db.py            # cria/atualiza o esquema e mostra o estado
"""

from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "ragmed.duckdb"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
TRANSCRIPT_DIR = ROOT / "transcripts"

COURSE_PREFIX = "crs_"
LESSON_PREFIX = "lsn_"
LOCAL_COURSE_PREFIX = "crs_loc_"
LOCAL_LESSON_PREFIX = "lsn_loc_"


def course_uid(site_course_id: str) -> str:
    return f"{COURSE_PREFIX}{site_course_id}"


def lesson_uid(site_lesson_id: str) -> str:
    return f"{LESSON_PREFIX}{site_lesson_id}"


def local_uid(prefix: str, identity: str) -> str:
    """Id estavel para material que nunca esteve na vitrine.

    Deriva do caminho original do arquivo, que e a identidade dele. E estavel
    porque esse caminho vira uma string historica gravada em transcripts.source_path
    - nao depende da pasta continuar existindo em disco.
    """
    import hashlib

    return f"{prefix}{hashlib.md5(identity.encode('utf-8')).hexdigest()[:8]}"


SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS seq_run_id START 1;

-- Uma linha por execucao do scrape. E o eixo temporal de tudo.
CREATE TABLE IF NOT EXISTS scrape_runs (
    run_id          BIGINT PRIMARY KEY DEFAULT nextval('seq_run_id'),
    scraped_at      TIMESTAMP NOT NULL,   -- quando o snapshot saiu do site
    loaded_at       TIMESTAMP NOT NULL,   -- quando entrou no banco
    snapshot_path   VARCHAR,
    n_courses       INTEGER,
    n_lessons       INTEGER,
    n_courses_new   INTEGER,
    n_lessons_new   INTEGER,
    n_courses_gone  INTEGER,
    n_lessons_gone  INTEGER
);

CREATE TABLE IF NOT EXISTS courses (
    course_uid          VARCHAR PRIMARY KEY,   -- crs_<site_course_id> | crs_loc_<hash>
    origin              VARCHAR NOT NULL,      -- 'site' | 'local'
    site_course_id      VARCHAR,               -- nulo quando origin = 'local'
    course_title        VARCHAR NOT NULL,
    course_url          VARCHAR,
    course_kind         VARCHAR,               -- 'produto' | 'aula'
    position_in_vitrine INTEGER,
    group_count         INTEGER,
    lesson_count        INTEGER,
    first_seen_at       TIMESTAMP NOT NULL,
    first_seen_run_id   BIGINT,                -- nulo para origin = 'local'
    last_seen_at        TIMESTAMP NOT NULL,
    last_seen_run_id    BIGINT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE  -- presente na ultima raspagem
);

CREATE TABLE IF NOT EXISTS lessons (
    lesson_uid          VARCHAR PRIMARY KEY,   -- lsn_<site_lesson_id> | lsn_loc_<hash>
    course_uid          VARCHAR NOT NULL,
    origin              VARCHAR NOT NULL,      -- 'site' | 'local'
    site_lesson_id      VARCHAR,               -- nulo quando origin = 'local'
    lesson_title        VARCHAR NOT NULL,
    lesson_url          VARCHAR,
    -- grupo desnormalizado: so 3 dos 35 cursos tem mais de um
    site_group_id       VARCHAR,
    group_title         VARCHAR,
    group_index         INTEGER,
    position_in_group   INTEGER,
    position_global     INTEGER,
    -- heuristicas
    instructor          VARCHAR,
    instructor_source   VARCHAR,               -- 'site_title' | 'filename'
    year                INTEGER,
    -- enriquecimento posterior (LLM sobre a transcricao)
    subject             VARCHAR,
    topics              VARCHAR[],
    summary             VARCHAR,
    enrichment_source   VARCHAR,
    enriched_at         TIMESTAMP,
    first_seen_at       TIMESTAMP NOT NULL,
    first_seen_run_id   BIGINT,                -- nulo para origin = 'local'
    last_seen_at        TIMESTAMP NOT NULL,
    last_seen_run_id    BIGINT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE  -- presente na ultima raspagem
);

-- 1:1 com lessons. Vive separado porque o ciclo de vida e outro: o scrape
-- do site nunca escreve aqui.
CREATE TABLE IF NOT EXISTS transcripts (
    lesson_uid          VARCHAR PRIMARY KEY,
    path                VARCHAR NOT NULL,      -- transcripts/<lesson_uid>.txt
    source_path         VARCHAR,               -- de onde veio (procedencia historica)
    md5                 VARCHAR NOT NULL,
    char_count          BIGINT,
    word_count          BIGINT,
    est_tokens          BIGINT,
    file_size_bytes     BIGINT,
    lang                VARCHAR,
    match_confidence    VARCHAR,               -- 'high' | 'medium'
    match_signals       VARCHAR,
    updated_at          TIMESTAMP NOT NULL
);

-- Append-only: o estado de cada curso/aula em cada execucao. E o que permite
-- ver renomeacao e reordenacao ao longo do tempo.
CREATE TABLE IF NOT EXISTS course_snapshots (
    run_id              BIGINT NOT NULL,
    course_uid          VARCHAR NOT NULL,
    course_title        VARCHAR,
    position_in_vitrine INTEGER,
    lesson_count        INTEGER,
    PRIMARY KEY (run_id, course_uid)
);

CREATE TABLE IF NOT EXISTS lesson_snapshots (
    run_id              BIGINT NOT NULL,
    lesson_uid          VARCHAR NOT NULL,
    course_uid          VARCHAR NOT NULL,
    lesson_title        VARCHAR,
    group_title         VARCHAR,
    group_index         INTEGER,
    position_in_group   INTEGER,
    position_global     INTEGER,
    PRIMARY KEY (run_id, lesson_uid)
);
"""

VIEWS = """
-- A lista de trabalho: aulas no ar que ainda nao foram transcritas.
-- O arquivo a criar chama-se transcripts/<lesson_uid>.txt.
CREATE OR REPLACE VIEW v_pending_downloads AS
SELECT
    l.lesson_uid,
    c.course_title,
    l.group_title,
    l.lesson_title,
    l.lesson_url,
    l.position_global,
    l.first_seen_at AS visto_desde,
    'transcripts/' || l.lesson_uid || '.txt' AS destino
FROM lessons l
JOIN courses c USING (course_uid)
LEFT JOIN transcripts t USING (lesson_uid)
WHERE l.origin = 'site'
  AND l.is_active
  AND t.lesson_uid IS NULL
ORDER BY c.position_in_vitrine, l.position_global;

-- Aulas que apareceram na execucao mais recente.
CREATE OR REPLACE VIEW v_new_lessons AS
SELECT
    l.lesson_uid,
    c.course_title,
    l.lesson_title,
    l.lesson_url,
    l.first_seen_at,
    l.first_seen_run_id
FROM lessons l
JOIN courses c USING (course_uid)
WHERE l.first_seen_run_id = (SELECT max(run_id) FROM scrape_runs)
ORDER BY c.position_in_vitrine, l.position_global;

-- Aulas que estiveram no site e sairam do ar. A transcricao continua ligada.
CREATE OR REPLACE VIEW v_removed_from_site AS
SELECT
    l.lesson_uid,
    c.course_title,
    l.lesson_title,
    l.last_seen_at AS sumiu_apos,
    l.last_seen_run_id,
    t.path,
    t.word_count
FROM lessons l
JOIN courses c USING (course_uid)
LEFT JOIN transcripts t USING (lesson_uid)
WHERE l.origin = 'site' AND NOT l.is_active
ORDER BY l.last_seen_at DESC, c.position_in_vitrine, l.position_global;

-- Material que nunca esteve na vitrine: extras, cursos retirados antes da
-- primeira raspagem, arquivos avulsos. Existe so porque voce tem o texto.
CREATE OR REPLACE VIEW v_local_only AS
SELECT
    l.lesson_uid,
    c.course_title,
    l.lesson_title,
    t.source_path,
    t.path,
    t.word_count
FROM lessons l
JOIN courses c USING (course_uid)
LEFT JOIN transcripts t USING (lesson_uid)
WHERE l.origin = 'local'
ORDER BY c.course_title, l.position_global;

-- Join achatado: a superficie que o RAG e os exports consomem.
CREATE OR REPLACE VIEW v_corpus AS
SELECT
    l.lesson_uid,
    c.course_uid,
    l.origin,
    c.course_title,
    c.course_url,
    l.group_title,
    l.group_index,
    l.lesson_title,
    l.lesson_url,
    l.position_in_group,
    l.position_global,
    l.instructor,
    l.instructor_source,
    l.year,
    l.subject,
    l.topics,
    l.summary,
    t.path,
    t.source_path,
    t.md5,
    t.char_count,
    t.word_count,
    t.est_tokens,
    t.file_size_bytes,
    t.lang,
    t.match_confidence,
    t.match_signals,
    l.is_active AS lesson_is_active,
    CASE
        WHEN t.lesson_uid IS NOT NULL AND l.origin = 'local' THEN 'local_only'
        WHEN t.lesson_uid IS NOT NULL                        THEN 'ok'
        WHEN l.is_active                                     THEN 'pending_transcription'
        ELSE 'removed_from_site'
    END AS status
FROM lessons l
JOIN courses c USING (course_uid)
LEFT JOIN transcripts t USING (lesson_uid)
ORDER BY c.position_in_vitrine, l.position_global;

-- Historico de execucoes, com o delta de cada uma.
CREATE OR REPLACE VIEW v_run_history AS
SELECT
    run_id,
    scraped_at,
    n_courses,
    n_lessons,
    n_courses_new,
    n_lessons_new,
    n_courses_gone,
    n_lessons_gone,
    snapshot_path
FROM scrape_runs
ORDER BY run_id DESC;
"""


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def init(con: duckdb.DuckDBPyConnection) -> None:
    """Idempotente: pode rodar em banco novo ou existente."""
    con.execute(SCHEMA)
    con.execute(VIEWS)


def main() -> None:
    con = connect()
    init(con)
    print(f"esquema aplicado em {DB_PATH}")

    tables = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_type, table_name"
    ).fetchall()
    for (name,) in tables:
        n = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
        print(f"  {name:<22} {n:>6}")
    con.close()


if __name__ == "__main__":
    main()
