-- Corpus do RAG em producao: so o que a busca e a citacao precisam.
-- Fonte da verdade continua sendo o DuckDB local; scripts/publish_supabase.py
-- recria o conteudo destas tabelas a cada atualizacao (3x ao ano).
--
-- Por que BM25 em SQL e nao ts_rank
-- ---------------------------------
-- ts_rank nao conhece a raridade de um termo: "dose" e "tratamento", que
-- aparecem em centenas de trechos, pesariam tanto quanto "nandrolona". O BM25
-- pondera por IDF, e foi a busca so-lexical BM25 que acertou a aula em 100% das
-- 25 perguntas no top-5. As estatisticas (df por lexema, N, tamanho medio)
-- ficam em tabelas recalculadas na publicacao, e a funcao buscar_trechos aplica
-- a formula sobre os candidatos que o indice GIN devolve.

create extension if not exists unaccent with schema extensions;

-- Portugues sem acento: a transcricao automatica erra acentos ("hipotenção",
-- "progestional") com frequencia, e a pergunta digitada tambem.
do $$
begin
  if not exists (select 1 from pg_ts_config where cfgname = 'pt_unaccent') then
    create text search configuration public.pt_unaccent (copy = pg_catalog.portuguese);
    alter text search configuration public.pt_unaccent
      alter mapping for hword, hword_part, word with extensions.unaccent, portuguese_stem;
  end if;
end $$;

create table if not exists public.rag_courses (
  course_uid    text primary key,
  course_title  text not null,
  course_url    text
);

create table if not exists public.rag_lessons (
  lesson_uid    text primary key,
  course_uid    text not null references public.rag_courses on delete cascade,
  lesson_title  text not null,
  lesson_url    text,
  instructor    text,
  year          int,
  subject       text,
  topics        text[],
  summary       text,
  word_count    int
);

create table if not exists public.rag_chunks (
  chunk_uid       text primary key,             -- lsn_X::fixed::0007
  lesson_uid      text not null references public.rag_lessons on delete cascade,
  chunk_index     int  not null,
  text            text not null,
  context_prefix  text,
  word_count      int  not null,
  -- Mesmo texto que o indice BM25 local: prefixo + trecho (a configuracao
  -- vencedora da Etapa 6 indexa com prefixo).
  fts tsvector generated always as
      (to_tsvector('public.pt_unaccent', coalesce(context_prefix, '') || ' ' || text)) stored
);
create index if not exists rag_chunks_fts_idx on public.rag_chunks using gin (fts);
create index if not exists rag_chunks_lesson_idx on public.rag_chunks (lesson_uid, chunk_index);

create table if not exists public.rag_lexeme_df (
  lexeme  text primary key,
  df      int not null
);

create table if not exists public.rag_corpus_stats (
  id            int primary key default 1 check (id = 1),
  n_chunks      int not null,
  avg_words     double precision not null,
  published_at  timestamptz not null,
  source_note   text
);

-- Nada disto e publico. RLS ligado e sem policy: anon e authenticated nao leem;
-- so a Edge Function, com a chave de servico, acessa.
alter table public.rag_courses      enable row level security;
alter table public.rag_lessons      enable row level security;
alter table public.rag_chunks       enable row level security;
alter table public.rag_lexeme_df    enable row level security;
alter table public.rag_corpus_stats enable row level security;

-- Recalcula as estatisticas do BM25. Chamada pelo publish_supabase.py.
create or replace function public.rag_refresh_stats(note text default null)
returns void language sql as $$
  truncate public.rag_lexeme_df;
  insert into public.rag_lexeme_df (lexeme, df)
    select word, ndoc from ts_stat('select fts from public.rag_chunks');
  insert into public.rag_corpus_stats (id, n_chunks, avg_words, published_at, source_note)
    select 1, count(*), avg(word_count), now(), note from public.rag_chunks
  on conflict (id) do update set n_chunks = excluded.n_chunks,
    avg_words = excluded.avg_words, published_at = excluded.published_at,
    source_note = excluded.source_note;
$$;

-- Busca BM25 (k1=1.5, b=0.75, os padroes do bm25s usado localmente).
-- A pergunta vira um OR de lexemas: AND exigiria que o trecho contivesse todas
-- as palavras da pergunta, o que numa fala transcrita quase nunca acontece.
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
  q as (
    select distinct u.lexeme
    from unnest(to_tsvector('public.pt_unaccent', pergunta)) u
  ),
  qry as (
    select nullif(string_agg(quote_literal(lexeme), ' | '), '')::tsquery as tsq from q
  ),
  st as (select n_chunks, avg_words from public.rag_corpus_stats where id = 1),
  cand as (
    select c.chunk_uid, c.fts, c.word_count
    from public.rag_chunks c
    join public.rag_lessons l using (lesson_uid)
    join public.rag_courses co using (course_uid)
    , qry
    where c.fts @@ qry.tsq
      and (curso is null
           or extensions.unaccent(co.course_title) ilike '%' || extensions.unaccent(curso) || '%')
  ),
  scored as (
    select cand.chunk_uid,
           sum(
             ln(1 + (st.n_chunks - d.df + 0.5) / (d.df + 0.5))
             * (tf * 2.5) / (tf + 1.5 * (0.25 + 0.75 * cand.word_count / st.avg_words))
           ) as score
    from cand
    cross join st
    cross join lateral (
      select u.lexeme, coalesce(array_length(u.positions, 1), 1) as tf
      from unnest(cand.fts) u
      where u.lexeme in (select lexeme from q)
    ) t
    join public.rag_lexeme_df d on d.lexeme = t.lexeme
    group by cand.chunk_uid
    order by score desc
    limit greatest(1, least(k, 50))
  )
  select (row_number() over (order by s.score desc))::int, s.score,
         c.chunk_uid, c.lesson_uid, c.chunk_index, l.lesson_title,
         co.course_title, l.lesson_url, l.instructor, c.text
  from scored s
  join public.rag_chunks c using (chunk_uid)
  join public.rag_lessons l using (lesson_uid)
  join public.rag_courses co using (course_uid)
  order by s.score desc;
$$;

-- Trechos vizinhos de um chunk: quando a resposta comeca no fim de um trecho e
-- continua no seguinte, o modelo pede o contexto em volta.
create or replace function public.ler_contexto(p_chunk_uid text, janela int default 1)
returns table (chunk_uid text, chunk_index int, lesson_title text, lesson_url text, text text)
language sql stable as $$
  select c.chunk_uid, c.chunk_index, l.lesson_title, l.lesson_url, c.text
  from public.rag_chunks alvo
  join public.rag_chunks c on c.lesson_uid = alvo.lesson_uid
   and c.chunk_index between alvo.chunk_index - least(janela, 3)
                         and alvo.chunk_index + least(janela, 3)
  join public.rag_lessons l on l.lesson_uid = c.lesson_uid
  where alvo.chunk_uid = p_chunk_uid
  order by c.chunk_index;
$$;

-- So a chave de servico (Edge Function) executa.
revoke execute on function public.buscar_trechos(text, int, text) from public, anon, authenticated;
revoke execute on function public.ler_contexto(text, int)         from public, anon, authenticated;
revoke execute on function public.rag_refresh_stats(text)         from public, anon, authenticated;
