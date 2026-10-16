# Roteiro de apresentação para o PO

Duração alvo: **20 min de demo + 10 min de perguntas**. A ordem abaixo é
deliberada: o problema primeiro, a virada de rota em seguida, e só então as
telas — porque a demo só impressiona quem já entendeu o que ela resolve.

---

## 0. Antes de entrar na sala (checklist)

> **Credencial validada em 02/10/2026.** A chave anterior estava revogada; a nova
> passou, e as três demos foram rodadas ponta a ponta com ela. As saídas estão
> gravadas em `demos/` como plano B. Revalide no dia, porque chave de terceiro
> pode ser rotacionada sem aviso.

```bash
cd /var/www/rag_hugo/ragmed && ~/.pyenv/versions/medrag/bin/python scripts/llm.py
```

Tem de imprimir `credencial OK`. Essa checagem usa `count_tokens` e é gratuita —
rode à vontade.

| item | comando / ação | por quê |
|---|---|---|
| Credencial válida | `python scripts/llm.py` → `credencial OK` | sem isso, não há Demo 2 nem 3 |
| Modelos aquecidos | rode **uma** busca qualquer antes da sala | a 1ª chamada carrega `bge-m3` + reranker: ~12 s. Aquecida, ~9 s |
| DBeaver fechado | fechar | DuckDB não aceita 2º processo; travar o banco na frente do PO é péssimo |
| Respostas gravadas | salvar a saída das 3 demos em arquivo | rede/saldo/API caindo no meio não derruba a apresentação |
| Terminal legível | fonte grande, janela limpa, `clear` entre blocos | a saída do `search.py` é larga |
| Alias pronto | `alias pyr=~/.pyenv/versions/medrag/bin/python` | digitar o caminho inteiro na frente dele queima tempo |

**O plano B já está gravado** (rodado em 02/10, fora do git):

```
demos/demo1_busca.txt               Demo 1 — search.py, testosterona em implante
demos/demo2_disfuncao_eretil.txt    Demo 2 — ask.py, resposta com FONTES
demos/demo3_controle_negativo.txt   Demo 3 — ask.py, roteador Cisco
```

Se algo falhar ao vivo: `cat demos/demo2_disfuncao_eretil.txt`. Diga que é saída
gravada — plano B assumido vale mais que demo travada. Para regravar com números
frescos, é o mesmo comando de cada demo com `> demos/<arquivo>` no fim.

**Tempo medido na máquina, com modelo já aquecido:** Demo 1 ~9 s · Demo 2 ~30 s ·
Demo 3 ~18 s. Tem silêncio de meio minuto na Demo 2 — é nele que você conta o que
ele vai ver.

---

## 1. O problema, em 90 segundos (sem slide, falado)

> "O material do college são 246 transcrições automáticas de aula: **2,45
> milhões de palavras**. Cada arquivo é uma **única linha corrida** de até 30 mil
> palavras — sem parágrafo, sem indicação de quem fala, com erro de
> reconhecimento de fala em termo técnico e em número."

Os dois problemas são opostos, e é isso que torna o caso interessante:

- **Grande demais para ler.** Achar "qual a dose de testosterona em implante"
  significa varrer 246 arquivos à mão.
- **Ruidoso demais para confiar.** O ASR erra nome de fármaco e corrompe dose.
  **Uma resposta que não deixe conferir a fonte é pior que nenhuma resposta.**

> "Então o objetivo não é 'um chatbot sobre as aulas'. É: responder uma pergunta
> clínica **citando a aula de origem com URL que o professor pode abrir e
> conferir**. A citação não é enfeite — é o que torna o ruído do ASR tolerável."

Frase para fixar: **o sistema recupera e resume o que o professor disse; quem
decide se está certo é o médico, na fonte.**

---

## 2. A virada de rota (2–3 min) — o ponto político da conversa

Esta parte é a que o PO precisa entender bem, porque **o que foi combinado mudou**.
Apresente como decisão técnica com motivo, não como escopo que escorregou.

> "A ideia inicial era um RAG que você usaria pelo chat do Claude. Comecei por
> ali e cheguei num limite: **naquele formato, a citação verificável — que é a
> razão de ser do projeto — não é garantível.**"

O argumento, concreto:

