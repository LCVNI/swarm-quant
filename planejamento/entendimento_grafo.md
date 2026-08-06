# Entendimento Profundo: Algoritmo de Grafos e Spillover

Este documento explica minuciosamente a lógica, a matemática e o código por trás da estratégia de Grafos (Market Graph) implementada em `grafo_estrategia.py`.

---

## 1. A Teoria dos Grafos Aplicada ao Mercado Financeiro

Para entender o código, primeiro desmistifiquemos o que é um "Grafo". 
Na matemática, um Grafo é apenas um mapa de conexões feito de duas partes:
* **Nós (Nodes/Vertices):** Os pontos do mapa. No nosso caso, **cada ação da bolsa é um Nó** (Ex: VALE3 é um nó, PETR4 é outro nó).
* **Arestas (Edges):** As linhas que conectam esses nós. No nosso algoritmo, **a aresta é a semelhança de comportamento (correlação)** entre duas ações.

A teoria que o algoritmo implementa (baseada em *Boginski et al.*) dita que o mercado pode ser desenhado sob uma grande teia de aranha estrutural. Ações que se conectam muito formam "comunidades". A hipótese principal da estratégia é comportamental/estatística: **Se todas as ações ligadas diretamente a VOCÊ subiram de preço nos últimos dias, e você não subiu, existe uma pressão matemática para que você suba também (o Efeito Spillover, ou "Transbordamento")**. O algoritmo tenta rastrear essa anomalia para comprar o "atrasado".

---

## 2. Passo a Passo do Código: Construindo a Vizinhança

Toda vez que o algoritmo "acorda" em um dia do loop de backtest, ele constrói essa teia de aranha do zero absoluto para tentar ler o estado atual do mercado (linhas 74-94: função `construir_grafo_correlacao`).

### A) A Janela de Correlação e a Matriz de Pearson
```python
janela_dados = retornos_pivot[retornos_pivot.index < data_referencia].tail(janela)
corr = janela_dados.corr()
```
O algoritmo não olha para preços, ele olha para **retornos diários** (a porcentagem que a ação subiu ou desceu no dia).
A função acima isola o que aconteceu no mercado nos últimos `X` dias antes do dia de hoje (definido pela `Janela de Correlação`). Ao acionar o método `.corr()`, o Pandas compara os retornos de todas as ações umas contra as outras usando a Correlação de Pearson (que vai de -1 a 1). 
* `1` significa que subiram e desceram perfeitamente em sincronia.
* `0` significa que não há relação nenhuma.

### B) Filtrando as "Amizades" Reais (Limiar/Threshold)
Neste ponto, o código criou uma tabela matricial contendo comparações matemáticas de todas as ações cruzadas e começa a adicionar os vértices (Arestas):
```python
for t1 in colunas:
    for t2 in colunas[i + 1:]:
        peso = corr.loc[t1, t2]
        if pd.notna(peso) and abs(peso) >= limiar_correlacao:
            grafo.add_edge(t1, t2, weight=float(peso))
```
Ele faz um "*Match*" um por um (`for t1 ... for t2`). Se a Ação A e a Ação B apresentarem um "peso" de correlação superior ao seu **Limiar** (ex: `0.30`), o algoritmo conclui que elas andam juntas com força suficiente e desenha a linha (Aresta) entre elas no Grafo (usando a biblioteca `networkx`).
Essa linha guarda o valor exato da correlação (como `weight`), garantindo que o algoritmo lembre o quão forte é a afinidade entre essas duas. Quem não atinge o limite é ignorado e não tem elo.

> 🛠️ **Ao final dessa função, o que temos?** Uma Estrutura da subjacente daquele dia específico do mercado. Você pode imaginar como um gráfico visual de teia enorme, onde ativos como bancos (ITUB4, BBDC4, BBAS3) estão embolados e densamente costurados entre si por arestas fortes, e empresas sem relação ficam isoladas ou desconectadas da panelinha central. Esta teia é o nosso *Market Graph*.

---

## 3. O Fator Decisivo: Sintetizando o Sinal Spillover

A teia (estrutura de vizinhança) define QUEM influencia QUEM. Mas como transformamos um desenho em um botão de "Comprar"?

A função `calcular_sinal_grafo` (linhas 97-126) faz isso buscando *anomalias relativas*. 

