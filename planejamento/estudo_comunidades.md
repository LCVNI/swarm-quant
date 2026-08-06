# Estudo de Detecção de Comunidades (Market Graph)

Antes de adotarmos cegamente o Algoritmo de Louvain para definir os nossos clusters e calcular a distorção do *Spillover*, é imperativo avaliarmos os métodos disponíveis na teoria de grafos. A escolha do algoritmo não muda só a velocidade do código, mas altera fundamentalmente a *física da formação de preço* que a Itaú Asset irá avaliar.

Abaixo destrinchamos as abordagens possíveis, as métricas e vantagens que derivam de cada uma delas.

---

## 1. Comparativo de Algoritmos de Detecção (Clustering)

### A) Modularity Optimization: Louvain vs. Leiden
* **O Algoritmo de Louvain:** 
  * **Funcionalidade:** Ele tenta maximizar iterativamente a "Modularidade" (`Q`), comparando a densidade interna de um grupo de ações com a densidade esperada se as conexões fossem aleatórias.
  * **Problemas:** Sofre do que chamamos de *Resolution Limit* (Limite de Resolução). O Louvain tende a aglutinar clusters pequenos genuínos em um único macrogrupo gigante (" engolindo" setores menores, como Educação, injetando-os, equivocadamente, no Varejo).
* **O Algoritmo de Leiden (O Sucessor do Louvain):**
  * **Funcionalidade:** Evolução direta do Louvain desenvolvido em 2019. Ele garante que as comunidades formadas sejam estritamente conectadas e resolve o problema do limite de resolução, sendo capaz de separar setores de mercado com muito mais pureza.
  * **Veredito:** Para a B3 (mercado dominado por financeiro/commodities vs microssetores), **Leiden é exponencialmente de melhor aceitação que Louvain** no estado da arte atual.

### B) Divisivos: Algoritmo de Girvan-Newman
* **Funcionalidade:** Diferente do Louvain/Leiden (que montam debaixo pra cima), o Girvan-Newman desmonta a rede de cima para baixo. Ele remove sucessivamente as arestas com o maior **Betweenness Centrality** (as pontes entre setores). Imagine que ele corta a ponte que liga o setor elétrico ao de saúde, separando os dois.
* **Prós e Contras:** Gera agrupamentos incrivelmente puros e interpretáveis, mas é **computacionalmente caríssimo** (`O(m²n)`). Rodar isso em um backtest diário ao longo de 10 anos pode inviabilizar o processamento e travar a infraestrutura.

### C) Propagação: Label Propagation Algorithm (LPA)
* **Funcionalidade:** Cada ação recebe um selo único no início. A cada rodada, "cada ação vota no selo que seus vizinhos mais usam".
* **Prós e Contras:** É insanamente rápido (`O(m)` linear). O grande perigo? Ele é **não-determinístico**. Se rodarmos o backtest 3 vezes na mesma janela temporal, ele pode agrupar as ações de forma levemente diferente. A Itaú Asset reprovaria imediatamente a falta de reproducibilidade de dados.

### D) Spectral Clustering
* **Funcionalidade:** Usa "autovalores" da Matriz Laplaciana do grafo para enxergar divisões espaciais.
* **O Perigo Oculto:** Ele requer que nós falemos previamentee um parâmetro `K` (No. de Comunidades que queremos encontrar). Como a B3 pode ter 5 macrossetores visíveis na calmaria e 1 só gigante na crise global, amarrar `K` no algoritmo nos impediria de captar a dinâmica fluída de contração e expansão do Grafo Financeiro ao longo do tempo.

---

## 2. Métricas de Topologia (Os Trunfos para a Estratégia)

Se adotarmos o **Leiden** ou **Louvain**, eles nos presentearão instantaneamente com dados maravilhosos para usarmos como travas condicionais do nosso sistema.

### 📌 Modularidade do Sistema (Índice `Q`)
* **O que é:** Um valor que vai de -0.5 a 1.0. Mede se as ações estão agrupadas fortemente, ou se a bolsa está uma "sopa aleatória caótica".
* **A Funcionalidade na Estratégia:** 
  * Se o Market Graph de hoje apontar um `Q` muito baixo (ex: `0.1`): O sinal da bolha não significa nada, as "amizades de setor" estão fracas e tudo é ruído instável. **Regra Adicionada: Impedir compras de Spillover**.
  * Se o Market Graph apontar `Q` alto (ex: `0.7`): A bolsa está rigidamente setorizada. A leitura de defasagens se torna extremamente confiável e robusta. Autoriza aportes mais agressivos.

### 📌 Quantidade de Clusters Formados (`N_Clusters`)
* **O que é:** O rastreamento de quantas macro-comunidades o mercado originou na data (ex: 7 clusters autônomos).
* **A Funcionalidade (Desastre Econômico):** Em crises agudas (como Pandemia de Março/2020), a quantidade de clusters despenca matematicamente. Se o normal da B3 era ter `8` comunidades e subitamente o número cair para `2`, é a prova quântica de que o contágio contaminou todos os ativos irremediavelmente (A famosa citação: *Em uma crise, a correlação de todos os ativos vai para 1*). O backtest pode utilizar o `N_Clusters` caindo como gatilho de defesa absoluto (zerar carteira comprada).

### 📌 Homogeneidade Interna do Cluster (Correlação Intra-Comunidade)
* **O que é:** Onde a ação atrasada está? Se pertencente ao Cluster A, qual a correlação média de todos pertencentes apenas lá dentro? 
* **A Funcionalidade:** Se descobrirmos que a Ação X está defasada no preço do Cluster A, mas o Cluster A tem uma Correlação Média Agrupada baixíssima, a Ação X não é impulsionada firmemente pelos seus membros a convergir. Evitaremos compras em Clusters soltos frouxamente pelo pacote.

---

## Síntese (Ponto de Decisão)
A recomendação técnica, caso avancemos no desenvolvimento do motor comunitário, é adotar o **Algoritmo de Leiden** e abandonar o uso das "vizinhanças imediatas", abraçando as três métricas (`Q`, `N_Clusters`, `Correlação Intra_Cluster`) como um **Risco/Filtro Dinâmico** elegantíssimo antes de calcularmos quem está com o Spillover Positivo no dia!
