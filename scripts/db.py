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
    -- Julgamento humano sobre o dominio, gravado a parte da heuristica
    -- lesson_quality.domain para que reprocessar o perfil nao o apague.
    domain_reviewed     VARCHAR,   -- 'clinical' | 'business'
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
    -- Aponta para a copia canonica quando duas aulas tem o mesmo conteudo.
    -- NULL = e a propria canonica. Serve para o chunker indexar so uma vez
    -- sem que a outra aula perca a transcricao nem vire pendencia.
    duplicate_of        VARCHAR,
    updated_at          TIMESTAMP NOT NULL
);

-- Perfil de cada transcricao. Separa medida de julgamento: as colunas de
-- contagem sao fato; as duas ultimas sao heuristicas com regra documentada em
-- scripts/profile_corpus.py, feitas para serem revisadas, nao obedecidas.
CREATE TABLE IF NOT EXISTS lesson_quality (
    lesson_uid            VARCHAR PRIMARY KEY,
    -- medidas
    word_count            BIGINT,
    sentence_count        BIGINT,
    sentence_median_words DOUBLE,   -- fala fica ~7, texto escrito ~15-20
    question_count        BIGINT,
    questions_per_1k      DOUBLE,   -- proxy de Q&A embutido
    filler_pct            DOUBLE,   -- muletas de fala sobre o total de palavras
    type_token_ratio      DOUBLE,   -- riqueza lexical; baixo = repetitivo
    course_median_words   DOUBLE,
    length_ratio          DOUBLE,   -- word_count / mediana do proprio curso
    clinical_score        DOUBLE,   -- 0 = so negocios, 1 = so clinico
    -- julgamentos (heuristicos)
    truncation_suspect    BOOLEAN,
    domain                VARCHAR,  -- 'clinical' | 'business' | 'mixed'
    computed_at           TIMESTAMP NOT NULL
);

-- A unidade que o RAG recupera. Uma aula vira muitos chunks.
--
-- chunk_uid = <lesson_uid>::<estrategia>::<indice>, ex. lsn_3521413::fixed::0007.
-- A estrategia entra no id porque o mesmo trecho cortado de duas formas sao dois
-- chunks distintos, e as tres convivem na tabela durante a comparacao. Estavel
-- enquanto a estrategia e seus parametros nao mudarem, e sempre rastreavel ate a
-- aula e ate o trecho exato do arquivo por char_start/char_end.
--
-- text e context_prefix ficam em colunas separadas de proposito: o prefixo situa
-- o trecho na aula ("de que curso, que aula, que assunto isto veio") e melhora a
-- recuperacao, mas guardar os dois juntos impediria medir o ganho dele.
CREATE TABLE IF NOT EXISTS chunks (
    chunk_uid       VARCHAR PRIMARY KEY,
    lesson_uid      VARCHAR NOT NULL,
    chunk_index     INTEGER NOT NULL,
    text            VARCHAR NOT NULL,
    context_prefix  VARCHAR,           -- derivado dos metadados, sem chamada de LLM
    char_start      BIGINT NOT NULL,   -- offset no arquivo de origem
    char_end        BIGINT NOT NULL,
    word_count      INTEGER,
    token_estimate  INTEGER,
    strategy        VARCHAR NOT NULL,  -- 'fixed' | 'semantic' | 'qa_turn'
    created_at      TIMESTAMP NOT NULL
);

-- Vetores densos, um por chunk. Guardados aqui mesmo em vez de num vector store
-- separado: com ~6 mil chunks, forca bruta com array_cosine_similarity responde
-- em milissegundos e evita mais uma peca movel no sistema.
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_uid       VARCHAR PRIMARY KEY,
    embedding       FLOAT[1024] NOT NULL,   -- BAAI/bge-m3, normalizado
    model           VARCHAR NOT NULL,
    created_at      TIMESTAMP NOT NULL
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

