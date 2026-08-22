#!/usr/bin/env python3
"""Registra no banco as aulas que nunca estiveram na vitrine.

    python scripts/load_local.py

Le data/local_lessons.json. Esse arquivo e a unica fonte da identidade das 21
transcricoes de origem local: elas nao aparecem em nenhum snapshot do site, e
os arquivos se chamam lsn_loc_<hash> - o hash veio do caminho original em raw/,
pasta que nao existe mais. Sem este passo, uma reconstrucao do banco deixaria
esses 21 arquivos orfaos.

E o irmao de load_snapshot.py: um cuida do que veio do site, o outro do que
so existe aqui. Idempotente - rodar de novo nao duplica nem sobrescreve.

Reconstrucao completa do banco, do zero:

    rm ragmed.duckdb
    python scripts/db.py
    python scripts/load_snapshot.py data/snapshots/<mais-recente>.json
    python scripts/load_local.py
    python scripts/sync_transcripts.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect, init  # noqa: E402

REGISTRY = ROOT / "data" / "local_lessons.json"


def main() -> None:
    if not REGISTRY.exists():
        raise SystemExit(f"{REGISTRY.relative_to(ROOT)} nao encontrado")
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))

    con = connect()
    init(con)
    now = datetime.now()

    for c in reg["courses"]:
        con.execute(
            "INSERT INTO courses (course_uid, origin, course_title, group_count, "
            "lesson_count, first_seen_at, last_seen_at, is_active) "
            "VALUES (?, 'local', ?, 1, ?, ?, ?, FALSE) ON CONFLICT DO NOTHING",
            [
                c["course_uid"],
                c["course_title"],
                sum(1 for e in reg["lessons"] if e["course_uid"] == c["course_uid"]),
                now,
                now,
            ],
        )

    for i, e in enumerate(reg["lessons"], start=1):
        con.execute(
            "INSERT INTO lessons (lesson_uid, course_uid, origin, lesson_title, "
            "position_global, first_seen_at, last_seen_at, is_active) "
            "VALUES (?, ?, 'local', ?, ?, ?, ?, FALSE) ON CONFLICT DO NOTHING",
            [e["lesson_uid"], e["course_uid"], e["lesson_title"], i, now, now],
        )
        # source_path so e gravado se a transcricao ja estiver registrada; o
        # sync nao conhece essa procedencia porque ela e anterior a ele.
        con.execute(
            "UPDATE transcripts SET source_path = ?, match_signals = 'origem_local' "
            "WHERE lesson_uid = ? AND source_path IS NULL",
            [e["source_path"], e["lesson_uid"]],
        )

    n_c, n_l = con.execute(
        "SELECT (SELECT count(*) FROM courses WHERE origin = 'local'), "
        "       (SELECT count(*) FROM lessons WHERE origin = 'local')"
    ).fetchone()
    print(f"{n_c} curso(s) e {n_l} aula(s) de origem local no banco")
    con.close()


if __name__ == "__main__":
    main()
