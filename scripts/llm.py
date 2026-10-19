#!/usr/bin/env python3
"""Cliente Anthropic compartilhado por todos os scripts que chamam LLM.

Existe para que modelo, tratamento de recusa e fallback fiquem definidos num
lugar so, em vez de repetidos (e divergindo) em ask.py, enrich_lessons.py e
build_eval_set.py.

Credencial
----------
A chave nunca e gravada em arquivo do projeto. Duas formas de fornecer:

    export ANTHROPIC_API_KEY=sk-ant-...        # no shell
    echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env # arquivo local, ja no .gitignore

O .env e lido por python-dotenv na importacao deste modulo.

Duas particularidades do Opus 5 que este modulo trata
----------------------------------------------------
1. O thinking vem LIGADO por padrao e divide o teto de max_tokens com o texto da
   resposta. Um max_tokens dimensionado para a resposta sozinha trunca no meio.
   Por isso o default aqui e folgado.

2. Os classificadores de seguranca podem recusar a requisicao: a chamada volta
   com HTTP 200 e stop_reason='refusal', nao com excecao. Ler response.content[0]
   sem checar quebra. Conteudo clinico e uma area em que recusa por falso
   positivo acontece, entao o fallback server-side fica ligado por padrao — numa
   recusa a propria API reexecuta em outro modelo dentro da mesma chamada.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

MODEL = "claude-opus-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class RecusaDoModelo(RuntimeError):
    """O modelo (ou a cadeia inteira de fallback) recusou a requisicao."""


def client():
    import anthropic

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit(
            "Sem credencial. Exporte ANTHROPIC_API_KEY no shell, ou crie um .env\n"
            "na raiz do projeto com  ANTHROPIC_API_KEY=sk-ant-...  (ja ignorado pelo git)."
        )
    return anthropic.Anthropic()


def texto_de(resposta) -> str:
    """Extrai o texto, checando recusa ANTES de tocar em content."""
    if resposta.stop_reason == "refusal":
        det = getattr(resposta, "stop_details", None)
        cat = getattr(det, "category", None) if det else None
        raise RecusaDoModelo(f"requisicao recusada (categoria: {cat})")
    return "".join(b.text for b in resposta.content if b.type == "text")


def complete(
    prompt: str,
    system: str | None = None,
    *,
    max_tokens: int = 8000,
    effort: str = "high",
    schema: dict | None = None,
    model: str = MODEL,
    fallbacks: bool = True,
) -> str:
    """Uma chamada. Devolve texto, ou JSON valido quando `schema` e passado."""
    cli = client()
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": effort},
    }
    if system:
        kwargs["system"] = system
    if schema:
        kwargs["output_config"]["format"] = {"type": "json_schema", "schema": schema}

    if fallbacks:
        resposta = cli.beta.messages.create(
            betas=[FALLBACK_BETA], fallbacks="default", **kwargs
        )
    else:
        resposta = cli.messages.create(**kwargs)
    return texto_de(resposta)


def check() -> None:
    """Valida a credencial sem gastar tokens de saida (count_tokens e gratuito)."""
    r = client().messages.count_tokens(
        model=MODEL, messages=[{"role": "user", "content": "ping"}]
    )
    print(f"credencial OK | modelo {MODEL} | count_tokens respondeu {r.input_tokens}")


if __name__ == "__main__":
    check()
