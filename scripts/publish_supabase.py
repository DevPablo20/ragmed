#!/usr/bin/env python3
"""Publica o corpus do RAG no Supabase (producao).

    python scripts/publish_supabase.py            # publica
    python scripts/publish_supabase.py --dry-run  # so conta o que iria

O DuckDB local continua sendo a fonte da verdade. Este script substitui o
conteudo das tabelas rag_* inteiro, numa transacao so: ou o corpus novo entra
completo, ou o antigo fica intacto. Com ~6,5 mil trechos isso leva segundos, e
substituir tudo e mais simples e mais seguro do que calcular diferencas — a
atualizacao acontece 3 vezes por ano.

O que sobe: as aulas de v_rag_corpus (curadoria aplicada) e os chunks da
estrategia fixed, a vencedora da Etapa 6. Nada de embeddings: a busca de
producao e BM25 em SQL sobre um indice invertido (ver supabase/migrations/),
que dispensa GPU no servidor.

Precisa de SUPABASE_DB_URL no .env (string do Session pooler).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect  # noqa: E402

STRATEGY = "fixed"


def load_corpus(con) -> dict[str, list[tuple]]:
    lessons = con.execute("""
        SELECT lesson_uid, course_uid, lesson_title, lesson_url, instructor, year,
               subject, topics, summary, word_count
        FROM v_rag_corpus ORDER BY lesson_uid
    """).fetchall()
    uids = [r[0] for r in lessons]
    courses = con.execute(f"""
        SELECT course_uid, course_title, course_url FROM courses
        WHERE course_uid IN (SELECT course_uid FROM v_rag_corpus) ORDER BY course_uid
    """).fetchall()
    chunks = con.execute(f"""
        SELECT chunk_uid, lesson_uid, chunk_index, text, context_prefix, word_count
        FROM chunks WHERE strategy = ? AND lesson_uid IN
            ({','.join('?' * len(uids))})
        ORDER BY chunk_uid
    """, [STRATEGY, *uids]).fetchall()
    return {"rag_courses": courses, "rag_lessons": lessons, "rag_chunks": chunks}


COLS = {
    "rag_courses": "course_uid, course_title, course_url",
    "rag_lessons": "lesson_uid, course_uid, lesson_title, lesson_url, instructor, year, "
                   "subject, topics, summary, word_count",
    "rag_chunks": "chunk_uid, lesson_uid, chunk_index, text, context_prefix, word_count",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = connect(read_only=True)
    corpus = load_corpus(con)
    con.close()
    for t, rows in corpus.items():
        print(f"  {t:<12} {len(rows):>6} linhas")
    if args.dry_run:
        return

    import psycopg
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL ausente no .env")

    with psycopg.connect(url, connect_timeout=20) as pg, pg.cursor() as cur:
        # cascade apaga aulas e trechos junto com os cursos; restart identity
        # mantem os ids dos trechos pequenos (sao chave do indice invertido)
        cur.execute("TRUNCATE public.rag_courses RESTART IDENTITY CASCADE")
        for tabela in ("rag_courses", "rag_lessons", "rag_chunks"):
            with cur.copy(f"COPY public.{tabela} ({COLS[tabela]}) FROM STDIN") as cp:
                for row in corpus[tabela]:
                    cp.write_row(row)
        nota = f"{len(corpus['rag_lessons'])} aulas, estrategia {STRATEGY}"
        cur.execute("SELECT public.rag_refresh_stats(%s)", [nota])
        cur.execute("SELECT n_chunks, round(avg_words::numeric, 1), published_at "
                    "FROM public.rag_corpus_stats")
        n, media, quando = cur.fetchone()
        cur.execute("SELECT (SELECT count(*) FROM public.rag_lexemes), "
                    "(SELECT count(*) FROM public.rag_postings)")
        lex, post = cur.fetchone()
    print(f"\npublicado: {n} trechos (media {media} palavras), {lex} lexemas, "
          f"{post} postings, em {quando:%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    main()