### A) Descobrindo os vizinhos de cada ação
```python
vizinhos = list(grafo.neighbors(ticker))
```
Para cada ação disponível no dia, ele joga o ticker dela nas ferramentas do Grafo e indaga: *"Quais ações estão conectadas DIRETAMENTE nesta por uma aresta que passou pelo limiar estrito?"*. Estes são os `vizinhos`.

### B) Pesando a voz dos vizinhos 
```python
for v in vizinhos:
    r = retornos_recentes.get(v, np.nan)
    pesos.append(abs(grafo[ticker][v]["weight"]))
    retornos_viz.append(r)
media_vizinhos = float(np.average(retornos_viz, weights=pesos))
```
Ele olha para a rentabilidade acumulada da última semana (`retorno_5d`) dos amigos daquela ação em análise. Para que a média não seja injusta, o código usa uma **média ponderada** por intermédio da biblioteca Numpy (`np.average(..., weights)`).
Se um vizinho "A" tem `0.80` de correlação estrutural com a minha ação, e o vizinho "B" tem `0.35`, a rentabilidade do vizinho "A" importa **muito mais** no peso da média (porque ele é mais "íntimo" no grafo que os construiu). 

`media_vizinhos` é a síntese do comportamento do grupo em torno desse ativo-alvo.

### C) Descobrindo a discrepância (A Anomalia para Lucrar)
```python
sinal_spillover = round(media_vizinhos - retorno_proprio, 4)
```
Eis aqui a linha mais crítica de todo o robô. Ela subtrai os números:
Se os vizinhos íntimos estouraram nos últimos 5 dias com uma média ponderada subindo maravilhosamente (`media_vizinhos = +8%`), mas a nossa ação analisada amargurou na dela uma lerdeza ficando no zero (`retorno_proprio = 0%`). Logo:
* O Sinal de **Spillover dela será +8%**. (Efeito da mola esticada: ela foi deixada para trás sem justificativas estatísticas, deve convergir agressivamente nos próximos dias se reajustando ao comportamento da panelinha).

Quanto **MAIOR** (mais positivo) o Spillover de uma ação neste momento da fórmula, significa que o nó dela não reflete ainda as vitórias recentes da sua bolha matemática, tornando-se uma mina de ouro em forma de compra barata.

---

## 4. O Impacto dos Hiperparâmetros na Estratégia (Sintonia Fina)

Uma das belezas vitais dessa estratégia é como variar os parâmetros (hiperparâmetros) do modelo transforma brutalmente o resultado. Cada variável não é apenas um número, mas altera a **física** do grafo e o comportamento estatístico capturado:

### A) Janela de Correlação (`Janela`)
É o "nível de memória" estrutural do nosso modelo.
* **Janelas Curtas (ex: 30-40 dias):** O robô possui memória de curtíssimo prazo. Resulta num grafo extremamente adaptativo e nervoso. Pode identificar rapidamente mudanças setoriais bruscas recentes (ex: crise repentina no varejo afetando setores inteiros simultaneamente). Contudo, pode ser enganado por ruídos passageiros, criando elos falsos e temporários.
* **Janelas Longas (ex: 120-252 dias):** Cria comunidades sólidas e baseadas em relações perenes (ex: os grandes bancos sempre andam juntos estruturalmente a longo prazo). O grafo fica muito mais robusto contra ruídos, mas "lento" para perceber mudanças conjunturais nas correlações da bolsa.

### B) Limiar de Correlação (`Threshold`)
É o "nível de exigência" para que as amizades entre ações existam no Grafo (o filtro de densidade).
* **Limiar Baixo (ex: 0.15 - 0.20):** Cria uma teia muito cheia e conectada ("*Dense Graph*"). Ações não tão parecidas começam a influenciar umas às outras. Isso gera muito sinal de compra, mas com menor assertividade no efeito de Spillover, já que as anomalias baseadas nessas correlações fracas muitas vezes são inconsequentes.
* **Limiar Alto (ex: 0.40 - 0.50):** Corta brutalmente a conectividade do mercado e cria um "*Sparse Graph*". Apenas as ações estritamente idênticas no padrão de subida/queda são tratadas como vizinhas. As restrições deixam muitos ativos isolados e, portanto, ignorados nas compras. O volume de operações cai drasticamente, no entanto, as oportunidades sinalizadas tornam-se de muito maior probabilidade e confiança.