| o que o produto exige | no chat como camada única | no projeto local |
|---|---|---|
| URL da aula conferível | o modelo **escreveria** a URL → pode alucinar | o `ask.py` **imprime** a URL a partir do banco. O modelo nunca a escreve, logo não pode inventá-la |
| achar termo exato (dose, fármaco, sigla) | busca por similaridade dilui número e termo raro | **BM25 + busca densa** juntos: um acha paráfrase, o outro acha o termo exato |
| saber *por que* um trecho foi escolhido | caixa-preta | `--explain` mostra a posição em cada lista antes da fusão |
| excluir duplicata e material não clínico | tudo que subisse entraria | curadoria humana versionada; **nada sai do índice em silêncio** |
| medir se está melhorando | não é mensurável | o índice é nosso: dá para rodar régua e comparar configurações |
| custo por busca | chamada de modelo sempre | busca local custa **zero** e roda sem rede |

> "E o mais importante: **não troquei o chat pelo terminal, eu separei as duas
> camadas.** O núcleo — curadoria, índice, busca, citação — está pronto e
> testado. A interface hoje é linha de comando porque foi o caminho mais curto
> para validar o núcleo. Expor isso depois como chat, como API ou dentro da
> plataforma é uma camada fina sobre o que já existe, não um recomeço."

Se ele perguntar "então eu não vou usar pelo chat?" → **"vai, se você priorizar a
interface. Virou um item de backlog com estimativa, em vez de uma premissa."**
(ver § 7, pedido 1).

---

## 3. Demo 1 — a busca, sem credencial e sem rede (4 min)

Abra por aqui de propósito: é a parte determinística, que não depende de API nem
de saldo, e é onde a confiança se constrói.

```bash
pyr scripts/search.py "qual a dose de reposição de testosterona em implante hormonal?" -k 3
```

**O que apontar na tela, nesta ordem:**

1. **O rank 1 é a aula certa** — *Aula 16: Implantes Hormonais II*, do curso
   *Avançado de Saúde do homem*, com score 0,82.
2. **A URL no fim de cada bloco.** "Isso veio do banco. É clicável, e é a aula
   real na plataforma."
3. **O trecho mostra início E fim**, com `[...1389 caracteres...]` no meio.
   Explique por que: *"chunk tem ~366 palavras. Julgar um chunk pelos 200
   primeiros caracteres já me fez condenar erroneamente a qualidade da busca. A
   informação costuma estar no meio."*
4. **O rank 2 é de outro curso** (*Pós-Graduação Medicina Metabólica*) e traz
   "implante de 25, 50, até 75" — **a mesma pergunta respondida por dois
   professores diferentes**. Isso é um argumento de produto forte: o sistema
   mostra divergência entre aulas em vez de escolher um lado.

Se der tempo, o mesmo comando com `--explain` mostra a posição do chunk na lista
densa e na BM25 antes da fusão. Use se o PO for técnico; pule se não for.

---

## 4. Demo 2 — a resposta gerada com citação (5 min)

```bash
pyr scripts/ask.py "quais as principais causas da impotência sexual e quais os tratamentos"
```

Esta pergunta está escolhida: foi nela que a validação de 24/08 pegou os quatro
comportamentos que vendem o projeto. **Enquanto roda, conte o que ele vai ver.**

**O que apontar na resposta:**

1. **Cada afirmação tem `[n]`.**
2. **O bloco `FONTES` no fim**, com a URL de cada aula citada — impresso pelo
   script, não escrito pelo modelo.
3. **Um `[n]` que aparece agrupado**, tipo `[5] [7] [10] Aula 03: Disfunção
   Erétil`. Vale contar o bug aqui, porque mostra rigor: *"a primeira versão
   mostrava só o `[5]`. Quem procurasse o `[7]` não achava fonte nenhuma. A URL
   estava lá, sob outro rótulo — mas citação que o leitor não consegue resolver
   não é citação verificável, que é exatamente a razão de ser do projeto."*
4. **O modelo sinaliza o erro de ASR em vez de repetir.** Na validação ele
   marcou "diasídicos", "canais de solo e potássio" e números que oscilam na fala
   como suspeitos. *"Ele não finge que a transcrição está certa."*
5. **Ele declara o que os trechos NÃO cobrem** — PDE5, ondas de choque, doses — e
   para. E **descartou sozinho** os trechos de infertilidade que a busca trouxe,
   por serem outro problema clínico.
6. **O disclaimer impresso no fim**: não é recomendação clínica, confira na fonte.

**Um sétimo ponto, se ele for técnico — e é o mais interessante da rodada de
02/10.** Olhe de onde veio a substância da resposta: **ranks [7], [8] e [9]**. Os
três primeiros colocados ([1], [2], [5], do curso de *Infertilidade*) o modelo
**descartou sozinho**, por serem outro problema clínico. Duas conclusões para
oferecer:

- *"O `-k` importa mais do que parece. Se eu tivesse pedido só os 5 primeiros
  trechos, esta resposta não existiria."*
- *"E isso é evidência a favor da minha suspeita do prefixo contextual — o curso
  errado se chama 'Avançado de Infertilidade e **Tratamento** Pré Gestação', e a
  pergunta tem a palavra 'tratamentos'. O nome do curso virou ímã de palavra-chave
  e empurrou a aula certa para o 7º lugar. É exatamente isso que a régua da Etapa
  6 vai medir."*

Isso transforma uma limitação em demonstração de rigor: você não só sabe da
fraqueza, **ela aparece na tela e você a explica antes de ele notar.**

Frase de fechamento do bloco: **"o valor não está em ele responder. Está em ele
dizer o que não sabe e mostrar onde conferir o que disse."**

---

## 5. Demo 3 — o controle negativo (3 min) — guarde este para o fim

```bash
pyr scripts/ask.py "como configurar um roteador Cisco?"
```

> "Toda demo de RAG mostra a pergunta que funciona. Vou mostrar a que não tem
> resposta no corpus, porque é aí que esses sistemas costumam inventar."

Ele recusa na primeira linha. E então faz algo melhor que recusar: vai atrás das
coincidências lexicais do corpus e **explica por que nenhuma serve**, em vez de
ignorá-las em silêncio ou usá-las como ponte para fabricar resposta. Na rodada de
02/10 achou **duas**:

- *"sai do **Cisco**"* → erro de transcrição de **ducto cístico**, e ele reconstrói
  o trajeto da via biliar para provar: hepático direito/esquerdo → hepático comum
  → cístico → vesícula → colédoco → duodeno.
- *"**router**"* → é **holter**, no sentido de monitoramento contínuo de glicemia
  por 14 dias; o próprio instrutor diz na aula que usava o termo "router" por vir
  da cardiologia.

E fecha oferecendo: *"se a sua dúvida for sobre algum desses dois temas clínicos,
reformule que eu respondo."*

Vale dizer isto em voz alta: **"ele não só recusou — ele diagnosticou dois erros
de transcrição para poder recusar com fundamento."** É o melhor momento da demo,
e é por isso que ela fica no fim.

**O número que fecha o argumento** (medido em 22 perguntas: 12 respondíveis pelo
corpus, 10 claramente fora, usando o maior score de rerank do top-10):

| classe | n | menor score | maior score |
|---|---|---|---|
| **dentro** do corpus | 12 | 0,5763 | 0,9937 |
| **fora** do corpus | 10 | 0,00005 | 0,0077 |

> "**75× de separação, sem nenhuma sobreposição.** Qualquer limiar entre 0,01 e
> 0,5 classifica as 22 corretamente. Ou seja: o sistema sabe, *antes* de
> responder, se a pergunta está dentro do corpus. Isso hoje é um sinal de
> confiança que eu posso exibir por pergunta."

Se ele perguntar "então por que não bloquear automaticamente?" → **"porque a
recusa raciocinada do modelo foi mais informativa que qualquer mensagem
enlatada. Foi ela que achou o 'router de glicemia'. E a economia seria de
centavos. É decisão de produto, está documentada em aberto, e é sua."**

---

## 6. A metodologia em três ideias (4 min, sem demo)

Não enumere scripts. Três ideias, e cada uma com o motivo.

### 6.1 O pipeline

```
                                  ┌─ BM25 (termo exato) ─┐
transcrição → chunks → índice ─── ┤                      ├─ RRF k=60 ─ top 50
                                  └─ denso (paráfrase) ──┘                │
                                                                          ▼
                    resposta ← LLM ← top 10 ←──────────────────────── rerank
```

Quatro frases, uma por etapa:

- **Chunking é o gargalo real**, e o motivo é uma medida: o corpus tem **zero
  quebras de linha**, 8 palavras por frase. *"Não existe parágrafo para
  aproveitar."* Por isso há **três estratégias convivendo** no banco
  (`fixed` 6.556 · `semantic` 6.921 · `qa_turn` 7.974 chunks) em vez de uma
  escolhida por gosto.
- **Dois índices porque eles erram de formas opostas.** O denso acha paráfrase e
  dilui número; o BM25 acha dose e nome de fármaco e não sabe que dois termos
  significam o mesmo. *"Um clínico pergunta ora por conceito, ora por nome de
  substância — precisa dos dois."*
- **A fusão é por posição, não por score** (RRF). *"Um score de BM25 e um cosseno
  vivem em escalas incomparáveis; mediar os dois dá um número sem significado."*