-- O CORPUS DO RAG. Esta view e a definicao unica do que entra no indice;
-- nenhum script deve reimplementar o criterio por conta propria.
--
-- Uma aula entra se, e so se:
--   1. origin = 'site'      material local fica de fora POR ORA - ver a nota
--                           em data/curation.json. Sao extras e um curso
--                           retirado da vitrine, sem URL nem posicao no site,
--                           entao nao da para citar a fonte numa resposta.
--   2. duplicate_of IS NULL so a copia canonica de cada conteudo repetido, para
--                           o RAG nao devolver a mesma explicacao duas vezes.
--   3. dominio clinico      o veredito humano (domain_reviewed) tem precedencia
--                           sobre a heuristica (lesson_quality.domain).
--   4. tem transcricao
CREATE OR REPLACE VIEW v_rag_corpus AS
SELECT
    l.lesson_uid,
    c.course_uid,
    c.course_title,
    l.group_title,
    l.lesson_title,
    l.lesson_url,
    l.instructor,
    l.year,
    l.subject,
    l.topics,
    l.summary,
    l.position_global,
    t.path,
    t.md5,
    t.word_count,
    t.est_tokens
FROM lessons l
JOIN courses c USING (course_uid)
JOIN transcripts t USING (lesson_uid)
LEFT JOIN lesson_quality q USING (lesson_uid)
WHERE l.origin = 'site'
  AND t.duplicate_of IS NULL
  AND COALESCE(l.domain_reviewed, q.domain) = 'clinical'
ORDER BY c.position_in_vitrine, l.position_global;

-- O complemento: tudo que ficou de fora, e por que. Nada some em silencio.
CREATE OR REPLACE VIEW v_rag_excluded AS
SELECT
    l.lesson_uid,
    c.course_title,
    l.lesson_title,
    t.word_count,
    CASE
        WHEN t.lesson_uid IS NULL        THEN 'sem transcricao'
        WHEN l.origin = 'local'          THEN 'origem local (fora por ora)'
        WHEN t.duplicate_of IS NOT NULL  THEN 'copia de ' || t.duplicate_of
        WHEN q.lesson_uid IS NULL        THEN 'sem perfil - rode profile_corpus.py'
        ELSE 'dominio ' || COALESCE(l.domain_reviewed, q.domain)
    END AS motivo
FROM lessons l
JOIN courses c USING (course_uid)
LEFT JOIN transcripts t USING (lesson_uid)
LEFT JOIN lesson_quality q USING (lesson_uid)
WHERE l.lesson_uid NOT IN (SELECT lesson_uid FROM v_rag_corpus)
ORDER BY motivo, c.position_in_vitrine, l.position_global;

-- O que o indice realmente contem: chunk + a identidade da aula de origem.
-- E a superficie que search.py consulta e que a geracao usa para citar a fonte.
CREATE OR REPLACE VIEW v_chunk_corpus AS
SELECT
    ch.chunk_uid,
    ch.lesson_uid,
    ch.chunk_index,
    ch.strategy,
    ch.text,
    ch.context_prefix,
    ch.context_prefix || ch.text AS text_with_context,
    ch.word_count,
    ch.token_estimate,
    l.lesson_title,
    l.lesson_url,
    l.instructor,
    l.subject,
    l.topics,
    c.course_uid,
    c.course_title,
    c.position_in_vitrine,
    l.position_global
FROM chunks ch
JOIN lessons l USING (lesson_uid)
JOIN courses c USING (course_uid)
ORDER BY c.position_in_vitrine, l.position_global, ch.chunk_index;

-- Aulas que merecem um olhar antes de entrarem no indice do RAG.
CREATE OR REPLACE VIEW v_quality_review AS
SELECT
    q.lesson_uid,
    c.course_title,
    l.lesson_title,
    q.word_count,
    q.course_median_words,
    round(q.length_ratio, 2)   AS length_ratio,
    round(q.clinical_score, 2) AS clinical_score,
    q.domain,
    q.truncation_suspect,
    t.path
FROM lesson_quality q
JOIN lessons l USING (lesson_uid)
JOIN courses c USING (course_uid)
JOIN transcripts t USING (lesson_uid)
WHERE q.truncation_suspect OR q.domain <> 'clinical'
ORDER BY q.truncation_suspect DESC, q.length_ratio;

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