### C) Horizonte de Posicionamento (`Horizonte`)
É o tempo dado à "mola do preço" para descomprimir e subir para alcançar a bolha.
* **Horizonte Curto (ex: 1 a 3 dias):** Exige que a correção estatística do preço pela lei do rebanho ocorra quase instantaneamente. Se a correção tardar um pouco mais, o robô vai encerrar a posição prematuramente no zero a zero ou com leve prejuízo.
* **Horizonte Longo (ex: 10 a 15 dias):** Dá bastante tempo hábil para a correção matemática se impor na bolsa puxando a ação atrasada. O perigo? Ficar dias comprado traz o "*Risco Direcional*". Mesmo a ação estando atrasada perante sua vizinhança, uma queda generalizada no Ibovespa naqueles 15 dias simplesmente engole esse micro-atraso estrutural e gera prejuízos externos ao modelo de grafos.

### D) Filtro de Concentração (`Top_n`)
* Define quão aguçado e concentrado será o uso de dinheiro do backtest. Um `top_n = 2` destina a proteção do caixa forçando a compra de exclusivamente os 2 ativos com a maior anomalia absoluta (spillover) possível na data. Restringe as operações apenas aos sinais mais insanos e gritantes do modelo quantitativo. Em contrapartida, sofre pelo alto risco atrelado à falta de diversificação na carteira, enquanto valores mais elásticos aumentam a segurança pulverizando as anomalias detectadas.

---

## 5. Orquestrando tudo e Conversando entre Si

Quando damos *"Play"*, o arquivo engata um **relógio que salta** (`Horizonte`), para o código não rodar predições diárias que se misturam e acumulam custos altíssimos. Funciona assim:

1. **Olhar pro Abismo do Passado:** O código para na data *D*. Pega as cotações de todo o trimestre passado dessa data, calcula os pares matemáticos que subiram ou desceram juntos rigorosamente pelo **Threshold (Limiar)**, e monta a *Teia Invisível* (A Estrutura de Vizinhança/Market Graph).
2. **Avaliar Tensões na Teia:** Ele investiga os cantos da teia onde uma ação não seguiu os saltos da sua própria bolha nos últimos 5 dias, aplicando o cálculo do sinal de convergência (`Spillover`).
3. **Escudo de Custos:** Todo sinal recém calculado inferior às mordidas operacionais (A Corretagem total aplicada via percentual e B3 calculada na defasagem, que chamamos de `custo_pct_ida_volta`), é jogado no lixo imediatamente. Ele não tenta vencer guerras sem margem.
4. **Alocação Exata:** Sobraram os melhores Spillovers? Como são ações descaradamente descontadas de sua bolha estatística, o robô as hierarquiza das com mais chances paras a pior, filtrando pelas posições restritivas da variável `Top_n`. Feito isso, distribui cirurgicamente o `Capital MAX` para quem ainda restar de sinal verde usando a estratégia gananciosa (_alocar_greedy_), até que não sobre mais `capital_disponivel`.
5. **Máquina do Tempo:** Agora possuindo a cota de sua panelinha super-elástica na conta... O Backtester viaja quanticamente pelo espaço `Horizonte` no tempo (Ex: 5 Dias) - `i += horizonte`. Descarrega todo o bloco que ele comprou ignorando tendências, recolhendo na unha os retornos finais dessa convergência por intermédio da rentabilidade contínua. Paga o contador do IR (retendo prejuízos lógicos acumulados para burlar o leão, conforme `calcular_ir_mensal`).

É essa conversa engrenada que faz do Market Graph uma tese tão bonita: A capacidade de quantificar a lei do rebanho no mercado, e ativamente se posicionar apostando nos rebeldes lixeiros cuja discrepância não possuir embasamento matemático contra toda sua história diária construída pelo próprio threshold.

---

## 6. A Engenharia Financeira: Por Menores do Código

Para que o Backtest seja realista e profissionalmente aplicável (diferente da maioria dos backtests acadêmicos ingênuos), a partir da linha 132 do `grafo_estrategia.py`, o projeto impõe uma camada dura de Realidade Financeira do mercado brasileiro.

