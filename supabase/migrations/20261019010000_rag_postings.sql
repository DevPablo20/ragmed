-- Indice invertido para o BM25: termo -> trechos onde aparece, com frequencia.
--
-- A primeira versao de buscar_trechos abria o tsvector de cada candidato para
-- achar a frequencia dos termos. Numa pergunta comum, lexemas como "pod" (poder)
-- e "ser" aparecem em ~5.800 dos 6.556 trechos, e a busca levava 4,3 s dentro do
-- banco. Com as postings pre-calculadas na publicacao, pontuar vira uma juncao
-- por chave sobre poucos milhares de linhas.
--
-- Ids inteiros em vez de chunk_uid/lexema em texto: a tabela tem ~1 milhao de
-- linhas, e a chave em texto quase triplicaria o espaco no plano gratuito.

drop function if exists public.buscar_trechos(text, int, text);
drop table if exists public.rag_lexeme_df;

alter table public.rag_chunks
  add column if not exists id int generated always as identity;
create unique index if not exists rag_chunks_id_idx on public.rag_chunks (id);

create table if not exists public.rag_lexemes (
  id      int generated always as identity primary key,
  lexeme  text not null unique,
  df      int  not null
);

create table if not exists public.rag_postings (
  lexeme_id  int      not null,
  chunk_id   int      not null,
  tf         smallint not null,
  primary key (lexeme_id, chunk_id)
);

alter table public.rag_lexemes  enable row level security;
alter table public.rag_postings enable row level security;

create or replace function public.rag_refresh_stats(note text default null)
returns void language sql as $$
  truncate public.rag_postings;
  truncate public.rag_lexemes restart identity;
  insert into public.rag_lexemes (lexeme, df)
    select word, ndoc from ts_stat('select fts from public.rag_chunks');
  insert into public.rag_postings (lexeme_id, chunk_id, tf)
    select lx.id, c.id, coalesce(array_length(u.positions, 1), 1)
    from public.rag_chunks c
    cross join lateral unnest(c.fts) u
    join public.rag_lexemes lx on lx.lexeme = u.lexeme;
  insert into public.rag_corpus_stats (id, n_chunks, avg_words, published_at, source_note)
    select 1, count(*), avg(word_count), now(), note from public.rag_chunks
  on conflict (id) do update set n_chunks = excluded.n_chunks,
    avg_words = excluded.avg_words, published_at = excluded.published_at,
    source_note = excluded.source_note;
  analyze public.rag_postings;
  analyze public.rag_lexemes;
$$;

-- BM25 (k1=1.5, b=0.75, idf de Lucene — os padroes do bm25s usado localmente).
-- A pergunta vira um OR de lexemas: exigir todos (AND) quase nunca casa numa
-- fala transcrita.
create or replace function public.buscar_trechos(
  pergunta text,
  k        int  default 15,
  curso    text default null
)
returns table (
  rank int, score double precision, chunk_uid text, lesson_uid text,
  chunk_index int, lesson_title text, course_title text, lesson_url text,
  instructor text, text text
)
language sql stable as $$
  with
  st as (select n_chunks, avg_words from public.rag_corpus_stats where id = 1),
  q as (
    select lx.id, ln(1 + (st.n_chunks - lx.df + 0.5) / (lx.df + 0.5)) as idf
    from (select distinct lexeme from unnest(to_tsvector('public.pt_unaccent', pergunta))) t
    join public.rag_lexemes lx using (lexeme)
    cross join st
  ),
  scored as (
    select p.chunk_id,
           sum(q.idf * (p.tf * 2.5)
               / (p.tf + 1.5 * (0.25 + 0.75 * c.word_count / st.avg_words))) as score
    from q
    join public.rag_postings p on p.lexeme_id = q.id
    join public.rag_chunks c on c.id = p.chunk_id
    cross join st
    where curso is null or c.lesson_uid in (
      select l.lesson_uid from public.rag_lessons l
      join public.rag_courses co using (course_uid)
      where extensions.unaccent(co.course_title) ilike '%' || extensions.unaccent(curso) || '%')
    group by p.chunk_id
    order by score desc
    limit greatest(1, least(k, 50))
  )
  select (row_number() over (order by s.score desc))::int, s.score,
         c.chunk_uid, c.lesson_uid, c.chunk_index, l.lesson_title,
         co.course_title, l.lesson_url, l.instructor, c.text
  from scored s
  join public.rag_chunks c on c.id = s.chunk_id
  join public.rag_lessons l using (lesson_uid)
  join public.rag_courses co using (course_uid)
  order by s.score desc;
$$;

revoke execute on function public.buscar_trechos(text, int, text) from public, anon, authenticated;
revoke execute on function public.rag_refresh_stats(text)         from public, anon, authenticated;
