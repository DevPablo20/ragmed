#!/usr/bin/env python3
"""Constroi os dois indices de recuperacao para uma estrategia de chunking.

    python scripts/build_index.py                     # estrategia fixed
    python scripts/build_index.py --strategy semantic

Dois indices, porque eles erram de formas diferentes
----------------------------------------------------
  denso (bge-m3)  acha parafrase: a pergunta "como repor testosterona" alcanca
                  um trecho que fala em "reposicao do hormonio masculino".
                  Erra em termo raro e em numero — o embedding dilui ambos.

  BM25            acha termo exato e raro: um nome de farmaco, uma dosagem,
                  uma sigla. Erra em parafrase — nao sabe que dois termos
                  diferentes significam a mesma coisa.

Um corpus de fala medica precisa dos dois: o clinico pergunta ora por conceito,
ora por nome de substancia. A fusao acontece em search.py.

Sobre nao usar vector store
---------------------------
Os vetores ficam em chunk_embeddings, no proprio DuckDB, e a busca e forca bruta
com array_cosine_similarity. Com ~7 mil chunks isso responde em milissegundos.
Um indice HNSW so passaria a compensar uma ordem de grandeza acima disso, e no
DuckDB a persistencia dele ainda e experimental — seria mais peca movel sem ganho.

O texto indexado inclui o prefixo contextual (curso/aula/assunto). E o que faz um
trecho que diz apenas "a dose costuma ser de 100 a 200" continuar recuperavel por
uma pergunta sobre testosterona. Com --no-context os indices sao montados so com
o texto (tabela chunk_embeddings_noctx, indexes/bm25_<estrategia>_noctx), para
a Etapa 6 medir se o prefixo ajuda ou atrapalha.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect, init  # noqa: E402

EMBED_MODEL = "BAAI/bge-m3"
INDEX_DIR = ROOT / "indexes"


def embeddings_table(context: bool) -> str:
    return "chunk_embeddings" if context else "chunk_embeddings_noctx"


def bm25_dirname(strategy: str, context: bool) -> str:
    return f"bm25_{strategy}" if context else f"bm25_{strategy}_noctx"


def load_chunks(con, strategy: str, context: bool = True) -> list[dict]:
    col = "text_with_context" if context else "text"
    rows = con.execute(
        f"SELECT chunk_uid, {col} AS doc FROM v_chunk_corpus WHERE strategy = ? "
        "ORDER BY chunk_uid", [strategy]
    ).df().to_dict("records")
    if not rows:
        raise SystemExit(f"nenhum chunk com strategy='{strategy}' - rode build_chunks.py")
    return rows


def build_dense(con, rows: list[dict], strategy: str, context: bool = True) -> None:
    from sentence_transformers import SentenceTransformer
    import torch

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cpu":
        print("  AVISO: sem CUDA - embedding vai levar dezenas de minutos")
    print(f"  carregando {EMBED_MODEL} em {dev}...")
    model = SentenceTransformer(EMBED_MODEL, device=dev)

    textos = [r["doc"] for r in rows]
    print(f"  embeddando {len(textos)} chunks...")
    vecs = model.encode(textos, normalize_embeddings=True, batch_size=32,
                        show_progress_bar=True, convert_to_numpy=True)

    now = datetime.now()
    uids = [r["chunk_uid"] for r in rows]
    tabela = embeddings_table(context)
    con.execute(
        f"DELETE FROM {tabela} WHERE chunk_uid IN "
        "(SELECT chunk_uid FROM chunks WHERE strategy = ?)", [strategy]
    )
    con.executemany(
        f"INSERT INTO {tabela} (chunk_uid, embedding, model, created_at) "
        "VALUES (?, ?, ?, ?)",
        [[u, v.tolist(), EMBED_MODEL, now] for u, v in zip(uids, vecs)],
    )
    print(f"  {len(uids)} vetores de {vecs.shape[1]} dimensoes gravados")


def build_bm25(rows: list[dict], strategy: str, context: bool = True) -> None:
    import bm25s

    dest = INDEX_DIR / bm25_dirname(strategy, context)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    corpus = [r["doc"] for r in rows]
    # stopwords em portugues: sem isso "de", "que", "para" dominam o score
    tokens = bm25s.tokenize(corpus, stopwords="pt", show_progress=False)
    retriever = bm25s.BM25()
    retriever.index(tokens, show_progress=False)
    retriever.save(str(dest))

    # A lista de uids fica ao lado, na mesma ordem em que o corpus foi indexado.
    # Guardar por fora em vez de usar o corpus embutido do bm25s: ele atribui um
    # id inteiro proprio a cada documento, e depender desse formato interno ja
    # custou um bug aqui. Indice -> uid e mapeamento nosso, explicito.
    import json
    (dest / "chunk_uids.json").write_text(
        json.dumps([r["chunk_uid"] for r in rows]), encoding="utf-8"
    )
    print(f"  indice BM25 em {dest.relative_to(ROOT)} ({len(rows)} documentos)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="fixed",
                    choices=["fixed", "semantic", "qa_turn"])
    ap.add_argument("--skip-dense", action="store_true")
    ap.add_argument("--skip-bm25", action="store_true")
    ap.add_argument("--no-context", action="store_true",
                    help="indexa so o texto, sem o prefixo curso/aula")
    args = ap.parse_args()

    con = connect()
    init(con)
    ctx = not args.no_context
    rows = load_chunks(con, args.strategy, ctx)
    print(f"estrategia {args.strategy} ({'com' if ctx else 'sem'} prefixo): "
          f"{len(rows)} chunks")

    if not args.skip_bm25:
        print("\nBM25:")
        build_bm25(rows, args.strategy, ctx)
    if not args.skip_dense:
        print("\ndenso:")
        build_dense(con, rows, args.strategy, ctx)

    n = con.execute(
        f"SELECT count(*) FROM {embeddings_table(ctx)} e JOIN chunks c USING (chunk_uid) "
        "WHERE c.strategy = ?", [args.strategy]
    ).fetchone()[0]
    print(f"\nindice pronto: {n} chunks com vetor")
    con.close()


if __name__ == "__main__":
    main()