### A) O Filtro Implacável dos Custos (Ida e Volta)
Antes mesmo de cogitar uma compra baseada em Spillovers fortemente positivos, o código mensura a "mordida" percentual teórica de transação através da variável `custo_pct_ida_volta = 2 * (taxa_b3 + corretagem_pct * (1 + iss))`. 
Por que este valor é multiplicado por 2? Porque a B3, as taxas de registro e liquidação cobram no momento que você entra na posição e também ao sair dela. Se a sua anomalia (Spillover matemático) indica um ganho potencial de `+0.35%`, mas os custos totais somados na ida e volta dão `0.40%`... você entra na trade já com um prejuízo probabilístico certo. O robô aplica na linha 260 um machado estatístico implacável onde só entram na conta ordens com `Sinal > Custo_Ida_Volta`. Ações que não superam o custo transacional morrem e são totalmente descartadas da recomendação da bolha no dia.

### B) A Mecânica do "Algoritmo Guloso" (`_alocar_greedy`)
A mecânica de alocar efetivamente os pesos da sua conta de capital respeita o sistema de heurística que chamamos de algorítmo "*Greedy*" (guloso). 
Imagine que você tem R$ 100.000 (Capital Disponível). Após filtrar apenas oportunidades que derrotem os custos de transação, o script engata a função e classifica a discrepância MAIS FORTE (a que oferece maior diferencial em % por defasagem na bolha) no rank Top 1, depois Top 2, etc (Até o limite do filtro `top_n`).
O modelo "*Greedy*" aloca dinheiro cegamente e de forma agressiva enchendo a posição de lotes em papéis dessa primeira oportunidade até o seu limite imposto por `capital_max_por_acao`. Caso reste capital no tesouro da estratégia, a sobra desce para a Top 2 no rank de Spillovers, e assim por diante. Essa implementação empacota e aloca com precisão fracionando em lotes inteiros usando divisão inteira (`quantidade = int(valor_alvo // preco)`). A beleza dissimulada disto, é que ele maximiza matematicamente o seu capital jogando sempre os recursos para o maior nível de probabilidade estatística que ele encontrar naquele momento, evitando investir em Spillovers marginais. O contraponto negativo é o risco de forte concentração setorial num trade (pouca diversificação momentânea) no exato dia analisado.

### C) Gestão Autônoma de Contabilidade e Emulação de IR (`calcular_ir_mensal`)
Após recolher os retornos estatísticos saltando no tempo através dos chamados "horizontes" (O que caracteriza a rotina como um clássico modelo de liquidação *Swing Trade* no mercado à vista), o backtester emula a legislação brasileira na função base de IR (L. 159). Emulando precisamente as obrigações da RFB agrupada em balanços mensais (`dt.to_period("M")`):
1. **Escudo Acumulativo de Prejuízos Retidos:** O mercado legal permite a postergação e o abatimento irrestrito de seus prejuízos de negociação (Swing trade com Swing trade). No evento em que a bolha implodir levando a perda de caixa real na semana, o backtest estoca as derrapadas em variável de crédito fiscal contábil chamada `prejuizo_acumulado_apos`. Se futuramente os trades renderem positivamente, o lucro tributário (`lucro_mes`) terá de superar inteiramente os tombos defasados antes de começar a incidir cobrança, reproduzindo rigorosamente sua conta da corretora.
2. **Controle da Isenção B3 (O Piso de Vendas):** Para *Swing Trade* em balcão à vista no varejo e institucional pequeno, o regime brasileiro ressalva isenção total apurando a meta mensal absoluta através da variável de vendas (`vendas_mes`). Acaso um determinado mês próspero exija muita rotatividade alocativa inflando ordens até romper o volume padronizado do teto isento mensal (`ISENCAO_VENDAS_MENSAL_PADRAO`), a cobrança retroage integralmente anulando o privilégio fiscal de 0% da pessoa física na conta.
3. **Restituição do Dedo-Duro Integral (IRRF):** No ato instantâneo de toda transação que realiza lucro financeiro, corretagem liquida impiedosamente um spread pequeno na B3 à título de controle e denúncia que denominamos `IRRF` - *Retenção Tributária na Fonte*. Sempre que houver o encerramento do balanço resultando em carnê DARF a vencer `ir_devido`, a rotina já calcula o repasse que restou preso em banco deduzindo este mesmo fator compensatório do resultado bruto a pagar (`darf = ir_devido - irrf_retido_mes`), evitando severas inconsistências e bitributação irrealista na curvatura histórica da simulação. 

