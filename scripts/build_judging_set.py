#!/usr/bin/env python3
"""Monta o teste de relevancia que o medico avalia (Etapa 6).

    python scripts/build_judging_set.py                 # perguntas padrao
    python scripts/build_judging_set.py --ids q01,q05   # subconjunto

Por que pooling, e nao "avaliar o top-5 do sistema atual"
---------------------------------------------------------
A pergunta em aberto e COMPARATIVA: o prefixo contextual ajuda ou atrapalha?
Qual estrategia de chunking? O rerank se paga? Se o medico julgar so o top-5 da
configuracao atual, as outras configuracoes trazem trechos que ninguem julgou e
a comparacao fica impossivel. Entao cada configuracao roda, o top-3 de todas e
unido (o "pool", metodo classico do TREC), e o medico julga a uniao uma vez.

Trechos de estrategias diferentes cobrem as mesmas falas com fronteiras
diferentes. Quando dois chunks da mesma aula se sobrepoem em >= 60% do menor,
viram UM trecho na planilha: o medico le uma vez e a nota vale para os dois.

O que o medico ve: so a pergunta e o texto, em ordem embaralhada. Nem posicao,
nem configuracao, nem aula — tudo isso puxaria a nota para concordar com a
maquina. O mapeamento trecho -> chunks fica em data/eval/judging_pool.json.

Saidas
    data/eval/runs.json            top-10 de cada configuracao, por pergunta
    data/eval/judging_pool.json    trecho -> chunks representados
    data/eval/avaliacao_trechos.xlsx   a planilha que vai para o medico
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect  # noqa: E402
from search import search  # noqa: E402

EVAL_DIR = ROOT / "data" / "eval"
POOL_DEPTH = 3       # quantos de cada configuracao entram no pool
RUN_DEPTH = 10       # quantos ficam gravados para as metricas
OVERLAP_MIN = 0.6    # sobreposicao (sobre o menor chunk) para fundir trechos

CONFIGS = {
    "fixed_ctx_rerank":    dict(strategy="fixed",    context=True,  rerank=True),
    "fixed_noctx_rerank":  dict(strategy="fixed",    context=False, rerank=True),
    "semantic_ctx_rerank": dict(strategy="semantic", context=True,  rerank=True),
    "qaturn_ctx_rerank":   dict(strategy="qa_turn",  context=True,  rerank=True),
    "fixed_ctx_norerank":  dict(strategy="fixed",    context=True,  rerank=False),
}

# q02 (implante) fica de fora: e o exemplo resolvido do tutorial. Orcamento:
# ~1 h do medico, ou ~40 trechos de 1-1,5 min. Com top-3 de cada configuracao,
# 7 perguntas cabem nisso. A selecao privilegia as perguntas em que as
# configuracoes DISCORDAM na regua automatica (q06, q15, q20, q25), onde a nota
# do medico mais informa, e cobre os tipos dose, conduta e mecanismo.
DEFAULT_IDS = ["q01", "q03", "q05", "q06", "q15", "q20", "q25"]


def overlap(a: dict, b: dict) -> float:
    if a["lesson_uid"] != b["lesson_uid"]:
        return 0.0
    ini, fim = max(a["char_start"], b["char_start"]), min(a["char_end"], b["char_end"])
    menor = min(a["char_end"] - a["char_start"], b["char_end"] - b["char_start"])
    return max(0, fim - ini) / menor if menor else 0.0


def build_pool(con, uids: list[str]) -> list[dict]:
    """Agrupa chunks sobrepostos; cada grupo vira um trecho para julgar."""
    rows = {
        r["chunk_uid"]: r
        for r in con.execute(
            "SELECT chunk_uid, lesson_uid, char_start, char_end, text FROM chunks "
            f"WHERE chunk_uid IN ({','.join('?' * len(uids))})", uids
        ).df().to_dict("records")
    }
    grupos: list[list[str]] = []
    for u in uids:  # uids chegam em ordem de prioridade: o 1o vira o representante
        for g in grupos:
            if any(overlap(rows[u], rows[m]) >= OVERLAP_MIN for m in g):
                g.append(u)
                break
        else:
            grupos.append([u])
    return [{"rep_chunk_uid": g[0], "member_chunk_uids": g, "text": rows[g[0]]["text"]}
            for g in grupos]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", default=",".join(DEFAULT_IDS))
    ap.add_argument("--seed", type=int, default=20261016)
    args = ap.parse_args()

    perguntas = {q["id"]: q for q in
                 json.loads((EVAL_DIR / "perguntas_treino.json").read_text("utf-8"))}
    ids = args.ids.split(",")
    con = connect(read_only=True)
    rng = random.Random(args.seed)

    # Roda TODAS as perguntas (a regua automatica usa as 25); so as de --ids
    # viram trechos para o medico.
    runs: dict[str, dict] = {c: {} for c in CONFIGS}
    for qid, q in perguntas.items():
        for nome, cfg in CONFIGS.items():
            hits = search(con, q["pergunta"], top_k=RUN_DEPTH, **cfg)
            runs[nome][qid] = [{"chunk_uid": h["chunk_uid"], "score": h["score"],
                                "lesson_uid": h["lesson_uid"]} for h in hits]

    pool_out = []
    for n, qid in enumerate(ids, 1):
        q = perguntas[qid]
        ordem: list[str] = []   # prioridade para escolher representante
        for nome in CONFIGS:
            ordem += [h["chunk_uid"] for h in runs[nome][qid][:POOL_DEPTH]]
        # O trecho-evidencia anotado entra sempre: assim a anotacao tambem e
        # conferida pelo medico, mesmo que nenhuma configuracao o tenha achado.
        ordem += [f"{q['lesson_uid']}::fixed::{i:04d}" for i in q["evidence_chunk_indices"]]
        ordem = list(dict.fromkeys(ordem))
        trechos = build_pool(con, ordem)
        rng.shuffle(trechos)
        for j, t in enumerate(trechos, 1):
            t["excerpt_id"] = f"P{n:02d}-T{j:02d}"
        pool_out.append({"qid": qid, "numero": n, "pergunta": q["pergunta"],
                         "trechos": trechos})
        print(f"  {qid}: {len(ordem)} chunks no pool -> {len(trechos)} trechos")
    con.close()

    total = sum(len(p["trechos"]) for p in pool_out)
    print(f"\n{len(ids)} perguntas, {total} trechos para julgar")

    (EVAL_DIR / "runs.json").write_text(
        json.dumps({"configs": CONFIGS, "runs": runs}, ensure_ascii=False, indent=1), "utf-8")
    (EVAL_DIR / "judging_pool.json").write_text(
        json.dumps([{**p, "trechos": [{k: v for k, v in t.items() if k != "text"}
                                      for t in p["trechos"]]} for p in pool_out],
                   ensure_ascii=False, indent=1), "utf-8")

    from judging_sheet import write_sheet
    write_sheet(pool_out, EVAL_DIR / "avaliacao_trechos.xlsx")
    print(f"planilha em {(EVAL_DIR / 'avaliacao_trechos.xlsx').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
