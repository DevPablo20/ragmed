#!/usr/bin/env python3
"""Busca hibrida sobre o corpus: BM25 + denso, fundidos por RRF, depois rerank.

    python scripts/search.py "qual a dose de testosterona em implante?"
    python scripts/search.py "cortisol e sono" --k 5 --course Cardiologia
    python scripts/search.py "vitamina D" --no-rerank --explain

O pipeline, e por que cada etapa existe
---------------------------------------
    pergunta ─┬─ BM25 (termo exato)  ─┐
              └─ denso (parafrase)   ─┴─ RRF k=60 ─ top 50 ─ rerank ─ top K

RRF (Reciprocal Rank Fusion) funde por POSICAO, nunca por score: um score BM25 e
uma similaridade de cosseno vivem em escalas incomparaveis, e mediar os dois
produz um numero sem significado. RRF so pergunta "em que lugar cada lista pos
este chunk?" — 1/(k + posicao), somado. A constante k=60 amortece o topo, de modo
que o primeiro lugar de uma lista nao atropela sozinho a outra.

O rerank e um cross-encoder: em vez de comparar dois vetores calculados
separadamente, ele le a pergunta e o trecho JUNTOS e pontua a relacao. E bem mais
caro, por isso roda so sobre os 50 candidatos que sobreviveram a fusao — e e onde
a precisao do topo realmente se decide.
"""

from __future__ import annotations

import argparse
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import bm25_dirname, embeddings_table  # noqa: E402
from db import ROOT, connect  # noqa: E402

EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
RRF_K = 60          # amortecimento da fusao; 60 e o valor canonico
CANDIDATE_K = 50    # quantos sobrevivem a fusao e vao para o rerank
TOP_K = 10


@lru_cache(maxsize=2)
def _embedder():
    from sentence_transformers import SentenceTransformer
    import torch
    return SentenceTransformer(EMBED_MODEL,
                               device="cuda" if torch.cuda.is_available() else "cpu")


@lru_cache(maxsize=2)
def _reranker():
    from sentence_transformers import CrossEncoder
    import torch
    return CrossEncoder(RERANK_MODEL,
                        device="cuda" if torch.cuda.is_available() else "cpu",
                        max_length=512)


@lru_cache(maxsize=8)
def _bm25(strategy: str, context: bool = True):
    """(retriever, uids) — o mapeamento indice->uid e nosso, nao do bm25s."""
    import json

    import bm25s
    path = ROOT / "indexes" / bm25_dirname(strategy, context)
    if not path.exists():
        raise SystemExit(f"indice BM25 ausente: {path} - rode build_index.py")
    uids = json.loads((path / "chunk_uids.json").read_text(encoding="utf-8"))
    return bm25s.BM25.load(str(path)), uids


def _allowed(con, strategy: str, course: str | None, subject: str | None,
             instructor: str | None) -> set[str] | None:
    """Pre-filtro por metadado. None = sem filtro (o caso comum).

    Filtrar ANTES da busca, e nao depois, evita o efeito de gastar as 50 vagas
    de candidato com chunks que serao descartados no fim.
    """
    if not any((course, subject, instructor)):
        return None
    sql = "SELECT chunk_uid FROM v_chunk_corpus WHERE strategy = ?"
    params: list = [strategy]
    for campo, valor in (("course_title", course), ("subject", subject),
                         ("instructor", instructor)):
        if valor:
            sql += f" AND lower({campo}) LIKE ?"
            params.append(f"%{valor.lower()}%")
    uids = {r[0] for r in con.execute(sql, params).fetchall()}
    if not uids:
        raise SystemExit("o filtro nao deixou nenhum chunk - revise os criterios")
    return uids


def dense_search(con, query: str, strategy: str, n: int,
                 allowed: set[str] | None, context: bool = True) -> list[str]:
    vec = _embedder().encode([query], normalize_embeddings=True)[0].tolist()
    sql = f"""
        SELECT e.chunk_uid
        FROM {embeddings_table(context)} e JOIN chunks c USING (chunk_uid)
        WHERE c.strategy = ?
        ORDER BY array_cosine_similarity(e.embedding, ?::FLOAT[1024]) DESC
        LIMIT ?
    """
    # Com filtro, pede mais e corta depois: o SQL nao conhece o conjunto allowed.
    limite = n if allowed is None else n * 8
    rows = con.execute(sql, [strategy, vec, limite]).fetchall()
    out = [r[0] for r in rows if allowed is None or r[0] in allowed]
    return out[:n]


