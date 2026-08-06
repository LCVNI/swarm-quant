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
