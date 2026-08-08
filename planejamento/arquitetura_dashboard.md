# Arquitetura Visual do Dashboard Institucional (Streamlit)

A melhor forma de convencer bancas avaliadoras de campeonatos Quants não é através de tabelas extensas, mas contextualizando o Retorno absoluto com a mecânica analítica que o defendeu. Para isso, precisamos reestruturar a interface para que as **métricas topológicas de Leiden conversem diretamente com a performance descrita nos indicadores de desempenho financeiro**.

Abaixo está a planta de integração da nossa UI no `app_grafo.py`.

---

## 1. O Que Já Temos e Seus Problemas Atuais
Atualmente o nosso backtester entrega na saída as matrizes `resumo` e `operacoes` abastecidas com:
* Evolução do Capital (`capital_apos_periodo`)
* Lucro por período (`lucro_periodo`)
* Densidade via Arestas (`n_arestas_grafo`)
* Modularidade Científica (`leiden_modularidade` - recém-adicionado)
* Quantidade de Agrupamentos (`leiden_qtd_clusters` - recém-adicionado)

⚠️ **Problema Físico:** Se plotarmos isso amontoado numa tabela crua do Pandas (`st.dataframe`), o sentido causal desaparece. O avaliador precisa enxergar visualmente a relação de "Causa-Efeito" (Exemplo: "O número de clusters caiu drasticamente na semana X e isso evitou um Drawdown profundo na semana Y").

---

## 2. A Injeção de Risco (Métricas Faltantes)
Como elencado no material de `indicadores_desempenho.md`, adicionaremos blocos sintéticos baseando-se no que a *Norn* gerou:
* **Win Rate & Profit Factor:** Baseado primariamente no array de `operacoes`.
* **Sharpe & Maximum Drawdown (MDD):** Processados em cima da oscilação do `capital_apos_periodo`.
* *(Passo a Ser Injetado)*: Importação da rotina SELIC local e IBOVESPA parquetizada para destravarmos com exatidão o "Alpha de Jensen" e o "Beta de Mercado".

---

## 3. O Layout Tático da Nova Aplicação 
Para que a tese flua da estrutura de Risco para a Rentabilidade, o Dashboard adotará o seguinte mosaico visual usando Abas e Gráficos Composicionais (`Plotly`):

### 🏁 Seção de Liderança (Header com KPIs Institucionais)
Logo no topo do App, independentemente de testes interativos, usamos um banner de `st.columns(5)` e injetamos widgets `st.metric()` cravando o escudo do robô:
* **Card 1 (Retorno Acumulado vs IBOV):** "Rentabilidade Bruta: 145% vs 45% (Benchmark)"
* **Card 2 (Drawdown Máximo):** "Max Drawdown: -12%" *(Cor vermelha para provar contenção).*
* **Card 3 (Sharpe / Sortino):** "Sharpe: 1.45"
* **Card 4 (Mecânica):** "Win Rate: 65% | Profit Factor: 1.8"
* **Card 5 (Estado do Leiden Ponto Final):** "Q Global: 0.61 (Mercado Estável)"

### 🌌 Área Central (Minimalismo e Correlação Visual Nativa)
Não vamos isolar a métrica da econofísica da métrica do dinheiro, mas também não usaremos motores tridimensionais pesados como o Plotly. Faremos o uso elegante de elementos nativos do Streamlit (`Altair` puro).
* **Curva de Capital Causa-Efeito (`st.line_chart`):** O gráfico exibirá a evolução geométrica do patrimônio da Norn sobreposto a **dois Benchmarks (Três Linhas Coexistentes)**: a volatilidade direcional do **Ibovespa** (Renda Variável) e a curva de juros da **Renda Fixa / CDI Acumulado**. Plotar as 3 curvas competindo ponta a ponta de forma plana comprovará instantaneamente aos juízes se o robô extrai Alpha real sobre a renda fixa enquanto mitiga os solavancos caóticos do IBOV.
* **O Risco Empilhado (`st.area_chart` Oculto do Leiden):** Exatamente abaixo da curva de capital, e em proporções fluídas, alinhamos um gráfico de área preenchida mapeando risco contínuo da rede (ou a modularidade `Q`). 
  * *O Xeque-Mate Mental:* Mesmo sendo dois componentes visuais independentes e ultraleves, a proximidade chapada na tela (`Stacking`) permite que a Banca conecte as curvas automaticamente. Eles lerão a queda na modularidade da rede na prancha debaixo avisando sobre o risco perigoso na Curva do IBOV na prancha de cima.

### 🔬 Painel de Abas Interativas (A Unificação Definitiva de Dados Históricos)
Uma dúvida comum é: *Esse modelo nativo super rápido apaga os dados brutos cruciais de auditoria?*
**A resposta é não! Nós unificamos na tela em tempo ultrarrápido.** 
Isolados nos bastidores do sistema de abas (`st.tabs`), garantimos navegabilidade técnica e zero tráfego morto:

* **Aba 1 (📊 KPIs e Tese Nativa):** A face frontal (Métricas + Gráficos Nativos Triplos). O Pitch Institucional livre de delay.
* **Aba 2 (🌌 Radar Leve - Raio-X):** Injeção do Mapa Gravitacional do último Frame sem dependências web asfixiantes.
* **Aba 3 (🧾 Lançamentos e Operações Diárias):** O mesmíssimo Dataframe cru que nós tínhamos (`st.dataframe(operacoes)`), preservando o preço exato, Custo, e IR de cada compra e venda disparada pela Norn para o júri auditar que não estamos roubando nos impostos.
* **Aba 4 (🗓️ Resumo por Período Acumulado):** O Log consolidado de cada rodada do laço For do código, preservando a contagem de nós, de capital líquido, etc. Nada vai para o lixo!

