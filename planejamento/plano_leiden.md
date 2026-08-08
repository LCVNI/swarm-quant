# Plano de Implementação: Algoritmo de Leiden e Análise de Comunidades

Este documento elabora de ponta a ponta as alterações no código, a superioridade do modelo de Leiden, e como os novos indicadores servirão como escudo protetor visual e quantitativo na interface Streamlit.

---

## 1. O Racional Científico: Por que Leiden no lugar de Louvain?

O Comitê da Itaú Asset frequentemente interroga o porquê de um pacote foi escohido em detrimento de outro. Responder com profundidade matemática gera extrema aprovação.
* **O Defeito do Louvain (Resolution Limit e Desconexão Oculta):** O Louvain foi o padrão ouro por anos, iterando trocas de nós para elevar a modularidade cega do sistema. No entanto, matematicamente o Louvain sofre do "Resolution Limit". Se o mercado estiver denso, o algoritmo de repente engole microssistemas que não deviam se misturar e os solda numa comunidade suja, criando as conhecidas *badly connected communities* (nós do mesmo cluster com literalmente zero arestas ligando-os). Em derivativos e retornos percentuais, um cluster mal montado quebra a confiabilidade do nosso gatilho.
* **A Cura do Leiden:** Publicado em 2019, o Algoritmo de Leiden altera a física destas mesclagens. Ele possui uma fase de refinamento avançada garantindo que toda comunidade originada precisa ser *estritamente conectada e coesa*. Um Small-Cap Tech isolado nunca será agrupado estatisticamente nos bancões apenas por "preguiça modular". É a supremacia em clareza para tesourarias. 

---

## 2. Orquestração de Código: O que será Alterado/Adicionado

As mudanças no `backend` (`grafo_estrategia.py`) e pacotes do projeto para tornar isso vivo.

### A) Novas Dependências
O NetworkX puro não tem Leiden implementado. 
* Precisaremos adicionar no ambiente e no `shell.nix`: pacote `cdlib` (Community Discovery Library) ou `leidenalg` (junto ao `igraph`). Vamos instanciar a ponte entre grafos do networkx e pacotes de descoberta.

### B) Mudanças no Motor (`grafo_estrategia.py`) - Cenário: Limiar como "Faxineiro"

Neste cenário de implementação (mantendo o Limiar nativo, mas sem o uso de MST em conjunto), o hiperparâmetro `limiar_correlacao` (Threshold) ganha um novo emprego. Ele deixa de ser o gatilho definidor final de quem puxa quem na compra, e passa a ser apenas um **preparador de terreno (Data Cleaner)** para proteger a memória e o processamento do algoritmo Leiden.

Como essas funções rodariam na prática (Visualização em Pseudocódigo Python):

1. **A Faxina Inicial (`construir_grafo_correlacao`):**
   Continua existindo com o intuito único de barrar ruído absoluto da matriz cruzada (ex: correlações fracas entre 0.00 e 0.15). Se injetarmos na *engine* do Leiden um "Grafo Denso Completo" onde 100% das ações desenham arestas com 100% da bolsa, a matemática Laplaciana travará a CPU em anos de loop retroativos.
   ```python
   # O Limiar atua deletando lixo relacional e entregando um pano limpo
   if abs(correlacao) > limiar_correlacao:
       grafo.add_edge(acao_A, acao_B, weight=correlacao)
   ```
   **Resultado Diário:** O Leiden recebe um mapa polido onde apenas laços de relevância estatística continuaram de pé.

2. **O Novo Coração da Lógica (`detectar_comunidades_leiden`):**
   Com o grafo saneado em mãos, nós extraímos os continentes absolutos com um novo pacote (adicionado no `shell.nix` como `cdlib` ou `leidenalg`). 
   ```python
   importências = algorithms.leiden(grafo_filtrado)
   # A library processa e devolve qual é o "Silo" aglutinado de cada ação:
   # Exemplo = {'VALE3': Cluster_1, 'CSNA3': Cluster_1, 'ITUB4': Cluster_8...}
   ```

3. **A Extinção da Média Vizinha de Grau-1 (`calcular_sinal_grafo`):**
   Aqui é onde a caça cega puramente matemática morre e entra o escopo econômico. O cálculo atraso convergente do Spillover agora puxa da estrutura macro.
   ```python
   # COMO É HOJE FICA PARA TRÁS
   # amigos = list(grafo.neighbors("ITUB4")) # --> Resultava apenas em BBDC4 e SANB11
   
   # COMO FICA:
   meu_cluster = mapeamento_leiden["ITUB4"] # O Leiden atesta que ITUB4 pertence ao Silo "Cluster_8" (Bancos Gerais)
   todas_acoes_do_silo = [acao for acao, clst in mapeamento_leiden.items() if clst == meu_cluster]
   
   # O Spillover se defende do ruído batendo o retorno da ITUB contra TODO o cluster. (Diluindo quedas falsas isoladas)
   sinal_spillover = media_retorno(todas_acoes_do_silo) - retorno_proprio("ITUB4")
   ```

---

## 3. Apresentação e Visualização na Aplicação (Streamlit)

Não há utilidade do rigor científico se os julgadores não puderem visualizá-lo em tela explodindo clareza (Como diz no edital: *"O mais importante é a clareza do raciocínio"*). Adicionaremos 3 elementos à interface em `app_grafo.py`:

### Elemento I: O Heatmap Temporal de Incerteza (Gráfico de Modularidade Q)
* **Design:** Um gráfico de área (linha preenchida) abaixo do gráfico do seu Saldo da Conta de Capital.
* **Leitura Visual:** O eixo variará de 0 até 1.0 (Valores do `Q`).
* **Interação e Clareza:** Poderemos plotar sombras laranjas/vermelhas se o "Q < 0.3". O Investidor baterá o olho, verá o gráfico laranjado despencando de qualidade em Março/2020 (Crise do Corona Crash) e atestará perfeitamente o porquê do nosso robô ter decidido "ficar de fora da bolsa" naquele mês incerto e opaco.

### Elemento II: O Relatório Diário de Coesão (`N_Clusters`)
* **Design:** No painel lateral, uma métrica de KPI `delta` exibindo: "Comunidades Identificadas Hoje: 6".
* **Leitura Visual:** Durante quedas abruptas de 6 comunidades para apenas 1 comunidade monolítíca global, é visível que o mercado está sofrendo de histeria coletiva onde as teses estatísticas caem por água abaixo e ativos dissimilares se correlacionam 100%.

### Elemento III: Botão Interativo e Visualização Topológica 
* **Design:** Ao lado da curva de capital atual, existirá a aba secundária chamada `[🔬 Visão do Radar: Raio-X Leiden]`.
* **Leitura Visual:** Ali usaremos uma biblioteca como `pyvis` ou `matplotlib` para renderizar o Market Graph (Teia em Formato Físico) do último dia do backtester (Datestamp). Os *Nodes* estarão circulados com Cores Distintas baseados na classificação macro do pacote Leiden! O analista girará as bolinhas vendo precisamente a perfeição com que a Vale está separada do Banco do Brasil.

Isso sela 100% da exigência do pilar de *Rigor Metodológico* do Edital. Estratégia coesa, justificativa matemática, visualização instintiva na UI e controle absoluto sobre comportamentos esdrúxulos!
