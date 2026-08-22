#!/usr/bin/env python3
"""Ingere um snapshot do site no ragmed.duckdb, preservando historico.

    python scripts/load_snapshot.py data/snapshots/20260822T120000.json

Formato do snapshot (produzido por scripts/scrape_snippet.js):

    {
      "scraped_at": "2026-08-22T12:00:00",
      "source": "https://ead.avantgardecollege.com.br/area/vitrine/home",
      "courses": [
        {"site_course_id": "252705", "course_title": "...", "course_url": "...",
         "course_kind": "produto", "position_in_vitrine": 25,
         "groups": [{"site_group_id": "710983", "group_title": "Oncologia",
                     "group_index": 1,
                     "lessons": [{"site_lesson_id": "3521413",
                                  "lesson_title": "...", "lesson_url": "...",
                                  "position_in_group": 1}]}]}
      ]
    }

Regras:
  - Nada e deletado. Curso/aula que nao aparece no snapshot vira is_active=false,
    e last_seen_at continua marcando quando foi visto pela ultima vez.
  - O que reaparece depois volta a is_active=true, mantendo o first_seen original.
  - A tabela transcripts nunca e tocada aqui.
  - instructor usa COALESCE(novo_do_site, existente): ha instrutores que so
    aparecem no nome do arquivo local, e um re-scrape nao pode apaga-los.

Tudo roda numa transacao: ou a execucao entra inteira, ou nao entra.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect, course_uid, init, lesson_uid  # noqa: E402

LIST_LIMIT = 15  # quantas novidades listar antes de resumir

_INSTRUCTOR_RE = re.compile(
    r"(Dra?\.?\s+[A-ZÀ-Ý][\wÀ-ÿ]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ]+)*"
    r"|[A-ZÀ-Ý][\wÀ-ÿ]+\s+[A-ZÀ-Ý][\wÀ-ÿ]+)$"
)
_NOT_A_NAME = {
    "Metabolismo Humano", "Base Alimentar", "Ganho de Massa", "Blue Zones",
    "Saude Digestiva", "Grande Debate", "Cadeia Esteroidal",
}


def instructor_from_title(title: str) -> str | None:
    for sep in ("|", " - ", " – "):
        if sep in title:
            tail = title.rsplit(sep, 1)[1].strip()
            if _INSTRUCTOR_RE.match(tail) and tail not in _NOT_A_NAME and len(tail) > 4:
                return tail
    return None


def year_from(*sources: str | None) -> int | None:
    for s in sources:
        if s and (m := re.search(r"\b(20[12]\d)\b", s)):
            return int(m.group(1))
    return None


def flatten(snapshot: dict) -> tuple[list[dict], list[dict]]:
    """Snapshot aninhado -> linhas planas de curso e de aula."""
    courses, lessons = [], []
    for c in snapshot["courses"]:
        cuid = course_uid(c["site_course_id"])
        groups = c.get("groups", [])
        position_global = 0
        for g in groups:
            for l in g.get("lessons", []):
                position_global += 1
                title = l["lesson_title"]
                lessons.append(
                    {
                        "lesson_uid": lesson_uid(l["site_lesson_id"]),
                        "course_uid": cuid,
                        "site_lesson_id": l["site_lesson_id"],
                        "lesson_title": title,
                        "lesson_url": l.get("lesson_url"),
                        "site_group_id": g.get("site_group_id"),
                        "group_title": g.get("group_title"),
                        "group_index": g.get("group_index"),
                        "position_in_group": l.get("position_in_group"),
                        "position_global": position_global,
                        "instructor": instructor_from_title(title),
                        "year": year_from(g.get("group_title"), c["course_title"]),
                    }
                )
        courses.append(
            {
                "course_uid": cuid,
                "site_course_id": c["site_course_id"],
                "course_title": c["course_title"],
                "course_url": c.get("course_url"),
                "course_kind": c.get("course_kind"),
                "position_in_vitrine": c.get("position_in_vitrine"),
                "group_count": len(groups),
                "lesson_count": position_global,
            }
        )
    return courses, lessons


def load(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    scraped_at = datetime.fromisoformat(snapshot["scraped_at"])
    courses, lessons = flatten(snapshot)

    con.execute("BEGIN TRANSACTION")
    try:
        run_id = con.execute(
            "INSERT INTO scrape_runs (scraped_at, loaded_at, snapshot_path, "
            "n_courses, n_lessons) VALUES (?, now(), ?, ?, ?) RETURNING run_id",
            [scraped_at, str(path.relative_to(ROOT)), len(courses), len(lessons)],
        ).fetchone()[0]

        con.execute("CREATE OR REPLACE TEMP TABLE stg_courses AS SELECT * FROM courses LIMIT 0")
        con.execute("CREATE OR REPLACE TEMP TABLE stg_lessons AS SELECT * FROM lessons LIMIT 0")
        con.executemany(
            "INSERT INTO stg_courses (course_uid, origin, site_course_id, course_title, "
            "course_url, course_kind, position_in_vitrine, group_count, lesson_count, "
            "first_seen_at, first_seen_run_id, last_seen_at, last_seen_run_id, is_active) "
            "VALUES (?, 'site', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)",
            [
                [c["course_uid"], c["site_course_id"], c["course_title"], c["course_url"],
                 c["course_kind"], c["position_in_vitrine"], c["group_count"],
                 c["lesson_count"], scraped_at, run_id, scraped_at, run_id]
                for c in courses
            ],
        )
        con.executemany(
            "INSERT INTO stg_lessons (lesson_uid, course_uid, origin, site_lesson_id, lesson_title, "
            "lesson_url, site_group_id, group_title, group_index, position_in_group, "
            "position_global, instructor, instructor_source, year, "
            "first_seen_at, first_seen_run_id, last_seen_at, last_seen_run_id, is_active) "
            "VALUES (?, ?, 'site', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'site_title', ?, ?, ?, ?, ?, TRUE)",
            [
                [l["lesson_uid"], l["course_uid"], l["site_lesson_id"], l["lesson_title"],
                 l["lesson_url"], l["site_group_id"], l["group_title"], l["group_index"],
                 l["position_in_group"], l["position_global"], l["instructor"], l["year"],
                 scraped_at, run_id, scraped_at, run_id]
                for l in lessons
            ],
        )

        # Contagem do delta antes do upsert, enquanto ainda da para distinguir.
        n_courses_new = con.execute(
            "SELECT count(*) FROM stg_courses s "
            "WHERE NOT EXISTS (SELECT 1 FROM courses c WHERE c.course_uid = s.course_uid)"
        ).fetchone()[0]
        n_lessons_new = con.execute(
            "SELECT count(*) FROM stg_lessons s "
            "WHERE NOT EXISTS (SELECT 1 FROM lessons l WHERE l.lesson_uid = s.lesson_uid)"
        ).fetchone()[0]
        # origin='local' nunca esteve na vitrine, entao nao conta como "sumiu".
        n_courses_gone = con.execute(
            "SELECT count(*) FROM courses c WHERE c.is_active AND c.origin = 'site' "
            "AND NOT EXISTS (SELECT 1 FROM stg_courses s WHERE s.course_uid = c.course_uid)"
        ).fetchone()[0]
        n_lessons_gone = con.execute(
            "SELECT count(*) FROM lessons l WHERE l.is_active AND l.origin = 'site' "
            "AND NOT EXISTS (SELECT 1 FROM stg_lessons s WHERE s.lesson_uid = l.lesson_uid)"
        ).fetchone()[0]

        # raw_folder e first_seen_* pertencem ao passado: nunca sao sobrescritos.
        con.execute("""
            INSERT INTO courses SELECT * FROM stg_courses
            ON CONFLICT (course_uid) DO UPDATE SET
                course_title        = excluded.course_title,
                course_url          = excluded.course_url,
                course_kind         = excluded.course_kind,
                position_in_vitrine = excluded.position_in_vitrine,
                group_count         = excluded.group_count,
                lesson_count        = excluded.lesson_count,
                last_seen_at        = excluded.last_seen_at,
                last_seen_run_id    = excluded.last_seen_run_id,
                is_active           = TRUE
        """)
        con.execute("""
            INSERT INTO lessons SELECT * FROM stg_lessons
            ON CONFLICT (lesson_uid) DO UPDATE SET
                course_uid        = excluded.course_uid,
                lesson_title      = excluded.lesson_title,
                lesson_url        = excluded.lesson_url,
                site_group_id     = excluded.site_group_id,
                group_title       = excluded.group_title,
                group_index       = excluded.group_index,
                position_in_group = excluded.position_in_group,
                position_global   = excluded.position_global,
                -- instrutor vindo do nome do arquivo nao pode ser apagado pelo site
                instructor        = COALESCE(excluded.instructor, lessons.instructor),
                instructor_source = CASE
                                        WHEN excluded.instructor IS NOT NULL THEN 'site_title'
                                        ELSE lessons.instructor_source
                                    END,
                year              = COALESCE(excluded.year, lessons.year),
                last_seen_at      = excluded.last_seen_at,
                last_seen_run_id  = excluded.last_seen_run_id,
                is_active         = TRUE
        """)

        # Some do site -> inativo, mas continua no banco com o last_seen antigo.
        con.execute(
            "UPDATE courses SET is_active = FALSE WHERE is_active AND origin = 'site' "
            "AND course_uid NOT IN (SELECT course_uid FROM stg_courses)"
        )
        con.execute(
            "UPDATE lessons SET is_active = FALSE WHERE is_active AND origin = 'site' "
            "AND lesson_uid NOT IN (SELECT lesson_uid FROM stg_lessons)"
        )

        con.execute(
            "INSERT INTO course_snapshots SELECT ?, course_uid, course_title, "
            "position_in_vitrine, lesson_count FROM stg_courses",
            [run_id],
        )
        con.execute(
            "INSERT INTO lesson_snapshots SELECT ?, lesson_uid, course_uid, lesson_title, "
            "group_title, group_index, position_in_group, position_global FROM stg_lessons",
            [run_id],
        )

        con.execute(
            "UPDATE scrape_runs SET n_courses_new = ?, n_lessons_new = ?, "
            "n_courses_gone = ?, n_lessons_gone = ? WHERE run_id = ?",
            [n_courses_new, n_lessons_new, n_courses_gone, n_lessons_gone, run_id],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return run_id


def report(con: duckdb.DuckDBPyConnection, run_id: int) -> None:
    row = con.execute(
        "SELECT scraped_at, n_courses, n_lessons, n_courses_new, n_lessons_new, "
        "n_courses_gone, n_lessons_gone FROM scrape_runs WHERE run_id = ?", [run_id]
    ).fetchone()
    scraped_at, nc, nl, ncn, nln, ncg, nlg = row
    print(f"\nexecucao {run_id}  ({scraped_at:%Y-%m-%d %H:%M})")
    print(f"  {nc} cursos, {nl} aulas no site")
    print(f"  novos: {ncn} curso(s), {nln} aula(s)")
    print(f"  sairam do ar: {ncg} curso(s), {nlg} aula(s)")

    prev = con.execute(
        "SELECT max(run_id) FROM scrape_runs WHERE run_id < ?", [run_id]
    ).fetchone()[0]
    if prev:
        renamed = con.execute("""
            SELECT a.lesson_uid, b.lesson_title, a.lesson_title
            FROM lesson_snapshots a JOIN lesson_snapshots b USING (lesson_uid)
            WHERE a.run_id = ? AND b.run_id = ? AND a.lesson_title <> b.lesson_title
        """, [run_id, prev]).fetchall()
        if renamed:
            print(f"  titulos alterados desde a execucao {prev}: {len(renamed)}")
            for uid, old, new in renamed[:10]:
                print(f"    {uid}  {old!r} -> {new!r}")

    if nln:
        # Na primeira execucao tudo e novo; listar 226 aulas nao ajuda ninguem.
        rows = con.execute("SELECT * FROM v_new_lessons").fetchall()
        shown = rows if len(rows) <= LIST_LIMIT else rows[:LIST_LIMIT]
        print("\naulas novas:")
        for uid, course, title, url, *_ in shown:
            print(f"  {uid}  {course} / {title}\n      {url}")
        if len(rows) > len(shown):
            print(f"  ... e mais {len(rows) - len(shown)}  (SELECT * FROM v_new_lessons)")
    if nlg:
        print("\naulas que sairam do ar nesta execucao:")
        for uid, course, title, seen, *_ in con.execute(
            "SELECT * FROM v_removed_from_site WHERE last_seen_run_id = ?", [prev or run_id]
        ).fetchall():
            print(f"  {uid}  {course} / {title}   (visto ate {seen:%Y-%m-%d})")

    pend = con.execute("SELECT count(*) FROM v_pending_downloads").fetchone()[0]
    print(f"\naguardando transcricao: {pend}  (SELECT * FROM v_pending_downloads)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot", type=Path)
    args = ap.parse_args()
    if not args.snapshot.exists():
        raise SystemExit(f"snapshot nao encontrado: {args.snapshot}")

    con = connect()
    init(con)
    run_id = load(con, args.snapshot.resolve())
    report(con, run_id)
    con.close()


if __name__ == "__main__":
    main()