Esta engenharia engenhosa em união com a teoria topológica dos algoritimos, faz o que raros robôs em tutoriais online conseguem emular: Trazer clareza não ao poder quantitativo cego da métrica grafista idealística, mas ao nível final onde ela interage, sangra custos reais, e paga a conta diária que o mundo lhe exigirá.


---


# Plano de Implementação: Métricas Quantitativas e Econofísica

Visando o sucesso da estratégia de redes topológicas (Market Graph) no desafio Itaú Quant 2026, propomos as seguintes expansões científicas aliadas a uma engenharia de dados precisa. Nenhuma linha de código final foi escrita ainda, focando inteiramente no racional matemático de como conectar as saídas atuais do nosso backtester às métricas cobiçadas das tesourarias e aos modelos complexos da econofísica.

## 1. Mapeamento Matemático dos Indicadores e Deficiência de Dados

Tirando proveito direto das estruturas de dados instanciadas através do `backtest_grafo()`:
O Dataframe `operacoes` possui o histórico granular trade a trade.
O Dataframe `resumo` estampa o histórico sequencial de capital alocado globalmente pela variável `capital_apos_periodo`.

### A) Métricas 100% Contempladas e Endógenas
Modelos financeiros que apenas exigem as vitórias, derrotas e histórico do nosso próprio caixa estão perfeitamente municiados para o cálculo.

* **Win Rate (Hit Ratio da Assertividade)**
  * **O que precisamos:** Quantizar os acertos.
  * **Fórmula:** `Contagem de(operacoes['lucro'] > 0) / TamanhoTotal(operacoes)`

* **Profit Factor (Fator de Equilíbrio Bruto)**
  * **O que precisamos:** Volume grana real ganho e perdido.
  * **Fórmula:** `Soma_Absoluta(operacoes['lucro'] > 0) / |Soma_Absoluta(operacoes['lucro'] < 0)|`

* **Maximum Drawdown (Cova Crítica)**
  * **O que precisamos:** Histórico cumulativo simulando pico financeiro para analisar as declinações percentuais a partir deste high.
  * **Fórmula:** `Vetor_Quedas = ( res['capital_apos_periodo'] / res['capital_apos_periodo'].cummax() ) - 1`. E então: `MDD = Vetor_Quedas.min()`

### B) Métricas Relativas e Gargalos (O que falta no Projeto)
Os indicadores queridinhos institucionais impõem uma relação do ativo contra o risco geral do ecossistema e contra prêmios fixos e livre de risco. 

* **Metodologias (Sharpe, Alpha e Beta):**
  * **Retorno da Carteira Diária:** Facilmente inferido pelo recálculo da porcentagem do nosso próprio dataframe `resumo`. 
  * **Sharpe:** `(Retorno_Portfólio - Retorno_CDI) / Volatilidade_Portfólio`
  * **Beta:** `Cov(Retorno_Portfólio, Retorno_IBOV) / Var(Retorno_IBOV)`
  * **Alpha:** `Retorno_Portfólio - [Retorno_CDI + Beta * (Retorno_IBOV - Retorno_CDI)]`

