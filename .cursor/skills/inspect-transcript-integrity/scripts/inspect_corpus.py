#!/usr/bin/env python3
"""Varredura de integridade das transcrições ragmed.

Implementa a ordem de decisão da skill inspect-transcript-integrity.
Não escreve no DuckDB. Saída: EDA/01-integridade-compreensao/decisoes.csv

    python .cursor/skills/inspect-transcript-integrity/scripts/inspect_corpus.py
"""

from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent


def find_root() -> Path:
    for p in [HERE, *HERE.parents]:
        if (p / "ragmed.duckdb").exists() and (p / "transcripts").is_dir():
            return p
    raise SystemExit("ragmed.duckdb não encontrado a partir do script")


ROOT = find_root()
TRANSCRIPT_DIR = ROOT / "transcripts"


def connect():
    return duckdb.connect(str(ROOT / "ragmed.duckdb"), read_only=True)

OUT = ROOT / "EDA" / "01-integridade-compreensao" / "decisoes.csv"
TODAY = date.today().isoformat()

# Calibração humana: não sobrescrever o veredito.
GOLD = {
    "lsn_3520778": ("inteira_curta", "confirmado", "humano"),
    "lsn_7780464": ("inteira_curta", "confirmado", "humano"),
    "lsn_6729443": ("truncada", "confirmado", "humano"),
    "lsn_4303292": ("truncada", "confirmado", "humano"),
    "lsn_9073011": ("inteira_curta", "confirmado", "humano"),
    "lsn_6729442": ("inteira_clinica", "confirmado", "humano"),
    "lsn_7784279": ("inteira_curta", "confirmado", "humano"),
    "lsn_loc_a77b2dff": ("resumo_notas", "confirmado", "humano"),
    "lsn_5491247": ("truncada", "confirmado", "humano"),
    "lsn_8875732": ("truncada", "incerto", "humano"),
    "lsn_7784275": ("inteira_clinica", "confirmado", "humano"),
    "lsn_5491265": ("truncada", "confirmado", "humano"),
    "lsn_8875733": ("inteira_clinica", "confirmado", "humano"),
    "lsn_7773605": ("asr_ruidosa_util", "confirmado", "humano"),
    "lsn_8881619": ("asr_ruidosa_util", "confirmado", "humano"),
}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def windows(text: str, n: int = 900) -> tuple[str, str, str]:
    text = text.strip()
    mid = max(0, len(text) // 2 - n // 2)
    return text[:n], text[mid : mid + n], text[-n:]


INTRO_TITLE = re.compile(
    r"bem-vind|boas-vindas|boas vindas|introdu[cç][aã]o|onboarding",
    re.I,
)

OPEN_RE = re.compile(
    r"\b("
    r"ola\b|olá\b|bom dia|boa tarde|boa noite|"
    r"seja muito bem-vind|seja bem-vind|sejam muito bem-vind|"
    r"vamos (começar|comecar|la|lá|falar|dar)|vamos falar|"
    r"eu sou (o |a )?(doutor|doutora|dr)|meu nome (e|é)|"
    r"sobe (ai|aí|no palco)|bem-vind"
    r")",
    re.I,
)

# Abertura de módulo de conteúdo (não saudação, mas início deliberado de tema).
TOPIC_OPEN_RE = re.compile(
    r"^(progesterona|testosterona|jejum|cortisol|ozonio|ozônio|"
    r"gente, vamos falar|vamos agora passar)",
    re.I,
)

CLOSE_RE = re.compile(
    r"("
    r"um abraco|um abraço|obrigad[oa]\b|ate la|até lá|"
    r"ficou claro|espero que tenha ficado|"
    r"proximo assunto|próximo assunto|"
    r"referencias bibliograficas|referências bibliográficas|"
    r"\bpalmas\b|conte com a gente|"
    r"muito obrigad|foi um tapinha|luva de pelica|"
    r"vamos para o nosso proximo|vamos para o nosso próximo|"
    r"vamos para a proxima aula|vamos para a próxima aula|"
    r"valeu a pena"
    r")",
    re.I,
)

CUT_END_RE = re.compile(
    r"(ta aqui o|tá aqui ó|tá aqui o|cad[eê] o|"
    r"nao apareceu|não apareceu|"
    r"vai quebrar jejum\.?$)",
    re.I,
)

ASR_RE = re.compile(
    r"usonioterapia|zoonoterapia|osioniz|"
    r"e a[ií] e a[ií] e a[ií]",
    re.I,
)

NOTES_MARKERS = re.compile(
    r"(→|=>|\bmg\b|\bml\b|\bEV\b|\bmcg\b|quelat|ampola|glicinato)",
    re.I,
)
SPEECH_FILLER = re.compile(r"\b(né|ne\b|tá\?|gente,|vamos lá)", re.I)


def title_is_intro(title: str) -> bool:
    t = fold(title)
    return bool(INTRO_TITLE.search(t)) or t.strip() in {
        "introducao",
        "introdução",
        "bem-vindo(a)!",
        "bem-vindo(a)",
        "bem-vindo",
    }


def looks_like_notes(title: str, text: str) -> bool:
    if re.search(r"resumo", fold(title)):
        return True
    head = text[:2500]
    markers = len(NOTES_MARKERS.findall(head))
    fillers = len(SPEECH_FILLER.findall(head))
    # resumo de doses: muitos marcadores, quase zero fala.
    return markers >= 8 and fillers <= 2


def has_opening(head: str) -> bool:
    h = head[:500]
    if OPEN_RE.search(h):
        return True
    if TOPIC_OPEN_RE.search(h.strip()):
        return True
    # "Então vamos lá" / "Então, gente, vamos" como início de bloco didático
    hf = fold(h[:120])
    if hf.startswith("entao vamos") or hf.startswith("então vamos"):
        return True
    if hf.startswith("entao, gente") or hf.startswith("então, gente"):
        return True
    if hf.startswith("gente, vamos") or hf.startswith("vamos falar agora"):
        return True
    return False


def has_closing(tail: str) -> bool:
    return bool(CLOSE_RE.search(tail[-600:]))


def has_cut_end(tail: str) -> bool:
    return bool(CUT_END_RE.search(tail[-250:]))


def midstream_start(head: str) -> bool:
    """Começo que na calibração era recorte, não abertura de aula."""
    h = fold(head[:180])
    needles = (
        "uma coisa, outra",
        "diz que e uma analise",
        "diz que é uma analise",
        "jejum e uma pergunta",
        "jejum é uma pergunta",
        "e a b12 que tem na",
    )
    return any(n in h for n in needles)


def classify(row: dict, text: str) -> tuple[str, str]:
    """Retorna (veredito, nota)."""
    title = row["lesson_title"] or ""
    pct = float(row["pct"] or 0)
    head, _mid, tail = windows(text)

    if looks_like_notes(title, text):
        return "resumo_notas", "documento de tópicos/doses, não fala"

    intro = title_is_intro(title)
    opening = has_opening(head) and not midstream_start(head)
    closing = has_closing(tail)
    cut = has_cut_end(tail)
    asr = bool(ASR_RE.search(text))

    # Recorte no começo sempre é truncada. Título "Onboarding" com desfecho
    # não salva se a fala já começa no meio.
    if midstream_start(head):
        return "truncada", "falta abertura (começo no meio da fala)"

    if cut and not closing:
        return "truncada", "falta desfecho"

    if not opening and not closing and pct < 40 and not intro:
        return "truncada", "sem abertura nem desfecho; % baixo vs. mediana do curso"

    if intro and opening and int(row["word_count"]) < 1200:
        return "inteira_curta", "welcome/introdução curta com forma reconhecível"

    if asr and (opening or closing or pct >= 40):
        return "asr_ruidosa_util", "termo ASR degradado; forma utilizável"

    if opening and closing:
        return "inteira_clinica", "abertura e desfecho reconhecíveis"

    if closing and pct >= 20:
        return "inteira_clinica", "desfecho didático; % não é prova de corte"

    if opening and pct >= 50:
        return "inteira_clinica", "abertura ok; aula longa o bastante para o curso"

    if not closing and pct < 30 and not intro:
        return "truncada", "sem desfecho e bem abaixo da mediana do curso"

    if opening or closing or pct >= 40:
        return "inteira_clinica", "forma utilizável (série/continuação)"

    return "truncada", "forma incompleta"


def load_rows(con):
    return con.execute(
        """
        WITH med AS (
          SELECT course_uid, median(t.word_count) AS med_curso
          FROM lessons l JOIN transcripts t USING (lesson_uid)
          GROUP BY 1
        )
        SELECT
          l.lesson_uid,
          c.course_title,
          l.lesson_title,
          t.word_count,
          round(m.med_curso) AS med_curso,
          round(100.0 * t.word_count / nullif(m.med_curso, 0), 1) AS pct
        FROM lessons l
        JOIN courses c USING (course_uid)
        JOIN transcripts t USING (lesson_uid)
        JOIN med m USING (course_uid)
        ORDER BY c.course_title, l.position_global NULLS LAST, l.lesson_uid
        """
    ).fetchdf()


def main() -> None:
    con = connect()
    df = load_rows(con)
    con.close()

    fieldnames = [
        "lesson_uid",
        "course_title",
        "lesson_title",
        "word_count",
        "med_curso",
        "pct",
        "veredito",
        "status",
        "decidido_por",
        "data",
        "nota",
    ]
    rows_out = []
    gold_mismatch = []

    for rec in df.to_dict("records"):
        uid = rec["lesson_uid"]
        path = TRANSCRIPT_DIR / f"{uid}.txt"
        text = path.read_text(encoding="utf-8")
        veredito, nota = classify(rec, text)

        if uid in GOLD:
            g_ver, g_status, g_who = GOLD[uid]
            if veredito != g_ver:
                gold_mismatch.append((uid, g_ver, veredito, nota))
            veredito, status, who = g_ver, g_status, g_who
            if uid == "lsn_8875732":
                nota = (
                    "calibração: forma truncada no fim; miolo útil. "
                    "truncada não significa inútil"
                )
            else:
                nota = "calibração humana 2026-08-23; " + nota
        else:
            status, who = "agente", "agente"

        rows_out.append(
            {
                "lesson_uid": uid,
                "course_title": rec["course_title"],
                "lesson_title": rec["lesson_title"],
                "word_count": int(rec["word_count"]),
                "med_curso": rec["med_curso"],
                "pct": rec["pct"],
                "veredito": veredito,
                "status": status,
                "decidido_por": who,
                "data": TODAY,
                "nota": nota,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    from collections import Counter

    counts = Counter(r["veredito"] for r in rows_out)
    print(f"escreveu {OUT.relative_to(ROOT)}  ({len(rows_out)} aulas)")
    for k, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<20} {n}")
    if gold_mismatch:
        print(f"\nAVISO: classificador divergiu de {len(gold_mismatch)} âncoras (ouro foi preservado):")
        for uid, g, got, nota in gold_mismatch:
            print(f"  {uid}: ouro={g}  script={got}  ({nota})")
    else:
        print("\nâncoras humanas: classificador alinhado em todas")


if __name__ == "__main__":
    main()
