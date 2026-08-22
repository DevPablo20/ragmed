#!/usr/bin/env python3
"""Sincroniza transcripts/*.txt com a tabela transcripts do banco.

    python scripts/sync_transcripts.py            # aplica
    python scripts/sync_transcripts.py --check    # so relata

O arquivo se chama pelo identificador da aula:

    transcripts/lsn_7773605.txt

Isso e o que substitui o casamento difuso entre nome de arquivo e titulo de
aula que existia antes: nao ha mais nada para adivinhar. Para registrar uma
aula nova, veja o uid em v_pending_downloads, grave o texto com esse nome e
rode este script.

O script recalcula md5 e contagens, faz upsert do que mudou, remove do banco
o que sumiu do disco, e avisa sobre arquivos cujo uid nao existe em lessons.
Nunca escreve em courses nem lessons - quem manda no catalogo e o loader.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, TRANSCRIPT_DIR, connect, init  # noqa: E402


def measure(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return {
        "md5": hashlib.md5(raw).hexdigest(),
        "char_count": len(text),
        "word_count": len(text.split()),
        "est_tokens": round(len(text) / 4),
        "file_size_bytes": len(raw),
        "lang": "pt-BR",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="so relata, nao escreve")
    args = ap.parse_args()

    con = connect()
    init(con)

    known = {r[0] for r in con.execute("SELECT lesson_uid FROM lessons").fetchall()}
    stored = {
        r[0]: r[1] for r in con.execute("SELECT lesson_uid, md5 FROM transcripts").fetchall()
    }

    on_disk, orphan_files = {}, []
    for path in sorted(TRANSCRIPT_DIR.glob("*.txt")):
        if path.stem in known:
            on_disk[path.stem] = path
        else:
            orphan_files.append(path)

    added, changed, unchanged = [], [], 0
    for uid, path in on_disk.items():
        m = measure(path)
        if uid not in stored:
            added.append((uid, path, m))
        elif stored[uid] != m["md5"]:
            changed.append((uid, path, m))
        else:
            unchanged += 1

    removed = sorted(set(stored) - set(on_disk))

    print(f"{len(on_disk)} arquivo(s) em {TRANSCRIPT_DIR.relative_to(ROOT)}/")
    print(f"  inalterados: {unchanged}")
    print(f"  novos:       {len(added)}")
    print(f"  alterados:   {len(changed)}")
    print(f"  sumiram:     {len(removed)}")
    for uid, path, _ in added:
        print(f"    + {uid}")
    for uid, path, _ in changed:
        print(f"    ~ {uid}")
    for uid in removed:
        print(f"    - {uid}")

    if orphan_files:
        print(f"\n{len(orphan_files)} arquivo(s) sem aula correspondente em lessons:")
        for p in orphan_files:
            print(f"    ? {p.name}")
        print("  O nome do arquivo precisa ser um lesson_uid existente.")
        print("  Rode o loader se for aula nova do site, ou confira o nome.")

    if args.check:
        con.close()
        return

    for uid, path, m in added + changed:
        con.execute(
            "INSERT INTO transcripts (lesson_uid, path, md5, char_count, word_count, "
            "est_tokens, file_size_bytes, lang, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, now()) "
            "ON CONFLICT (lesson_uid) DO UPDATE SET "
            "  path = excluded.path, md5 = excluded.md5, "
            "  char_count = excluded.char_count, word_count = excluded.word_count, "
            "  est_tokens = excluded.est_tokens, "
            "  file_size_bytes = excluded.file_size_bytes, updated_at = now()",
            [uid, str(path.relative_to(ROOT)), m["md5"], m["char_count"],
             m["word_count"], m["est_tokens"], m["file_size_bytes"], m["lang"]],
        )
    for uid in removed:
        con.execute("DELETE FROM transcripts WHERE lesson_uid = ?", [uid])

    total, pend = con.execute(
        "SELECT (SELECT count(*) FROM transcripts), (SELECT count(*) FROM v_pending_downloads)"
    ).fetchone()
    print(f"\ntranscripts: {total}  |  aguardando transcricao: {pend}")

    # O manifest e um export da view, para quem preferir CSV ao SQL.
    df = con.execute("SELECT * FROM v_corpus").df()
    (ROOT / "data").mkdir(exist_ok=True)
    df.to_csv(ROOT / "data" / "manifest.csv", index=False)
    df.to_parquet(ROOT / "data" / "manifest.parquet", index=False)
    print("data/manifest.csv e data/manifest.parquet atualizados")
    con.close()


if __name__ == "__main__":
    main()