- **O rerank é onde a precisão do topo se decide**, e é a etapa que dá o sinal de
  confiança do slide anterior.

Se pedir número: na pergunta da testosterona, 6 dos alvos ficam no top-10 **com**
rerank, contra 4 sem.

### 6.2 Nada sai do índice em silêncio

Dos 246 arquivos, **206 aulas entram** no índice (33 cursos, 1,99 M palavras). As
40 de fora, com motivo registrado:

| motivo | quantas |
|---|---|
| origem local — sem URL, logo **não citável** | 20 |
| domínio `business` — marketing, vendas, gestão | 16 |
| cópia de outra aula | 4 |

> "Tem uma view que define o que entra e outra, obrigatória, que lista o que
> ficou de fora **com o motivo**. As exclusões são decisão humana, ficam num JSON
> versionado com data e justificativa, e são **reversíveis**: mudar uma linha
> devolve as 20 aulas locais ao índice."

Conte **a duplicata que quase passou**, porque é a melhor história de rigor do
projeto: a detecção inicial comparou os textos **por amostragem** e concluiu que
duas aulas de Vitaminas eram distintas. A comparação completa mostrou que a
"Aula 05" **não é aula**: é a "Aula 06" truncada — 97,6% dela está dentro da 06,
palavra por palavra. *"Amostragem responde 'são parecidas?', não 'uma está
contida na outra?'."*

### 6.3 Nada é deletado, e o banco é derivado

Aula que sai do ar vira inativa e continua consultável, com a transcrição ligada
a ela. Cada raspagem do site fica guardada inteira, nunca sobrescrita. E o banco
pode ser **apagado e reconstruído do zero** — o teste já passou duas vezes.

> "O que é insubstituível são as transcrições e as decisões humanas de curadoria.
> Todo o resto é derivado e regenerável. Isso é o que garante que o conhecimento
> do projeto está em arquivo versionado, e não na cabeça de quem o construiu."

Esse é o argumento de **continuidade**: se outra pessoa assumir, está escrito.

---

## 7. Vantagens e limitações — leia como são, não como queremos

Faça este bloco **você**, antes de ele perguntar. Limitação apresentada é
credibilidade; limitação descoberta por ele é problema.

### Vantagens

| vantagem | o que sustenta |
|---|---|
| Citação impossível de alucinar | a URL é impressa pelo script a partir do banco, nunca gerada |
| Recusa medida, não prometida | 75× de separação de score entre dentro e fora do corpus, sem sobreposição |
| Busca auditável e barata | roda sem rede e sem credencial; custo zero por busca; `--explain` mostra o caminho |
| Curadoria rastreável | toda exclusão tem motivo, data e autor, e é reversível |
| Reprodutível do zero | reconstrução completa do banco testada 2× |
| Flexível por construção | 3 estratégias de chunking convivem; pré-filtro por curso/instrutor; pronto para virar API |
| Rápido | ~9–12 s por pergunta na CLI, e a maior parte disso é **carregar o modelo** — num serviço que fica de pé, cai para a casa dos milissegundos de busca |

### Limitações para produção

Agrupadas por quem precisa resolver — isso ajuda o PO a decidir.

**Faltam duas etapas conhecidas (eu resolvo, é trabalho):**

1. **Não existe régua de avaliação.** Esta é a limitação mais honesta de todas:
   *"não consigo afirmar qual das três estratégias de chunking é a melhor, nem
   quanto o rerank contribui. As demos que você viu são perguntas-teste
   validadas uma a uma, não uma métrica."* O plano é ~100 perguntas com a aula
   correta anotada **e validada por humano**, medindo recall@k, MRR e nDCG@10.
2. **O enriquecimento por LLM não foi feito** (~US$ 8,25, uma vez). Ele preenche
   assunto, tópicos e resumo das 206 aulas, e habilita o filtro por assunto.
   **Recomendo inverter a ordem e fazer a régua primeiro** — uma medição recente
   sugere que o prefixo contextual pode estar **prejudicando** a recuperação, não
   ajudando. Se for esse o caso, enriquecer o prefixo **agrava** o problema, e
   são 8 dólares gastos para piorar. A régua custa centavos e responde antes.

**Dependências de infraestrutura (precisa de decisão e de orçamento):**

3. **Roda numa GPU local** (RTX 4070 Ti Super). Em produção isso significa GPU no
   servidor, ou trocar os embeddings por API — o que adiciona custo e latência
   por busca. E o reranker **não é descartável**: é ele que dá o sinal de
   confiança do § 5.
