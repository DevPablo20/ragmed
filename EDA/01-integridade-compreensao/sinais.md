# Sinais — integridade e compreensão

Calibrado na amostra (humano 2026-08-23) e aplicado às 247 (agente).

## Validados (nesta amostra)

1. **`word_count` << mediana do próprio curso não prova truncamento.**
   Welcome e introduções de série são 2–8% da mediana e estão inteiros
   (`lsn_3520778`, `lsn_7780464`, `lsn_9073011`, `lsn_7784279`).

2. **Truncada de verdade combina forma + tamanho.**
   Título de aula clínica (não “Bem-vindo” / “Introdução”) + começa no meio
   ou termina no meio + bem abaixo da mediana do curso.
   Caso-tipo: `lsn_4303292` (promete dicas, para em “tá aqui ó”).

3. **Três sítios de corte, não um.**
   - Falta o começo, o fim existe (`lsn_5491247`, confirmado).
   - Começo existe, falta o fim (`lsn_5491265`, confirmado; `lsn_8875732` ainda incerto).
   - Falta os dois / recorte (`lsn_4303292`, `lsn_6729443`, ambos confirmados).

3b. **`truncada` descreve a forma, não o valor do miolo.**
   Humano em `lsn_8875732`: “no meio do texto tem informações relevantes”.
   Isso não desmente o corte no fim. Aula cortada pode (e costuma) ter
   trecho utilizável no RAG. Não esperar “truncada = jogar fora”.

4. **Desfecho didático (“ficou claro”, “referências”, “próximo assunto”,
   “um abraço”) pesa mais que o percentual.**
   `lsn_7784275` tem 21% da mediana do TRH e mesmo assim fecha com bibliografia
   → `inteira_clinica`.

5. **Apontar slide não é, sozinho, `slide_opaco`.**
   Se o fato é dito em seguida (“isso aqui é uma lipoproteína” + definição),
   a aula pode ser utilizável. `slide_opaco` nesta amostra só aparece como
   *corte* (“tá aqui ó” sem o conteúdo).

6. **Mediana é por curso.** Saúde do homem ~4,5k é o normal dali
   (`lsn_3545312`). Masterclass ~2k. Super módulo 1 ~16k.

7. **ASR aceitável vs. ASR que quebra termo clínico.**
   `né`/`tá`/`astrona` em aula íntegra → `inteira_clinica`.
   `zoológico`/`usonioterapia` no lugar de ozônio, com o ensino ainda
   recuperável → `asr_ruidosa_util` (`lsn_7773605`).

8. **Nem todo `.txt` é fala.** `lsn_loc_a77b2dff` é resumo de doses.
   Rótulo `resumo_notas`. Não exigir saudação nem “até logo”.

9. **Aula longa bagunçada quase nunca é truncada.**
   Vendas / posicionamento / oncologia / consulta ao vivo têm abertura e
   fechamento. O problema é ruído, assunto ou caso de paciente — tópicos 02+.

10. **“A gente fala do resto depois” em aula de série não é corte**
    (`lsn_9354505`).

## Rejeitados / armadilhas

- Usar a mediana **global** (~8680) como limiar.
- Tratar todo arquivo < 1000 palavras como truncado.
- Tratar todo “isso aqui” / “tá aqui ó” como inútil — só quando o fato
  não é dito.
- Confundir `inteira_curta` (welcome/intro íntegra) com “excluir do RAG”.
  Exclusão é tópico 02 / `include_in_rag`, não este.

## Incerto — precisa de regra/script depois

- Limiar numérico automático: 25% da mediana do curso pega welcome *e*
  truncada. Só funciona **depois** de filtrar título (Bem-vindo, Introdução,
  Onboarding) ou de olhar abertura/fim.
- ORIGEM aula 01 (`lsn_8875732`): permanece `truncada` / `incerto`. Miolo útil.
  Não bloqueia o fechamento do tópico.
- Limiar numérico sozinho continua inválido; o script combina título, abertura,
  desfecho e mediana do curso.
- Masterclass colesterol vs. ácido úrico: **fechada**. Humano confirmou
  `truncada` (`lsn_6729443`) e `inteira_clinica` (`lsn_6729442`).
- Como marcar trecho de intervalo com ASR repetido (`E aí E aí`) dentro de
  aula inteira: hoje a aula inteira vira `asr_ruidosa_util`; no chunking
  futuro talvez se descarte só a janela do intervalo.
- Normalização de termos (`usonioterapia` → `ozonioterapia`) é pós-inspeção,
  não veredito.
