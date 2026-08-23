# Decisões — integridade e compreensão

Fonte das **247 aulas:** [decisoes.csv](decisoes.csv) (varredura do agente,
skill v1, 2026-08-23). Este markdown guarda a **calibração humana** e o
resumo do corpus. Não editar aula a aula daqui pra frente.

`veredito`: `inteira_curta` | `truncada` | `resumo_notas` | `asr_ruidosa_util` | `inteira_clinica`

`status` no CSV: `confirmado` / `incerto` = âncora humana (o script não
sobrescreve o rótulo); `agente` = julgamento autônomo.

## Corpus (247)

| veredito | n |
|---|---|
| inteira_clinica | 224 |
| truncada | 10 |
| asr_ruidosa_util | 8 |
| inteira_curta | 4 |
| resumo_notas | 1 |

Leitura: a maior parte do texto está inteira e utilizável. Truncadas são
exceção. ASR que quebra termo clínico é raro e ainda assim recuperável.
`truncada` não significa “não indexar”.

As 6 aulas da amostra que estavam `proposto` foram fechadas pelo agente
como `inteira_clinica` (Cortisol Pré-Imersão, Saúde Digestiva, TRH Saúde do
homem, Posicionamento Marina, Oncologia, Consulta ao vivo).

## Calibração humana (15 âncoras — não relitigar)

| lesson_uid | veredito | status | nota |
|---|---|---|---|
| lsn_3520778 | inteira_curta | confirmado | Welcome Nutrição, 157 pal. |
| lsn_7780464 | inteira_curta | confirmado | Introdução MMI 2024 |
| lsn_6729443 | truncada | confirmado | Masterclass colesterol, recorte |
| lsn_4303292 | truncada | confirmado | Tríade II, caso-tipo (“tá aqui ó”) |
| lsn_9073011 | inteira_curta | confirmado | ORIGEM Boas-vindas |
| lsn_6729442 | inteira_clinica | confirmado | Masterclass ácido úrico |
| lsn_7784279 | inteira_curta | confirmado | Introdução TRH (teaser) |
| lsn_loc_a77b2dff | resumo_notas | confirmado | Doses/fórmulas, não fala |
| lsn_5491247 | truncada | confirmado | Onboarding Pacheco, falta começo |
| lsn_8875732 | truncada | incerto | ORIGEM aula 01: fim fraco, miolo útil |
| lsn_7784275 | inteira_clinica | confirmado | TRH aula 01, fecha com referências |
| lsn_5491265 | truncada | confirmado | Jejum, sem encerramento |
| lsn_8875733 | inteira_clinica | confirmado | Progesterona, chão de ASR aceitável |
| lsn_7773605 | asr_ruidosa_util | confirmado | Ozônio / usonioterapia |
| lsn_8881619 | asr_ruidosa_util | confirmado | Vendas, ruído no intervalo |

Zero `corrigido` na calibração: o critério foi aceito. Varredura das demais
usa o mesmo critério via `inspect_corpus.py`.
