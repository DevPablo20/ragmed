# Exemplos que ensinaram o critério

Citações das aulas que **definiram** um rótulo. Não copiar a aula inteira.

## `inteira_curta` — welcome completo (não é corte)

**lsn_3520778** (157 pal., 2,4% da mediana do curso). Título “Bem-vindo(a)!”.

Início: apresentação. Fim: o recado acaba.

> Olá pessoal, tudo bem? Eu sou o doutor Alexandre Duarte, essa é a doutora Tânia. A gente vem aqui começar o nosso curso de nutrição metabólica.

> …e a gente não consegue ter saúde, ter qualidade de vida sem um metabolismo que funciona da maneira adequada.

**lsn_9073011** — mesmo rótulo, com despedida explícita:

> Seja muito bem-vindo ao Origem. Eu sou o Dr. Alexandre Duarte…

> Nos vemos no dia 29 às 10 da manhã. Um abraço e até lá.

Sinal: título de welcome/introdução **e** fala de abertura **e** desfecho. `% da mediana do curso` irrelevante.

## `truncada` — caso-tipo (Tríade Energética II)

**lsn_4303292** (354 pal., 6,6% da mediana). Título é aula clínica, não intro.

Entra no meio (Q&A de B12) e para apontando o slide:

> Então, gente, vamos lá. Vamos falar de triade energética. Finalmente, né? … E a B12 que tem na... Já vou até respondendo.

> Entendendo o cortisol. Cortisol é o hormônio mais importante do corpo. Eu vou dar algumas dicas aqui pra vocês … tá aqui ó.

Sinal: promete conteúdo + “tá aqui ó” / frase aberta + `word_count` << mediana **do curso**.

## `truncada` — falta só o começo (desfecho existe)

**lsn_5491247** Onboarding. Fecha a sessão, mas a primeira frase já está no meio do DISC:

> Diz que é uma análise de perfil comportamental que engloba as pessoas do mundo em quatro perfis.

> …Obrigado. E o que vocês precisarem de mentoria, de informação, pode contar comigo, tá bom?

Sinal: sem saudação/abertura de aula; última frase é encerramento de quem fala.

## `truncada` — abertura intacta, corte no fim

**lsn_8875732** ORIGEM aula 01. Começa como aula de verdade; some no comentário de slide:

> Olá gente, tudo bem? Bom dia. Vamos começar então essa nossa aula…

> Aqui eu repeti, lembro que botei duas vezes e não apareceu.

Sinal: irmãs do mesmo curso são 3–7× maiores; o fim não entrega “obrigado / próximo assunto / referências”.

Humano (2026-08-23) deixou `incerto`: o **miolo é relevante**. Manter `truncada` na forma; não ler isso como “aula sem valor”.

## `inteira_clinica` — módulo curto com desfecho didático

**lsn_6729442** Masterclass ácido úrico (430 pal.). Curso com mediana baixa (~2,1k). Aponta slide, mas o fato é falado; fecha o módulo:

> Espero que tenha ficado claro pra vocês.

Contraste com `lsn_4303292`: aqui não há promessa pendente.

## `inteira_clinica` — chão de ASR aceitável (controle)

**lsn_8875733** Progesterona (~8k, ~100% da mediana do curso).

> Progesterona, vamos agora passar de fase e começar de fato a aula hormonal.

> Perfeito, é isso por enquanto da progesterona, … mas vamos para o nosso próximo assunto.

`né` / `tá` / “astrona” (estrona) são o ruído normal. Não marcar `asr_ruidosa_util` por isso.

## `asr_ruidosa_util` — termo clínico destruído, ensino recuperável

**lsn_7773605** (ozônio). Primeiras frases:

> Então, o zoológico é uma coisa, né? … todos os outros profissionais da saúde podem trabalhar com zoonoterapia. … Para a gente trabalhar com a usonioterapia no consultório…

Algumas frases depois o termo correto aparece e o mecanismo é ensinável:

> Então o ozônio é a forma criatômica do oxigênio, enquanto o oxigênio é normalmente encontrado na forma diatômica.

Inteira (8,9k, acima da mediana do curso). O problema é vocabulário, não corte.

## `resumo_notas` — não é fala

**lsn_loc_a77b2dff** “resumo vitaminas e minerais”. Origem local.

> Minerais de pior absorção: Cromo → Magnésio → Silício. … Fosfato bibásico de potássio até 1200mg dia

> HMB (ácido β-hidroxi β-metilbutírico): Derivado da leucina. Ação anticatabólica…

Íntegro como documento de doses. Não avaliar com o mesmo teste de “abertura de aula / até logo”.

## Armadilha — mediana global

**lsn_3545312** Saúde do homem, TRH, 4510 palavras = **mediana daquele curso**.
Na mediana global (~8680) pareceria “curta”. É o tamanho normal daquele avançado.
Não usar mediana global como prova de truncamento.

## Armadilha — aula de série que “adia o resto”

**lsn_9354505** Cortisol, Pré-Imersão. Fecha:

> …depois a gente fala do resto da tríade.

Isso é encerramento de sessão, não corte. A aula de cortisol está inteira.