Essa amarração converte uma equação de física abstrata numa máquina legível, corporativa e visualmente inatacável nos pré-requisitos solicitados de interpretabilidade e lógica de dados do edital.

---

## 4. Defesa Teórica no Relatório Final (O Argumento do Raio-X)

Apresentar um grafo complexo cheio de nós e arestas coloridas (Pyvis) é esteticamente impactante na UI, mas **tecnicamente perigoso/inútil** se não soubermos explicar para a banca *o que aquilo controla e por que está ali* de forma direta. No Relatório de Finalização, o Raio-X de Comunidades será o nosso principal álibi visual para explicar a inteligência do robô de forma didática.

**Como explicaremos isso estruturalmente (O Script do Pitch):**

1. **A Verdade Oculta dos Setores:** Argumentaremos que analistas humanos costumam agrupar e operar a bolsa através de rótulos engessados (Ex: "Fica Lançado em Varejo, Fica Comprado em Bancos"). A nossa visualização prova que o dinheiro não obedece nomes de etiqueta. O algoritmo Leiden detecta **quem realmente capta e perde dinheiro junto na veia no mercado**. As fatias do nosso raio-x mostram no dado bruto que frequentemente uma empresa de Logística pertence matematicamente à constelação do Varejo pelas correlações fortes ocultas.
2. **A Blindagem do Sinal (Sustentação):** Explicaremos para o júri usando o radar: *"Vejam a Constelação Azul. Se o nosso algoritmo identificar este grupo de 20 empresas bilionárias fluindo interconectadas para uma alta generalizada, e constatar que apenas 1 delas ficou estranhamente deixada para trás, a Norn sinaliza Compra Imediata. Ela compra ancorada na gravidade subjacente (Força G) destas 19 gigantes empurrando a lei do preço à convergir para cima"*. 
3. **Mitigação do Risco Visível:** A rede prova que rejeitamos "Falsas Anomalias". Se uma *Penny Stock* (Ação obscura) saltou do nada e caiu, o júri verá que na Constelação do Pyvis esse ativo possivelmente está "voando num vazio escuro" totalmente desconectado das tribos de sustentação seguras, e o nosso filtro não aprovaria essa aposta. A cor e o grupo blindam argumentos de trade instintivos cegos!

---

## 5. Exportação Centralizada (O "One-Click Dossiê")

Atualmente, o gestor sofre fazendo download de arquivos `.csv` isolados e soltos pra analisar a saúde do robô. Para selar o acabamento luxuoso do Dashboard, nós adicionaremos um botão mestre de exportação na lateral: **"⬇️ Gerar Relatório de Auditoria do Fundo"**.

### Qual a Extensão Definitiva? (O Poder do Arquivo `XLSX` Multi-Sheets)
Muitos amadores optam por extrair PDFs cegos, o que impede a banca de testar a veracidade do cálculo dos números. A extensão padrão ouro de relatórios é o **Excel Avançado (`.xlsx`)** alimentado pela engine do `xlsxwriter`.

* **Por que Excel?** O formato `.csv` é cego: ele só suporta uma matriz, quebrando muitas vezes caso o usuário abra em Excel mal configurado. O formato `.xlsx` (turbinado pela dupla `XlsxWriter` + Pandas) gerado nos permite construir um "Book" financeiro de puro luxo na raiz.
* **O Padrão Organizacional do Dossiê:**
   O arquivo constrói as 3 abas separadas milimetricamente lá embaixo (Guias):
   1. **Guia 1 (`KPIs_Contabeis`):** Resumo cravado de vitórias, Sharpe, Beta e o Alpha absoluto. A capa matriz do Relatório.
   2. **Guia 2 (`Mesa_Operacoes_Cruas`):** A tabela minuciosa de Compra Venda e Custos de cada trade (Pra provar cirurgicamente que pagamos e descontamos tudo).
   3. **Guia 3 (`Serie_Temporal_Geral`):** O log diário das curvas que as lógicas gráficas consumirão estatisticamente.

* **Formatação Contábil Nativa Injetada:** A mágica oculta da *engine* no backend é forçar que a robô *Norn* não cuspa as tabelas com colunas sujas do tipo Float (ex: "Capital: `1000.51892`"). Nós forçamos a exportação já travada como Dinheiro Contábil: **`R$ 1.000,52`**. O avaliador abre e a planilha da operação de arbitragem parece polida por um contador de Risco Sênior.

* **Gráficos Nativos Embutidos (🏆 Data Storytelling Supremo):** Com a planilha gerada, os gráficos já estariam formados! O juiz da Asset não precisará desenhar nada na unha. O próprio Python usando o comando `workbook.add_chart({'type': 'line'})` mapeia apontando pros dados ocultados da 'Guia 3' e desenha um visual vivo na nossa Capa de Apresentação ('Guia 1'). Efeito: Ao realizar o duplo-clique no arquivo `Relatorio_Norn.xlsx`, o inspetor tem num segundo uma tela exibindo o gráfico vibrante da Estratégia ultrapassando o Ibovespa, integrado a tabela limpa!

Isso sela a eficiência do sistema: Fica na interface do Streamlit apenas um botão gigante **[⬇️ Baixar Dossiê Relatório Completo]** na barra lateral, envelopando todos os KPIs, gráficos nativos montados e tabelas separadas num único arquivo indissociável de auditoria mestre!
