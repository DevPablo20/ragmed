#!/usr/bin/env python3
"""Corta as transcricoes em chunks e grava na tabela chunks.

    python scripts/build_chunks.py                       # estrategia fixed
    python scripts/build_chunks.py --strategy semantic
    python scripts/build_chunks.py --strategy qa_turn
    python scripts/build_chunks.py --all                 # as tres, para comparar

Por que isto e o ponto delicado deste corpus
--------------------------------------------
Cada transcricao e UMA linha corrida de ate 30 mil palavras, com frases de ~7
palavras (e fala, nao texto escrito) e sem paragrafo nenhum. Nao ha fronteira
natural para aproveitar. Cortar por tamanho fixo e o pior caso: todo chunk nasce
partindo um raciocinio ao meio.

As tres estrategias atacam isso de formas diferentes:

  fixed     ~512 tokens com 15% de overlap, encostando a fronteira na ultima
            pontuacao final da janela. E a linha de base — simples e previsivel.

  semantic  agrupa frases e corta onde a similaridade entre grupos vizinhos
            despenca, ou seja, onde o assunto muda. Custa uma passada de
            embedding a mais, mas respeita o conteudo em vez do tamanho.

  qa_turn   usa as interrogacoes como candidatas a fronteira. Sao 177 por aula
            em mediana: cada uma marca uma virada de turno entre quem pergunta
            e quem explica.

Nenhuma e obviamente melhor a priori — por isso as tres coexistem na mesma
tabela, separadas pela coluna `strategy`, e a escolha vira medicao na Etapa 6.

O prefixo contextual
--------------------
Cada chunk carrega um prefixo com curso, aula e assunto. Situar o trecho na aula
melhora muito a recuperacao, e aqui sai de graca: os metadados ja estao no banco,
entao nao ha uma chamada de LLM por chunk. Fica em coluna separada de `text`
justamente para dar para medir o efeito dele.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect, init  # noqa: E402

# ~512 tokens. Em pt-BR falado, uma palavra da cerca de 1,4 token.
TARGET_WORDS = 360
OVERLAP_RATIO = 0.15
# Ao fechar uma janela, procura pontuacao final nos ultimos 20% dela.
SNAP_TAIL = 0.20
# semantic: tamanhos em frases do grupo e limites do chunk resultante
SEM_GROUP = 4
SEM_MIN_WORDS, SEM_MAX_WORDS = 120, 600
# semantic: corta quando a similaridade entre grupos vizinhos cai abaixo do
# percentil escolhido das quedas observadas naquela aula (limiar relativo, nao
# absoluto — cada aula tem seu proprio ritmo de mudanca de assunto).
SEM_PERCENTILE = 25

# Abaixo disto o trecho e muleta de fala solta ("Perfeito.", "Exatamente.") e
# nunca sera uma resposta util — vira ruido no indice.
MIN_WORDS = 50

_SENT = re.compile(r"[^.!?…]+[.!?…]+|\S+$")


def sentences(text: str) -> list[tuple[int, int, str]]:
    """(char_start, char_end, frase). Preserva offsets para rastrear a origem."""
    out = []
    for m in _SENT.finditer(text):
        s = m.group().strip()
        if s:
            out.append((m.start(), m.end(), s))
    return out


def chunk_fixed(text: str) -> list[tuple[int, int]]:
    """Janela de ~TARGET_WORDS palavras com overlap, encostando em pontuacao."""
    sents = sentences(text)
    if not sents:
        return []
    spans, i = [], 0
    while i < len(sents):
        words, j = 0, i
        while j < len(sents) and words < TARGET_WORDS:
            words += len(sents[j][2].split())
            j += 1
        # Recua ate a ultima frase que termina em pontuacao final, dentro da
        # cauda da janela — evita cortar no meio de um raciocinio.
        limite = max(i + 1, int(i + (j - i) * (1 - SNAP_TAIL)))
        for k in range(j - 1, limite - 1, -1):
            if sents[k][2].rstrip()[-1:] in ".!?…":
                j = k + 1
                break
        spans.append((sents[i][0], sents[j - 1][1]))
        if j >= len(sents):
            break
        # Recua o overlap contando palavras de tras para frente.
        back, w = j, 0
        while back > i + 1 and w < TARGET_WORDS * OVERLAP_RATIO:
            back -= 1
            w += len(sents[back][2].split())
        i = back
    return spans


def chunk_semantic(text: str, model) -> list[tuple[int, int]]:
    """Corta onde a similaridade entre grupos de frases vizinhos despenca."""
    import numpy as np

    sents = sentences(text)
    if len(sents) < SEM_GROUP * 2:
        return chunk_fixed(text)

    grupos = [sents[i:i + SEM_GROUP] for i in range(0, len(sents), SEM_GROUP)]
    textos = [" ".join(s[2] for s in g) for g in grupos]
    emb = model.encode(textos, normalize_embeddings=True, show_progress_bar=False,
                       batch_size=64)
    sims = (emb[:-1] * emb[1:]).sum(axis=1)
    if len(sims) == 0:
        return chunk_fixed(text)
    corte = float(np.percentile(sims, SEM_PERCENTILE))

    spans, ini, palavras = [], 0, 0
    for gi, g in enumerate(grupos):
        palavras += sum(len(s[2].split()) for s in g)
        ultimo = gi == len(grupos) - 1
        quebra = (not ultimo) and sims[gi] <= corte and palavras >= SEM_MIN_WORDS
        if ultimo or quebra or palavras >= SEM_MAX_WORDS:
            spans.append((grupos[ini][0][0], g[-1][1]))
            ini, palavras = gi + 1, 0
    return spans


def chunk_qa_turn(text: str) -> list[tuple[int, int]]:
    """Trata a interrogacao como virada de turno; agrupa ate o tamanho alvo."""
    sents = sentences(text)
    if not sents:
        return []
    spans, ini, palavras = [], 0, 0
    for i, (_, _, s) in enumerate(sents):
        palavras += len(s.split())
        ultimo = i == len(sents) - 1
        # Fecha DEPOIS de uma pergunta quando o chunk ja tem tamanho util:
        # a pergunta e a resposta que a segue devem ficar no mesmo trecho.
        vira_turno = s.rstrip().endswith("?") and palavras >= TARGET_WORDS * 0.5
        if ultimo or vira_turno or palavras >= TARGET_WORDS * 1.6:
            spans.append((sents[ini][0], sents[i][1]))
            ini, palavras = i + 1, 0
    return spans


def merge_tiny(spans: list[tuple[int, int]], text: str) -> list[tuple[int, int]]:
    """Funde trechos curtos demais no vizinho, em vez de descarta-los.

    Fundir preserva a cobertura do texto; descartar abriria buracos. Como os
    spans sao contiguos ou sobrepostos, fundir e so estender a fronteira.
    """
    if not spans:
        return spans
    out: list[list[int]] = [list(spans[0])]
    for a, b in spans[1:]:
        if len(text[out[-1][0]:out[-1][1]].split()) < MIN_WORDS:
            out[-1][1] = b          # o anterior era curto: absorve este
        elif len(text[a:b].split()) < MIN_WORDS:
            out[-1][1] = max(out[-1][1], b)   # este e curto: cola no anterior
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def build_prefix(row: dict) -> str:
    """Situa o trecho na aula. Deterministico — nenhuma chamada de LLM."""
    partes = [f"Curso: {row['course_title']}", f"Aula: {row['lesson_title']}"]
    if row.get("subject"):
        partes.append(f"Assunto: {row['subject']}")
    if row.get("instructor"):
        partes.append(f"Instrutor: {row['instructor']}")
    return "[" + " | ".join(partes) + "]\n"


def run(con, strategy: str) -> int:
    rows = con.execute("""
        SELECT v.lesson_uid, v.lesson_title, v.course_title, v.instructor,
               v.subject, t.path
        FROM v_rag_corpus v JOIN transcripts t USING (lesson_uid)
    """).df().to_dict("records")
    if not rows:
        raise SystemExit("v_rag_corpus vazio - rode sync_transcripts.py")

    model = None
    if strategy == "semantic":
        from sentence_transformers import SentenceTransformer
        import torch

        dev = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"  carregando bge-m3 em {dev} para detectar fronteiras...")
        model = SentenceTransformer("BAAI/bge-m3", device=dev)

    now = datetime.now()
    con.execute("DELETE FROM chunks WHERE strategy = ?", [strategy])
    total = 0
    for n, row in enumerate(rows, 1):
        text = Path(ROOT / row["path"]).read_text(encoding="utf-8")
        if strategy == "fixed":
            spans = chunk_fixed(text)
        elif strategy == "semantic":
            spans = chunk_semantic(text, model)
        elif strategy == "qa_turn":
            spans = chunk_qa_turn(text)
        else:
            raise SystemExit(f"estrategia desconhecida: {strategy}")
        spans = merge_tiny(spans, text)

        prefix = build_prefix(row)
        payload = []
        for i, (a, b) in enumerate(spans):
            trecho = text[a:b].strip()
            if not trecho:
                continue
            payload.append([
                f"{row['lesson_uid']}::{strategy}::{i:04d}", row["lesson_uid"], i, trecho,
                prefix, a, b, len(trecho.split()), round(len(trecho) / 4),
                strategy, now,
            ])
        con.executemany(
            "INSERT INTO chunks (chunk_uid, lesson_uid, chunk_index, text, "
            "context_prefix, char_start, char_end, word_count, token_estimate, "
            "strategy, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
        total += len(payload)
        if n % 50 == 0 or n == len(rows):
            print(f"  {n}/{len(rows)} aulas, {total} chunks")
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="fixed",
                    choices=["fixed", "semantic", "qa_turn"])
    ap.add_argument("--all", action="store_true", help="roda as tres estrategias")
    args = ap.parse_args()

    con = connect()
    init(con)
    for strategy in (["fixed", "semantic", "qa_turn"] if args.all else [args.strategy]):
        print(f"\nestrategia: {strategy}")
        n = run(con, strategy)
        stats = con.execute(
            "SELECT count(*), round(avg(word_count)), min(word_count), "
            "max(word_count), round(median(word_count)) "
            "FROM chunks WHERE strategy = ?", [strategy]
        ).fetchone()
        print(f"  {stats[0]} chunks | palavras: min {stats[2]} · "
              f"mediana {stats[4]:.0f} · media {stats[1]:.0f} · max {stats[3]}")
    con.close()


if __name__ == "__main__":
    main()
