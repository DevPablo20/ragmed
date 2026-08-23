# Perfil do corpus

Gerado por `scripts/profile_corpus.py` em 2026-08-23 19:40.

## Volume

- **246** transcrições, **2.451.021** palavras (~3.7 M tokens estimados)
- palavras por aula: min **157** · p10 **3.302** · mediana **8.732** · p90 **18.102** · max **30.460**
- dispersão de **194×** entre a menor e a maior

## Estrutura do texto

| medida | mediana | leitura |
|---|---|---|
| palavras por frase | 8 | texto escrito fica em 15–20; isto é fala transcrita |
| interrogações por 1k palavras | 17.3 | Q&A embutido, sem marcação de locutor |
| muletas de fala | 4.3% | «né», «então», «tipo», «gente» |
| riqueza lexical (TTR) | 0.180 | quanto menor, mais repetitivo |

Nenhum arquivo tem quebra de linha: cada transcrição é uma única linha corrida. Não há parágrafo nem turno de fala para aproveitar como fronteira natural de chunk.

## Suspeitas de truncamento (12)

Regra: menos de **30%** da mediana de palavras do próprio curso. Aberturas legítimas («Introdução», «Bem-vindo») caem aqui também — por isso é suspeita, não veredito.

| aula | palavras | mediana do curso | razão | curso |
|---|---|---|---|---|
| Bem-vindo(a)! | 157 | 6.525 | 0.02 | Avançado de Nutrição Metabólic |
| Introdução | 208 | 5.274 | 0.04 | Review Congresso Internacional |
| Aula 05: Tríade Energética II | 354 | 5.395 | 0.07 | Introdutório de Fisiologia do  |
| Introdução: Terapia de Reposição Hormonal | 782 | 10.829 | 0.07 | Intensivo de Terapia de Reposi |
| resumo vitaminas e minerais | 928 | 9.020 | 0.10 | Avançado de Vitaminas, Minerai |
| AULA 01 - Onboarding | Luiz Pacheco | 1768 | 15.999 | 0.11 | Pós-Graduação Medicina Metaból |
| AULA 04 - Jejum | Dr. Alexandre Duarte | 2414 | 15.999 | 0.15 | Pós-Graduação Medicina Metaból |
| Aula 4 - Desmistificando o colesterol | 327 | 2.154 | 0.15 | Masterclass de Fisiologia do M |
| Aula 3 - Ácido úrico | 430 | 2.154 | 0.20 | Masterclass de Fisiologia do M |
| Aula 01: Os Hormonios Esteroidais | Dr. Alex | 2305 | 10.829 | 0.21 | Intensivo de Terapia de Reposi |
| Aula 02 | Alimentação | 2926 | 13.153 | 0.22 | Avançado de Oncologia + OmicSc |
| Aula 01 - Introdução Cadeia Esteroidal | 1949 | 8.030 | 0.24 | ORIGEM - Fisiologia Hormonal A |

## Domínio (26 aulas fora de «clinical»)

`clinical_score` = proporção de vocabulário clínico contra vocabulário de negócios **no texto**, não no título. Classificar por título erra: «Gestão Integrada da Doença Cardiovascular» é aula clínica que casa com «gestão».

| aula | score | domínio | palavras | curso |
|---|---|---|---|---|
| Aula 014 Aula Código da Audiencia Elias | 0.06 | business | 26608 | Avançado de Peptídeos |
| Aula 12 Vendas Luiz Pacheco | 0.07 | business | 10228 | Imersão em Fisiologia do Met |
| Aula 11: A Guerra de Percepções | William  | 0.07 | business | 20303 | Imersão em Fisiologia do Met |
| Aula 12 - Marketing de Conteúddo | Allan Lim | 0.08 | business | 15591 | Imersão em Fisiologia do Met |
| AULA 01 - Onboarding | Luiz Pacheco | 0.11 | business | 1768 | Fellowship em Medicina Metab |
| AULA 01 - Onboarding | Luiz Pacheco | 0.11 | business | 1768 | Pós-Graduação Medicina Metab |
| Aula 10 - Tathi Dehandela | 0.11 | business | 11182 | Imersão em Fisiologia do Met |
| 06 - Aula Carlos Nivel Cognitivo | 0.12 | business | 24522 | Pós-Graduação Medicina Metab |
| AULA 02 - Luiz Pacheco | 0.13 | business | 7163 | Pós-Graduação Medicina Metab |
| 07 - Aula Will Posicionamento | 0.14 | business | 21316 | Pós-Graduação Medicina Metab |
| AULA 05 - Luiz Pacheco Part 02 | 0.15 | business | 12393 | Pós-Graduação Medicina Metab |
| Aula 02 Vendas | 0.16 | business | 30460 | Pós-Graduação Medicina Metab |
| Aula 14: Sucesso em Gestão e Vendas | Luiz P | 0.27 | business | 10257 | Imersão em Fisiologia do Met |
| Aula 04 - Onboarding | Marina | 0.28 | business | 11424 | Onboarding Pós Graduação 202 |
| Aula 01 Marketing | 0.29 | business | 24112 | Pós-Graduação Medicina Metab |
| Aula 03 - Onboarding | Luiz Pacheco | 0.31 | business | 12607 | Onboarding Pós Graduação 202 |
| Aula 15 Contabilidade Matheus Gabrich | 0.32 | business | 5346 | Imersão em Fisiologia do Met |
| Aula 09 Tecnologia na Prática Médica Samuel  | 0.38 | mixed | 6919 | Imersão em Fisiologia do Met |
| Aula 013 Aula Posicionamento Marina | 0.42 | mixed | 27591 | Avançado de Peptídeos |
| Aula 08 - Gestão e Vendas | Luiz Pacheco | 0.44 | mixed | 9880 | Imersão em Fisiologia do Met |
| AULA 02 - Marketing e Posicionamento | Marin | 0.47 | mixed | 6798 | Fellowship em Medicina Metab |
| AULA 02 - Marketing e Posicionamento | Marin | 0.47 | mixed | 6798 | Pós-Graduação Medicina Metab |
| Aula 02 - Onboarding | Método In-MitoGen | 0.61 | mixed | 6398 | Onboarding Pós Graduação 202 |
| Perguntas finais | 0.64 | mixed | 6639 | Masterclass de Fisiologia do |
| Aula 04: Direito Médico | Ricardo Palova | 0.65 | mixed | 10552 | Imersão em Fisiologia do Met |
| Aula 09: Exames Genéticos e de DNA | Pier P | 0.68 | mixed | 7524 | Imersão em Fisiologia do Met |

