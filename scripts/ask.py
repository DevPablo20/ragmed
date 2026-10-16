#!/usr/bin/env python3
"""Pergunta ao corpus: recupera os trechos e gera a resposta com a fonte citada.

    python scripts/ask.py "qual a dose de testosterona em implante?"
    python scripts/ask.py "cortisol e sono" --course Cardiologia -k 8
    python scripts/ask.py "..." --show-context   # imprime o que foi recuperado

O prompt e escrito para que a resposta seja verificavel, nao so plausivel:
o modelo responde SOMENTE a partir dos trechos recuperados, cita a aula de onde
tirou cada afirmacao, e diz explicitamente quando o corpus nao cobre a pergunta
em vez de completar com conhecimento proprio. E aqui que o lesson_url que
guardamos desde a primeira raspagem vira resposta conferivel — e a razao de as
aulas de origem local, que nao tem URL, ficarem fora do indice.

Aviso de uso: isto recupera e resume o que os professores disseram em aula. Nao
e recomendacao clinica, e o texto vem de transcricao automatica, que erra termo.
A citacao existe para voce poder conferir na aula original.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
from llm import RecusaDoModelo, complete  # noqa: E402
from search import search  # noqa: E402

SYSTEM = """\
Você responde perguntas clínicas usando exclusivamente trechos de transcrições de \
aulas de medicina metabólica que recebe no contexto.

Regras:
- Responda SOMENTE com o que está nos trechos. Não complete com conhecimento próprio.
- Se os trechos não cobrem a pergunta, diga isso claramente e pare. É melhor não \
responder do que inventar.
- Cite a fonte de cada afirmação no formato [n], referindo o número do trecho.
- Os trechos vêm de transcrição automática de fala e contêm erros de reconhecimento \
(termos médicos grafados errado, números possivelmente corrompidos). Se um valor ou \
termo parecer inconsistente, sinalize em vez de repeti-lo como certo.
- Quando os trechos discordam entre si, mostre a divergência em vez de escolher um lado.
- Escreva em português do Brasil, direto, sem preâmbulo."""


def montar_contexto(hits: list[dict]) -> str:
    partes = []
    for h in hits:
        partes.append(
            f"[{h['rank']}] Curso: {h['course_title']} | Aula: {h['lesson_title']}"
            + (f" | Instrutor: {h['instructor']}" if h.get("instructor") else "")
            + f"\n{h['text'].strip()}"
        )
    return "\n\n---\n\n".join(partes)


def imprimir_fontes(hits: list[dict]) -> None:
    """Agrupa por aula, mas lista TODOS os [n] que apontam para ela.

    Deduplicar por lesson_uid guardando so o primeiro rank quebrava o contrato de
    citacao, e de forma invisivel: numa resposta real o modelo citou [5], [7] e
    [10] — tres chunks da MESMA aula — e o bloco mostrava so o [5]. Quem
    procurasse [7] nao achava numero nenhum, embora a URL estivesse ali sob outro
    rotulo. Citacao que o leitor nao consegue resolver nao e citacao verificavel,
    que e a razao de ser deste projeto.
    """
    print("\n" + "─" * 78 + "\nFONTES\n")
    por_aula: dict[str, list[dict]] = {}
    for h in hits:
        por_aula.setdefault(h["lesson_uid"], []).append(h)
    # dict preserva ordem de insercao, entao as aulas saem na ordem do ranking.
    for grupo in por_aula.values():
        h = grupo[0]
        ns = " ".join(f"[{x['rank']}]" for x in grupo)
        print(f"  {ns} {h['lesson_title']}")
        print(f"      {h['course_title']}")
        print(f"      {h['lesson_url']}")
    print("\nTranscrições automáticas de aula — confira na fonte antes de usar "
          "clinicamente.")


def perguntar(con, pergunta: str, top_k: int = 10, **filtros) -> dict:
    hits = search(con, pergunta, top_k=top_k, **filtros)
    if not hits:
        return {"resposta": "Nenhum trecho recuperado para esta pergunta.", "hits": []}

    prompt = (
        f"TRECHOS RECUPERADOS:\n\n{montar_contexto(hits)}\n\n"
        f"---\n\nPERGUNTA: {pergunta}"
    )
    try:
        resposta = complete(prompt, system=SYSTEM, max_tokens=8000)
    except RecusaDoModelo as e:
        resposta = f"[o modelo recusou responder: {e}]"
    return {"resposta": resposta, "hits": hits}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pergunta")
    ap.add_argument("-k", "--top-k", type=int, default=10)
    ap.add_argument("--strategy", default="fixed",
                    choices=["fixed", "semantic", "qa_turn"])
    ap.add_argument("--course"), ap.add_argument("--subject")
    ap.add_argument("--instructor")
    ap.add_argument("--show-context", action="store_true")
    args = ap.parse_args()

    con = connect(read_only=True)
    r = perguntar(con, args.pergunta, args.top_k, strategy=args.strategy,
                  course=args.course, subject=args.subject,
                  instructor=args.instructor)

    if args.show_context:
        print("=" * 78)
        for h in r["hits"]:
            print(f"[{h['rank']}] {h['course_title']} | {h['lesson_title']}")
            print(f"    {h['text'][:240].strip()}...\n")
        print("=" * 78 + "\n")

    print(r["resposta"])
    if r["hits"]:
        imprimir_fontes(r["hits"])
    con.close()


if __name__ == "__main__":
    main()
