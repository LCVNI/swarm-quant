# Estudo Aprofundado: Algoritmos de Detecção de Comunidades para o Desafio Quant AI 2026

Com base nos critérios estabelecidos no Edital do **Desafio Itaú Asset Quant AI 2026** e no **Guia de Primeiros Passos**, o foco do desafio é:
1. **Lógica e Estruturação (20%)**: Modelos sistemáticos, replicáveis e fáceis de explicar prevalecem sobre "caixas-pretas" supercomplexas.
2. **Criatividade e Inovação (20%)**: Trazer um racional econômico forte (ex: uma hipótese inteligente de como o fluxo corre na B3).
3. **Robustez do Backtest (15%)**: O modelo deve ser rápido o suficiente para simular múltiplos regimes de mercado, suportando testes sem explodir computacionalmente.

Enquanto o **Leiden** e o **Louvain** baseiam-se em *Modularidade* (focados na estrutura estática), existem **outras escolas de teoria de redes** que trazem interpretações completamente diferentes—frequentemente mais alinhadas ao conceito monetário de "Spillover" (transbordamento/fluxo).

---

## 1. Infomap (Map Equation)
* **A Teoria Base:** Desenvolvido por Martin Rosvall, é baseado na **teoria da informação**. Enquanto o Leiden se importa com "quais nós têm mais arestas entre si", o Infomap simula um caminhante aleatório (Fluxo de Dinheiro/Informação) viajando pela rede. Ele tenta descrever o caminho da forma mais compacta possível. Quando o visitante passa muito tempo preso num grupo (ex: dinheiro circulando nos bancões), isso vira um cluster.
* **Por que é matador para o Spillover:** Se o seu Grafo for *direcionado* (ex: Causalidade de Granger, Transfer Entropy ou Liderança-Defasagem), o Infomap captura a direcionalidade do choque, enxergando "Sinks" (quem absorve o spillover) e "Sources" (quem gera o spillover).
* **Métricas Interessantes Adicionadas:**
  * **Network Code Length ($L$):** Um substituto do Índice $Q$ (Modularidade). Mede a previsibilidade dos fluxos no mercado. Um Code Length curto significa forte determinismo no fluxo (alta chance de acerto no trade de spillover).
  * **PageRank de Fluxo:** Identifica "Ativos Sorvedouros" (ativos onde todo o pânico ou euforia do setor vai parar, como o PETR4 ou VALE3 em seus pares).

## 2. K-Clique Percolation (Comunidades Sobrepostas)
* **A Teoria Base:** Diferente do Leiden, onde uma ação só tem uma "panelinha", o modelo de Percolação de Cliques permite *Overlapping Communities* (Comunidades Sobrepostas).
* **Por que faz sentido na B3:** Na vida real, a Bolsa BR é cheia de "Bridges" (pontes). **Itaúsa (ITSA4)** pertence ao setor bancário, mas também tem papéis de infraestrutura/saneamento. **Cosan (CSAN3)** é energia, logística e agro. Forçar essas empresas a 1 cluster apaga informações.
* **Métricas Interessantes Adicionadas:**
  * **Grau de Sobreposição (Overlap Ratio):** Quão conectada a Ação X está com diferentes partes do mercado. Ações com alta sobreposição são termômetros de *Contágio Sistêmico*. Se as duas comunidades da ITSA4 entrarem em choque, ela sofrerá duplo impacto e o modelo "zeraria" essa posição preventivamente.
  * **Tamanho do Maior K-Clique:** Em bolhas financeiras, o maior K-Clique costuma crescer absurdamente engolindo o mercado, indicando máxima fragilidade sistêmica.

## 3. Walktrap (Random Walks na Vizinhança)
* **A Teoria Base:** Também utiliza *Random Walks*, focado no princípio de que se você iniciar uma caminhada de 3 a 4 saltos, provavelmente não vai conseguir sair de dentro de uma comunidade densa.
* **Métricas Interessantes Adicionadas:**
  * **Distância de Passos (Walk Distance):** Permite calcular precisamente as "Defasagens Geográficas" no mercado. Exemplo: "O choque que ocorreu em VALE3 hoje, estatisticamente, demora 3 passos (ou 3 dias) para atingir as siderúrgicas menores." — Um racional extremamente atraente para apresentar a uma banca da Itaú Asset.

---

## 2. Ranking e Veredito (Sob a Ótica do Itaú Quant AI 2026)

Recomendação técnica avaliando *Complexidade vs. Replicabilidade vs. Inovação*:

### 🥇 1º Lugar: Infomap (Nota: 9.5/10)
* **Por quê?** Se a tese principal é **Spillover** (que remete a *Direção/Causalidade*, ou seja, o dinheiro saindo de A para B), modularidade simples (Leiden) perde o sentido dinâmico. O Infomap trabalha nativamente com Grafos Direcionados, é linearmente rápido ($O(m)$) para permitir um backtest histórico sem lentidão, e traz um racional teóricobrilhante focado em Fluxo de Capital. Atende maravilhosamente a "Criatividade (20%) e Modelagem (20%)".
* **Desafio:** Exige que a matriz de adjacência (matriz de correlação) do seu Grafo se torne direcionada (ex: quem lidera e quem segue os impulsos de preço).

### 🥈 2º Lugar: Algoritmo de Leiden (Nota: 9.0/10)
* **Por quê?** Caso vocês decidam manter o Grafo via "Correlação/Cointegração Simples" (não direcionado), o Leiden é rei absoluto. Ele é seguro, rigoroso, rápido e gera métricas explicáveis (`Q` e `N_Clusters`). O desafio cita: *"O mais importante não é o nível de complexidade, e sim a clareza do raciocínio..."*. O Leiden é super didático e aprova com facilidade no pilar de Rigor Metodológico.

### 🥉 3º Lugar: Overlapping K-Cliques (Nota: 7.5/10)
* **Por quê?** Conceitualmente fantástico. Mostra maturidade econômica entender que empresas atuam em cross-sectors. O problema? Regras operacionais ficam mais complexas num ambiente com comunidades que se colidem sobrepostas ("*Compro ou não compro ITSA4 se a comunidade 1 manda comprar e a comunidade 2 manda vender?*"). Isso pode gerar sinais confusos (a famosa "caixa-preta" complexa demais e difícil de explicar sem um GenAI sofisticado decifrando as saídas).

### ❌ 4º Lugar: Algoritmos Divisivos (Girvan-Newman) (Nota: 4.0/10)
* **Por quê?** Matematicamente lindos, mas o tempo computacional é exponencialmente mais lento. Em um backtest de estratégia rodando ao longo de anos com rebalanceamento frequente, a infraestrutura da máquina pode não segurar. O backtest falharia por timeout, indo contra o pilar "Testável" do edital.

---
**Conclusão Estratégica:**
Se vocês criarem uma métrica que captura a **direção** do movimento (quem puxa e quem sofre), adotem o **Infomap**. Se continuarem com métricas puramente estáticas e de correlação sem direção, continuem com o **Leiden**, pois as funções dinâmicas do Risco (`Q`, `N_Clusters`) são muito bem-vistas aos olhos institucionais pela sua simplicidade e inteligência.
