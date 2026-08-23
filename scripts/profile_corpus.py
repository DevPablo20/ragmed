#!/usr/bin/env python3
"""Perfila o corpus e grava lesson_quality + um relatorio legivel.

    python scripts/profile_corpus.py            # aplica e escreve o relatorio
    python scripts/profile_corpus.py --check    # so imprime, nao escreve no banco

Reexecutavel: rode de novo depois de adicionar aulas e as medidas se atualizam.

O que ele mede, e o que ele apenas suspeita
-------------------------------------------
Medidas sao fato: contagem de palavras, frases, interrogacoes, muletas de fala,
riqueza lexical. Entram no banco como numeros.

Julgamentos sao heuristicas com regra explicita, feitas para serem revisadas:

  truncation_suspect  a aula tem menos de TRUNC_RATIO da mediana de palavras do
                      proprio curso. Comparar contra o curso, e nao contra o
                      corpus, evita acusar aula curta de curso curto. Aberturas
                      legitimas ('Introducao', 'Bem-vindo') caem aqui tambem -
                      por isso e suspeita, nao veredito.

  domain              proporcao de vocabulario clinico contra vocabulario de
                      negocios NO TEXTO, nao no titulo. Classificar por titulo
                      erra feio: 'Gestao Integrada da Doenca Cardiovascular' e
                      aula clinica que casa com 'gestao'.
"""

from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, connect, init  # noqa: E402

REPORT = ROOT / "data" / "reports" / "corpus_profile.md"

# Abaixo desta fracao da mediana do curso, a aula vira suspeita de truncamento.
TRUNC_RATIO = 0.30
# Acima/abaixo destes limites de clinical_score, o dominio e considerado puro.
CLINICAL_HI, CLINICAL_LO = 0.70, 0.35

