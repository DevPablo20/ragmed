-- Consultas prontas para o ragmed.duckdb.
--
--   duckdb ragmed.duckdb          (se instalar o CLI)
--   ~/.pyenv/versions/medrag/bin/python -c "import duckdb; \
--     print(duckdb.connect('ragmed.duckdb').execute(open('scripts/queries.sql').read()).df())"
--
-- Ou, mais confortavel, dentro do notebook:
--   import duckdb; con = duckdb.connect('ragmed.duckdb'); con.execute(...).df()


-- ===========================================================================
-- O DIA A DIA
-- ===========================================================================

-- O que falta baixar e transcrever. E a lista de trabalho: a coluna `destino`
-- ja diz com que nome gravar o arquivo.
SELECT * FROM v_pending_downloads;

-- Material que nunca esteve na vitrine (extras, cursos retirados antes da
-- primeira raspagem). Existe no corpus so porque voce tem o texto.
SELECT * FROM v_local_only;

-- O que apareceu na ultima raspagem.
SELECT * FROM v_new_lessons;

-- O que saiu do ar (a transcricao continua ligada e acessivel).
SELECT * FROM v_removed_from_site;

-- Historico das raspagens, com o delta de cada uma.
SELECT * FROM v_run_history;


-- ===========================================================================
-- PANORAMA DO CORPUS
-- ===========================================================================

-- Cobertura por curso: quanto ja esta transcrito.
SELECT
    c.course_title,
    count(*)                                     AS aulas,
    count(t.lesson_uid)                          AS transcritas,
    count(*) - count(t.lesson_uid)               AS faltando,
    round(100.0 * count(t.lesson_uid) / count(*), 1) AS pct,
    sum(t.word_count)                            AS palavras
FROM lessons l
JOIN courses c USING (course_uid)
LEFT JOIN transcripts t USING (lesson_uid)
WHERE l.is_active
GROUP BY c.course_title, c.position_in_vitrine
ORDER BY c.position_in_vitrine;

-- Volume de texto por instrutor.
SELECT
    l.instructor,
    count(*)          AS aulas,
    sum(t.word_count) AS palavras,
    round(avg(t.word_count)) AS media
FROM lessons l
JOIN transcripts t USING (lesson_uid)
WHERE l.instructor IS NOT NULL
GROUP BY l.instructor
ORDER BY palavras DESC;

-- Transcricoes curtas demais para o curso: candidatas a download truncado.
-- Compara cada aula com a mediana do proprio curso, nao com a global.
SELECT
    c.course_title,
    l.lesson_title,
    t.word_count,
    median(t.word_count) OVER (PARTITION BY c.course_uid) AS mediana_do_curso,
    t.path
FROM transcripts t
JOIN lessons l USING (lesson_uid)
JOIN courses c USING (course_uid)
QUALIFY t.word_count < 0.25 * mediana_do_curso
ORDER BY t.word_count;


-- ===========================================================================
-- HISTORICO
-- ===========================================================================

-- Aulas que mudaram de titulo entre duas raspagens.
SELECT
    a.lesson_uid,
    b.lesson_title AS antes,
    a.lesson_title AS depois
FROM lesson_snapshots a
JOIN lesson_snapshots b USING (lesson_uid)
WHERE a.run_id = (SELECT max(run_id) FROM scrape_runs)
  AND b.run_id = (SELECT max(run_id) - 1 FROM scrape_runs)
  AND a.lesson_title <> b.lesson_title;

-- Trajetoria completa de uma aula ao longo das raspagens.
SELECT
    s.run_id,
    r.scraped_at,
    s.lesson_title,
    s.group_title,
    s.position_global
FROM lesson_snapshots s
JOIN scrape_runs r USING (run_id)
WHERE s.lesson_uid = 'lsn_3521413'
ORDER BY s.run_id;

-- Como o catalogo cresceu.
SELECT
    r.run_id,
    r.scraped_at,
    r.n_courses,
    r.n_lessons,
    r.n_lessons_new,
    r.n_lessons_gone
FROM scrape_runs r
ORDER BY r.run_id;


-- ===========================================================================
-- PARA O RAG
-- ===========================================================================

-- A tabela que alimenta o chunking. lesson_uid vira o prefixo do chunk id:
-- lsn_3521413::0007
SELECT
    lesson_uid,
    course_title,
    group_title,
    lesson_title,
    lesson_url,
    instructor,
    year,
    subject,
    topics,
    path,
    word_count
FROM v_corpus
WHERE status = 'ok'
ORDER BY course_title, position_global;

-- Aulas ainda sem enriquecimento (assunto/topicos) — entrada do passo de LLM.
SELECT l.lesson_uid, l.lesson_title, t.path_raw, t.word_count
FROM lessons l
JOIN transcripts t USING (lesson_uid)
WHERE l.subject IS NULL
ORDER BY t.word_count DESC;
