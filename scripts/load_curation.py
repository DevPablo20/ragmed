#!/usr/bin/env python3
"""Aplica as decisoes humanas de curadoria no banco.

    python scripts/load_curation.py

Le data/curation.json e grava:

    lessons.domain_reviewed     veredito sobre o dominio da aula
    transcripts.duplicate_of    aponta para a copia canonica

Nenhuma das duas colunas e tocada pelos loaders do site nem pelo sync, entao o
julgamento sobrevive a re-raspagem e a reprocessamento do perfil. O JSON existe
para que sobreviva tambem a uma reconstrucao do banco do zero.

Faz parte da sequencia de reconstrucao:

    python scripts/db.py
    python scripts/load_snapshot.py data/snapshots/<mais-recente>.json
    python scripts/load_local.py
    python scripts/sync_transcripts.py
    python scripts/profile_corpus.py
    python scripts/load_curation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect, init  # noqa: E402

CURATION = ROOT / "data" / "curation.json"


def main() -> None:
    if not CURATION.exists():
        raise SystemExit(f"{CURATION.relative_to(ROOT)} nao encontrado")
    cur = json.loads(CURATION.read_text(encoding="utf-8"))

    con = connect()
    init(con)

    known = {r[0] for r in con.execute("SELECT lesson_uid FROM lessons").fetchall()}
    faltando = []

    dom = {k: v for k, v in cur.get("domain", {}).items() if not k.startswith("_")}
    for uid, value in dom.items():
        if uid not in known:
            faltando.append(uid)
            continue
        con.execute(
            "UPDATE lessons SET domain_reviewed = ? WHERE lesson_uid = ?", [value, uid]
        )

    con.execute("UPDATE transcripts SET duplicate_of = NULL")
    for d in cur.get("duplicates", []):
        if d["duplicate"] not in known or d["canonical"] not in known:
            faltando.append(d["duplicate"])
            continue
        con.execute(
            "UPDATE transcripts SET duplicate_of = ? WHERE lesson_uid = ?",
            [d["canonical"], d["duplicate"]],
        )

    n_dom, n_dup = con.execute(
        "SELECT (SELECT count(*) FROM lessons WHERE domain_reviewed IS NOT NULL), "
        "       (SELECT count(*) FROM transcripts WHERE duplicate_of IS NOT NULL)"
    ).fetchone()
    print(f"{n_dom} aula(s) com dominio revisado")
    print(f"{n_dup} transcricao(oes) marcada(s) como copia de outra")
    if cur.get("removed"):
        print(f"{len(cur['removed'])} removida(s) do corpus (registro em curation.json)")
    if cur.get("open_questions"):
        print(f"{len(cur['open_questions'])} pergunta(s) em aberto aguardando decisao")
    if faltando:
        print(f"\nATENCAO - uids em curation.json que nao existem em lessons: {faltando}")
    con.close()


if __name__ == "__main__":
    main()