Conteúdo classificado como `business`: **10%** do corpus em palavras. É material legítimo do curso, de outro domínio — rotular permite filtrar na consulta sem perder nada.

## Cobertura por curso

| curso | aulas | palavras | mediana |
|---|---|---|---|
| Pós-Graduação Medicina Metabólica - Super Módulo 1 | 16 | 245.688 | 15.999 |
| Imersão em Fisiologia do Metabolismo Humano | 2026 | | 20 | 214.305 | 10.044 |
| Imersão em Fisiologia do Metabolismo Humano | 2025 | 14 | 158.125 | 12.035 |
| Imersão em Fisiologia do Metabolismo Humano | 2024 | 15 | 139.292 | 7.597 |
| Pós-Graduação Medicina Metabólica - Super Módulo 3 | 8 | 120.469 | 14.600 |
| Avançado de Peptídeos | 14 | 111.212 | 4.198 |
| Avançado de Oncologia + OmicScreen | 7 | 97.960 | 13.153 |
| Avançado Pediatria Metabólica | 5 | 88.147 | 17.533 |
| Pós-Graduação Medicina Metabólica - Super Módulo 2 | 7 | 86.511 | 8.863 |
| Avançado de Doenças Autoimunes | 11 | 86.118 | 7.822 |
| Avançado de Saúde do homem | 16 | 70.547 | 4.472 |
| Avançado de Vitaminas, Minerais e Terapias Endovenos | 7 | 65.976 | 9.020 |
| Avançado de Termografia | 6 | 65.480 | 10.431 |
| Avançado de Análise de Exames Laboratoriais e DNA | 6 | 65.393 | 11.586 |
| Avançado de Nutrição Metabólica | 8 | 61.921 | 6.525 |
| Avançado de Saúde da Mulher | 4 | 60.037 | 16.600 |
| Avançado de Saúde Digestiva e Disbiose | 4 | 56.818 | 13.569 |
| Avançado de Cardiologia | 6 | 52.801 | 8.154 |
| Avançado de Neurotransmissores | 3 | 52.061 | 18.094 |
| Avançado de Emagrecimento Saudável | 6 | 50.612 | 7.879 |
| Avançado de Infertilidade e Tratamento Pré Gestação | 6 | 46.931 | 7.788 |
| Review Congresso Internacional de Metabologia (MMI)  | 8 | 45.558 | 5.274 |
| Review Congresso Internacional de Metabologia (MMI)  | 6 | 44.592 | 7.630 |
| Intensivo de Terapia de Reposição Hormonal | 5 | 44.328 | 10.829 |
| Avançado de Exercício Endurance | 3 | 43.245 | 13.345 |
| Onboarding Pós Graduação 2026 | 4 | 42.389 | 11.692 |
| Introdutório de Fisiologia do Metabolismo Humano | 7 | 42.205 | 5.395 |
| Avançado de Tríade Energética | 3 | 40.074 | 11.106 |
| Intensivo de Terapias Injetáveis | 3 | 39.077 | 13.759 |
| ORIGEM - Fisiologia Hormonal Avançada | 4 | 31.823 | 8.030 |
| Avançado de Anabolismo Saudável | 3 | 31.632 | 10.461 |
| Masterclass de Fisiologia do Metabolismo Humano | 6 | 17.269 | 2.154 |
| Tratamento Metabólico da Hipercalcemia | 1 | 15.107 | 15.107 |
| Fellowship em Medicina Metabólica | 2 | 8.566 | 4.283 |
| Pré-Imersão 2026 | 1 | 8.385 | 8.385 |
| ORIGEM — Boas-vindas | 1 | 367 | 367 |

## O que isto sugere para o RAG

1. **Segmentação é o gargalo.** Uma linha corrida de até 30 mil palavras, com frases de 7 palavras e sem parágrafo, é o pior caso para chunking de tamanho fixo — todo chunk nasce cortando um raciocínio. Vale testar quebra semântica e uso das interrogações como fronteira.
2. **Enriquecer rende mais que limpar.** `subject`/`topics`/`summary` vazios em `lessons` habilitam pré-filtro por metadado e prefixo contextual por chunk.
3. **Rotular, não descartar.** As aulas `business` saem da busca clínica por filtro, e continuam disponíveis.
4. **Sem régua não há ganho medível.** Antes de escolher estratégia de chunk, um conjunto de perguntas com a aula-fonte anotada.