4. **O banco não aceita dois processos escrevendo.** Leitura concorrente é
   tranquila; reindexar exige janela. Para volume real, trocar o motor ou separar
   leitura de escrita.
5. **A interface hoje é linha de comando.** Não há tela, autenticação,
   multiusuário, nem registro de quem perguntou o quê. Para o PO usar sozinho,
   isso é o item 1 do pedido abaixo.
6. **Custo por pergunta gerada: ~US$ 0,10**, e com dependência de um fornecedor
   único de modelo.

**Limites do material, que nenhuma engenharia resolve:**

7. **A ingestão é manual.** Raspar o site é um snippet colado no DevTools, e a
   transcrição de aula nova é trabalho humano. Hoje há **zero pendências**, mas
   aula nova não entra sozinha.
8. **O ASR erra, e vai continuar errando.** Número de dose se corrompe na fala.
   A mitigação é a citação e o modelo sinalizar a inconsistência — **não é
   corrigir o texto**. Isso não vai mudar.
9. **Cobertura é 206 de 246 aulas.** As 20 locais ficam fora por não terem URL,
   e isso é consequência direta de a citação ser a regra do projeto.

**Risco de produto, e vale dizer em voz alta:**

10. **É conteúdo clínico.** O disclaimer está impresso em toda resposta, mas se
    isso for exposto a aluno em escala, a conversa passa a ser de
    responsabilidade e compliance, não de engenharia. **Essa decisão é do PO, e
    eu não vou tomá-la sozinho.**

---

## 8. O que eu peço de decisão (feche por aqui)

Não encerre em "é isso". Encerre com três perguntas objetivas:

1. **Quem é o usuário da v1?** Só você, uma equipe pequena, ou aluno? A resposta
   muda tudo: para você sozinho, o que existe hoje já serve e eu invisto na
   régua. Para aluno, o trabalho vira interface, autenticação e compliance —
   outro projeto, em cima do mesmo núcleo.
2. **Posso fazer a régua antes do enriquecimento?** Custa centavos, e responde se
   os US$ 8,25 valem a pena antes de serem gastos.
3. **Tem apetite para GPU em servidor?** É o que separa "roda na minha máquina"
   de "roda para a equipe".

---

## 9. Perguntas que ele provavelmente vai fazer

| pergunta | resposta curta |
|---|---|
| "Por que não é mais no chat do Claude?" | § 2. Porque a citação verificável não é garantível quando é o modelo que escreve a URL. O chat volta como camada, se você priorizar. |
| "Ele pode inventar uma aula que não existe?" | Não. A URL é impressa pelo script a partir do banco, sobre os chunks que a busca de fato retornou. |
| "E se a transcrição estiver errada?" | Vai estar, em algum lugar. O modelo é instruído a **sinalizar** valor inconsistente, e a citação existe para você conferir. Não é um sistema que corrige o professor; é um que te leva até ele. |
| "Quanto custa?" | Busca: zero. Resposta gerada: ~US$ 0,10. Enriquecimento: US$ 8,25 uma vez. Infra: GPU, se sair da minha máquina. |
| "Está pronto?" | O núcleo está pronto e validado ponta a ponta. Falta a régua para eu poder dizer *quanto* ele é bom, e falta interface para você usar sem terminal. |
| "Quanto tempo para eu usar sozinho?" | Depende da resposta 1 do § 8 — não dê número antes disso. |
| "Dá para colocar na plataforma do college?" | Tecnicamente sim, é camada. Mas aí entram autenticação, multiusuário e a conversa de responsabilidade clínica do item 10. |
| "E se o site mudar?" | Cada raspagem é guardada e comparada com a anterior: o loader imprime o diff — aula nova, aula que saiu do ar, título alterado. Dá para ver **quando** mudou, em vez de descobrir que mudou. |

---

## 10. Colagem rápida dos comandos

```bash
alias pyr=~/.pyenv/versions/medrag/bin/python
cd /var/www/rag_hugo/ragmed

pyr scripts/llm.py                                  # credencial (gratuito)
pyr scripts/search.py "qual a dose de reposição de testosterona em implante hormonal?" -k 3
pyr scripts/ask.py "quais as principais causas da impotência sexual e quais os tratamentos"
pyr scripts/ask.py "como configurar um roteador Cisco?"
```

Números para ter na ponta da língua: **246** transcrições · **2,45 M** palavras ·
**206** aulas indexadas em **33** cursos · **6.556** chunks na estratégia `fixed`
· **75×** de separação entre pergunta dentro e fora do corpus · **~US$ 0,10** por
resposta.