* 🚨 **O que nos falta para programar as relativas:** 
Nós carecemos do fornecimento e extração de dois universos cruciais na nossa pipeline de infraestrutura de dados para os dias do backtest:
  1. **Taxa Livre de Risco:** A curva SELIC ou CDI Histórico para deduzir o custo de oportunidade (Usado em *Sharpe, Sortino, Jensen's Alpha*).
  2. **Benchmark Comparativo:** Séries históricas de fechamento contínuo do **IBOVESPA** (*BOVA11 / BVSP*) para as regressões lineares exigidas em *Alpha e Beta*. Precisaremos implementar extratores (via YahooFinance/BCB) ou carregar parquets na nossa infraestrutura antes de seguir adiante e criar colunas pareadas no dataframe.

---

## 2. Indicadores da Literatura da Econofísica (Expandindo a Física do Grafo)

As teorias de econofísica enxergam a precificação interligada da bolsa de valores como um sistema massivo dinâmico. Visto que modelamos nossas premissas via grafos topológicos matemáticos, introduzir esses 3 indicadores complementares eleva absurdamente o rigor científico frente à banca da Itau Asset.

### A) Densidade da Rede Estatística e "Medo Coletivo"
* **Conceito Base:** Em momentos calmos, a bolsa segue ritmos setoriais fragmentados. Quando uma quebra sistêmica ou contágio de pânico explode ("Joesley Day", circuit breakers globais), a correlação transversal salta à máxima. As ações se fundem (todas caem rigidamente iguais uníssonas). O grafo atinge a Densidade Máxima (`1.0`).
* **Indicador a se verificar:** Quantificar estaticamente a **Densidade e Assortatividade Global do Grafo** dia a dia. Estruturar um argumento de que nossa aplicação rastreia o aumento abrupto de arestas unificadas como uma *"Sirene Preventiva Macro"* para abortar trades de spillover até a turbulência ou densidade se dispersar.

### B) Centralidade de Autovetores (Eigenvector Centrality)
* **Conceito Base:** O Google domina a web através de nós de pesquisa por força do PageRank. Na econofísica (modelos de falhas em cascata de Mantegna e Sornette), nem todos os vizinhos possuem o mesmo grau de contágio ou massa de interferência. Um ativo periférico influenciando vale menos que o peso de uma "superestrela topológica" incrustada no centro irradiando poder sobre dezenas de outros vértices.
* **Indicador a se verificar:** Analisar o *"Risk Weighting"* multiplicando as probabilidades da bolha pelo fator das notas de subordinação (Eigenvector score). Em vez de `calculo de média simples ponderada` pelo coef. Pearson, os Spillovers mais pesados atuariam nos cruzamentos oriundos dos grandes astros do mercado, purificando nossa escolha quantitativa das discrepâncias das "blue-chips do grafo".

### C) Expoente de Hurst (Persistência e Reunião em Carga)
* **Conceito Base:** A física tradicional do caos tenta quebrar a tese ingênua popular que o mercado caminha puramente em "passeio aleatório - (Random Walk)". O expoente de Hurst (`H`) flagra estatisticamente comportamentos persistentes contra não-persistentes.
  * `H == 0.5` : Passeio Aleatório.
  * `H < 0.5` : Série dotada de viés comportamental voltado à rápida **Reversão à Média**.
* **Indicador a se verificar:** Comprovar a viabilidade técnica da lei do rebanho gerando Hurst Exponents empíricos retroativos sobre nossas linhas de atrasos (O cálculo pontual da discrepância geradora do Spillover). Nós conseguiremos comprovar aos avaliadores, sem a sombra de dúvidas, que as fendas pontuais que selecionamos (Onde a Bolha > Ação) possuíam vetores mecânicos intrínsecos de regressão de preços ao centro do pelotão e de baixa incerteza de direcionalidade!

---

## 3. Conexões Diretas com Algoritmos Avançados de Redes

Esses conceitos e medidores de risco casam com absoluta perfeição com as mais conceituadas teorias de topologia estrutural do ecossistema financeiro. A implementação dessas ideias na nossa estratégia cria ramificações diretas para:

* **Árvore Geradora Mínima (Minimum Spanning Tree - MST | Mantegna):** Em vez de construir o grafo cortando arestas com um limiar fixo e burro (ex: Threshold = 0.3), a técnica MST extrair apenas o "esqueleto" hierárquico vital da B3 sem fechar ciclos. Ele elimina o ruído gerado pela alta *Densidade Sistêmica* focando exclusivamente na árvore genealógica primária de quem se move pelo reflexo de quem.
* **Métricas de Centralidade Ampliadas (Betweenness e PageRank):** O conceito do *Eigenvector Centrality* pode ser pareado com o *Betweenness*. Ações com alto Betweenness são "pontes" logísticas entre clusters diferentes (Ex: Uma holding conectando o setor de Bancos ao de Energia). Se um *Spillover* despontar nessas pontes de alta centralidade, a chance de ele iniciar um contágio inter-setor é gigante frente ao resto do mercado.
* **Detecção de Comunidades (Algoritmo de Louvain):** Atualmente, nosso cálculo de anomalia olha estatisticamente para vizinhos estritos de 1º Grau. O algoritmo de Louvain fatia o grafo descobrindo macrorregiões independentes. Nós poderíamos usar o Louvain para comparar a variação de preço da Ação não apenas contra os amigos próximos, mas sim usando a média coesa do seu "Continente (Cluster)" no Grafo, atenuando sinais falsos de curtíssimo prazo e validando reversões macroestruturais.