def bm25_search(query: str, strategy: str, n: int,
                allowed: set[str] | None, context: bool = True) -> list[str]:
    import bm25s
    retriever, uids = _bm25(strategy, context)
    tokens = bm25s.tokenize([query], stopwords="pt", show_progress=False)
    limite = min(n if allowed is None else n * 8, len(uids))
    idx, _ = retriever.retrieve(tokens, k=limite, show_progress=False)
    achados = [uids[int(i)] for i in idx[0]]
    out = [u for u in achados if allowed is None or u in allowed]
    return out[:n]


def rrf(*rankings: list[str], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: soma 1/(k + posicao) de cada lista."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for pos, uid in enumerate(ranking, start=1):
            score[uid] = score.get(uid, 0.0) + 1.0 / (k + pos)
    return sorted(score.items(), key=lambda kv: -kv[1])


def search(con, query: str, strategy: str = "fixed", top_k: int = TOP_K,
           rerank: bool = True, course: str | None = None,
           subject: str | None = None, instructor: str | None = None,
           explain: bool = False, context: bool = True) -> list[dict]:
    """context=False busca e reranqueia so pelo texto, sem o prefixo curso/aula."""
    allowed = _allowed(con, strategy, course, subject, instructor)

    densos = dense_search(con, query, strategy, CANDIDATE_K, allowed, context)
    lexicais = bm25_search(query, strategy, CANDIDATE_K, allowed, context)
    fundidos = rrf(densos, lexicais)[:CANDIDATE_K]
    if not fundidos:
        return []

    uids = [u for u, _ in fundidos]
    meta = {
        r["chunk_uid"]: r
        for r in con.execute(
            "SELECT * FROM v_chunk_corpus WHERE chunk_uid IN "
            f"({','.join('?' * len(uids))})", uids
        ).df().to_dict("records")
    }

    if rerank:
        campo = "text_with_context" if context else "text"
        pares = [(query, meta[u][campo]) for u in uids]
        scores = _reranker().predict(pares, show_progress_bar=False)
        ordem = sorted(zip(uids, scores), key=lambda kv: -kv[1])[:top_k]
    else:
        ordem = fundidos[:top_k]

    saida = []
    for pos, (uid, score) in enumerate(ordem, start=1):
        m = meta[uid]
        item = {
            "rank": pos, "chunk_uid": uid, "score": float(score),
            "lesson_uid": m["lesson_uid"], "lesson_title": m["lesson_title"],
            "lesson_url": m["lesson_url"], "course_title": m["course_title"],
            "instructor": m["instructor"], "text": m["text"],
        }
        if explain:
            item["pos_denso"] = densos.index(uid) + 1 if uid in densos else None
            item["pos_bm25"] = lexicais.index(uid) + 1 if uid in lexicais else None
        saida.append(item)
    return saida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("--strategy", default="fixed",
                    choices=["fixed", "semantic", "qa_turn"])
    ap.add_argument("-k", "--top-k", type=int, default=TOP_K)
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--course"), ap.add_argument("--subject")
    ap.add_argument("--instructor")
    ap.add_argument("--no-context", action="store_true",
                    help="usa os indices montados sem o prefixo curso/aula")
    ap.add_argument("--explain", action="store_true",
                    help="mostra a posicao em cada lista antes da fusao")
    args = ap.parse_args()

    con = connect(read_only=True)
    hits = search(con, args.query, args.strategy, args.top_k, not args.no_rerank,
                  args.course, args.subject, args.instructor, args.explain,
                  not args.no_context)
    print(f'"{args.query}"  ({args.strategy}, '
          f'{"com" if not args.no_rerank else "sem"} rerank)\n')
    for h in hits:
        origem = ""
        if args.explain:
            d = f"denso#{h['pos_denso']}" if h["pos_denso"] else "denso:—"
            b = f"bm25#{h['pos_bm25']}" if h["pos_bm25"] else "bm25:—"
            origem = f"  [{d} {b}]"
        print(f"{h['rank']:>2}. {h['score']:+.3f}  {h['course_title'][:38]}{origem}")
        print(f"    {h['lesson_title'][:70]}")
        # Mostra o inicio E o fim do chunk. Um recorte so do comeco engana: num
        # chunk de ~366 palavras a informacao procurada costuma estar no meio ou
        # no fim, e ja me levou a descartar como irrelevante um trecho que tinha
        # exatamente a resposta.
        t = h["text"].strip()
        if len(t) <= 620:
            print(f"    {t}")
        else:
            print(f"    {t[:300]}")
            print(f"    [...{len(t) - 600} caracteres...]")
            print(f"    {t[-300:]}")
        print(f"    {h['lesson_url']}\n")
    con.close()


if __name__ == "__main__":
    main()