_FILLER = re.compile(
    r"\b(né|ne|tá|ta|então|entao|assim|tipo|pessoal|gente|ok|certo|beleza|"
    r"olha|veja|enfim|sabe|entendeu|pronto)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)

# Vocabulario marcador. Nao pretende ser exaustivo - so precisa separar as duas
# familias de aula que o corpus realmente tem.
CLINICAL = """paciente pacientes dose doses hormônio hormonio hormonal exame exames
tratamento sintoma sintomas terapia metabolismo receptor receptores sangue dosagem
mg ml diagnóstico diagnostico clínico clinico patologia célula celula celular
tireoide tireóide cortisol insulina testosterona estrogênio estrogenio progesterona
vitamina mineral suplementação suplementacao prescrição prescricao mitocôndria
mitocondria enzima proteína proteina glicose colesterol inflamação inflamacao
deficiência deficiencia laboratorial sérico serico plasma tecido
implante implantes anestesia anestésico anestesico sutura suturar incisão incisao
bisturi agulha assepsia curativo cicatriz náilon nailon subcutâneo subcutaneo
punção puncao cânula canula""".split()

BUSINESS = """cliente clientes venda vendas vender marketing faturamento posicionamento
instagram público publico preço preco contrato marca audiência audiencia funil
conversão conversao lead leads anúncio anuncio campanha branding negócio negocio
empresa faturar lucro investimento estratégia estrategia comunicação comunicacao
persona engajamento seguidores conteúdo conteudo""".split()


def analyse(text: str) -> dict:
    words = _WORD.findall(text.lower())
    n = len(words) or 1
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    sent_lens = [len(s.split()) for s in sentences] or [0]

    clin = sum(words.count(w) for w in CLINICAL)
    biz = sum(words.count(w) for w in BUSINESS)
    score = clin / (clin + biz) if (clin + biz) else 0.5

    return {
        "word_count": len(text.split()),
        "sentence_count": len(sentences),
        "sentence_median_words": float(st.median(sent_lens)),
        "question_count": text.count("?"),
        "questions_per_1k": 1000 * text.count("?") / n,
        "filler_pct": 100 * len(_FILLER.findall(text)) / n,
        "type_token_ratio": len(set(words)) / n,
        "clinical_score": score,
    }


def classify(score: float) -> str:
    if score >= CLINICAL_HI:
        return "clinical"
    if score <= CLINICAL_LO:
        return "business"
    return "mixed"


def fmt(v: float, nd: int = 1) -> str:
    return f"{v:,.{nd}f}".replace(",", ".")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    con = connect()
    init(con)
    rows = con.execute("""
        SELECT l.lesson_uid, c.course_uid, c.course_title, l.lesson_title,
               t.path, l.origin
        FROM lessons l
        JOIN transcripts t USING (lesson_uid)
        JOIN courses c USING (course_uid)
        ORDER BY c.position_in_vitrine NULLS LAST, l.position_global
    """).fetchall()
    if not rows:
        raise SystemExit("nenhuma transcricao registrada - rode sync_transcripts.py")

    prof = {}
    for uid, cuid, ctitle, ltitle, path, origin in rows:
        m = analyse(Path(ROOT / path).read_text(encoding="utf-8"))
        m |= {"course_uid": cuid, "course_title": ctitle,
              "lesson_title": ltitle, "origin": origin, "path": path}
        prof[uid] = m

    # A mediana e por curso: aula curta num curso curto nao e anomalia.
    by_course: dict[str, list[int]] = {}
    for m in prof.values():
        by_course.setdefault(m["course_uid"], []).append(m["word_count"])
    medians = {c: st.median(v) for c, v in by_course.items()}

    for m in prof.values():
        med = medians[m["course_uid"]] or 1
        m["course_median_words"] = float(med)
        m["length_ratio"] = m["word_count"] / med
        m["truncation_suspect"] = m["length_ratio"] < TRUNC_RATIO
        m["domain"] = classify(m["clinical_score"])

    # ---------------- relatorio ----------------
    wc = [m["word_count"] for m in prof.values()]
    q = st.quantiles(wc, n=10)
    trunc = sorted(
        (m for m in prof.values() if m["truncation_suspect"]), key=lambda m: m["length_ratio"]
    )
    nonclin = sorted(
        (m for m in prof.values() if m["domain"] != "clinical"), key=lambda m: m["clinical_score"]
    )
    total_words = sum(wc)

    L = [
        "# Perfil do corpus",
        "",
        f"Gerado por `scripts/profile_corpus.py` em {datetime.now():%Y-%m-%d %H:%M}.",
        "",
        "## Volume",
        "",
        f"- **{len(prof)}** transcrições, **{fmt(total_words,0)}** palavras "
        f"(~{fmt(total_words*1.5/1e6,1)} M tokens estimados)",
        f"- palavras por aula: min **{min(wc)}** · p10 **{fmt(q[0],0)}** · "
        f"mediana **{fmt(st.median(wc),0)}** · p90 **{fmt(q[8],0)}** · max **{fmt(max(wc),0)}**",
        f"- dispersão de **{max(wc)//max(min(wc),1)}×** entre a menor e a maior",
        "",
        "## Estrutura do texto",
        "",
        "| medida | mediana | leitura |",
        "|---|---|---|",
        f"| palavras por frase | {fmt(st.median([m['sentence_median_words'] for m in prof.values()]),0)} "
        "| texto escrito fica em 15–20; isto é fala transcrita |",
        f"| interrogações por 1k palavras | {fmt(st.median([m['questions_per_1k'] for m in prof.values()]),1)} "
        "| Q&A embutido, sem marcação de locutor |",
        f"| muletas de fala | {fmt(st.median([m['filler_pct'] for m in prof.values()]),1)}% "
        "| «né», «então», «tipo», «gente» |",
        f"| riqueza lexical (TTR) | {fmt(st.median([m['type_token_ratio'] for m in prof.values()]),3)} "
        "| quanto menor, mais repetitivo |",
        "",
        "Nenhum arquivo tem quebra de linha: cada transcrição é uma única linha "
        "corrida. Não há parágrafo nem turno de fala para aproveitar como "
        "fronteira natural de chunk.",
        "",
        f"## Suspeitas de truncamento ({len(trunc)})",
        "",
        f"Regra: menos de **{TRUNC_RATIO:.0%}** da mediana de palavras do próprio curso. "
        "Aberturas legítimas («Introdução», «Bem-vindo») caem aqui também — por isso "
        "é suspeita, não veredito.",
        "",
        "| aula | palavras | mediana do curso | razão | curso |",
        "|---|---|---|---|---|",
    ]
    for m in trunc:
        L.append(
            f"| {m['lesson_title'][:44]} | {m['word_count']} | "
            f"{fmt(m['course_median_words'],0)} | {m['length_ratio']:.2f} | "
            f"{m['course_title'][:30]} |"
        )

    L += [
        "",
        f"## Domínio ({len(nonclin)} aulas fora de «clinical»)",
        "",
        "`clinical_score` = proporção de vocabulário clínico contra vocabulário de "
        "negócios **no texto**, não no título. Classificar por título erra: "
        "«Gestão Integrada da Doença Cardiovascular» é aula clínica que casa com «gestão».",
        "",
        "| aula | score | domínio | palavras | curso |",
        "|---|---|---|---|---|",
    ]
    for m in nonclin:
        L.append(
            f"| {m['lesson_title'][:44]} | {m['clinical_score']:.2f} | {m['domain']} | "
            f"{m['word_count']} | {m['course_title'][:28]} |"
        )

    biz_words = sum(m["word_count"] for m in prof.values() if m["domain"] == "business")
    L += [
        "",
        f"Conteúdo classificado como `business`: **{fmt(100*biz_words/total_words,0)}%** "
        "do corpus em palavras. É material legítimo do curso, de outro domínio — "
        "rotular permite filtrar na consulta sem perder nada.",
        "",
        "## Cobertura por curso",
        "",
        "| curso | aulas | palavras | mediana |",
        "|---|---|---|---|",
    ]
    agg: dict[str, list] = {}
    for m in prof.values():
        agg.setdefault(m["course_title"], []).append(m["word_count"])
    for title, v in sorted(agg.items(), key=lambda kv: -sum(kv[1])):
        L.append(f"| {title[:52]} | {len(v)} | {fmt(sum(v),0)} | {fmt(st.median(v),0)} |")

    L += [
        "",
        "## O que isto sugere para o RAG",
        "",
        "1. **Segmentação é o gargalo.** Uma linha corrida de até 30 mil palavras, "
        "com frases de 7 palavras e sem parágrafo, é o pior caso para chunking de "
        "tamanho fixo — todo chunk nasce cortando um raciocínio. Vale testar "
        "quebra semântica e uso das interrogações como fronteira.",
        "2. **Enriquecer rende mais que limpar.** `subject`/`topics`/`summary` vazios "
        "em `lessons` habilitam pré-filtro por metadado e prefixo contextual por chunk.",
        "3. **Rotular, não descartar.** As aulas `business` saem da busca clínica por "
        "filtro, e continuam disponíveis.",
        "4. **Sem régua não há ganho medível.** Antes de escolher estratégia de chunk, "
        "um conjunto de perguntas com a aula-fonte anotada.",
        "",
    ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"{len(prof)} transcricoes | {fmt(total_words,0)} palavras")
    print(f"  suspeitas de truncamento: {len(trunc)}")
    print(f"  fora de 'clinical': {len(nonclin)} ({fmt(100*biz_words/total_words,0)}% do corpus)")
    print(f"  relatorio: {REPORT.relative_to(ROOT)}")

    if args.check:
        con.close()
        return

    now = datetime.now()
    con.execute("DELETE FROM lesson_quality")
    con.executemany(
        "INSERT INTO lesson_quality (lesson_uid, word_count, sentence_count, "
        "sentence_median_words, question_count, questions_per_1k, filler_pct, "
        "type_token_ratio, course_median_words, length_ratio, clinical_score, "
        "truncation_suspect, domain, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            [uid, m["word_count"], m["sentence_count"], m["sentence_median_words"],
             m["question_count"], m["questions_per_1k"], m["filler_pct"],
             m["type_token_ratio"], m["course_median_words"], m["length_ratio"],
             m["clinical_score"], m["truncation_suspect"], m["domain"], now]
            for uid, m in prof.items()
        ],
    )
    print(f"  lesson_quality: {con.execute('SELECT count(*) FROM lesson_quality').fetchone()[0]} linhas")
    print("  revisar com: SELECT * FROM v_quality_review")
    con.close()


if __name__ == "__main__":
    main()
