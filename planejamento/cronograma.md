# Cronograma — Pré-relatório (Desafio Itaú Quant AI 2026)

Prazo: pré-relatório entregue até **31/07/2026**. Hoje: **24/07/2026** (7
dias corridos).

> **Status atualizado:** os itens 1-6 do `IMPLEMENTACAO.md` (correção do
> `requirements.txt`, filtro de custo, métricas de risco, benchmark
> equal-weight e filtro de liquidez) já estão concluídos e integrados ao
> `app_grafo.py`. Os blocos de "Qui 24/07" a "Dom 27/07" abaixo, na parte
> de implementação técnica, estão portanto feitos — falta rodar o
> backtest final com esses ajustes e seguir para a análise dos
> resultados.

## Decisão de fluxo: relatório ou backtest primeiro?

Nenhum dos dois isoladamente — **paralelizar por tipo de conteúdo**:

- O que **não depende de resultado** (hipótese, metodologia, dados
  usados, uso de IA generativa) pode ser escrito desde já, porque não
  muda com o backtest.
- O que **depende de resultado** (retorno, Sharpe, drawdown, comparação
  com benchmark, análise crítica) só pode ser escrito depois de rodar o
  backtest com as correções mínimas (métricas de risco e benchmark ainda
  não existem no código hoje — ver `IMPLEMENTACAO.md`). Escrever essa
  parte cedo demais gera retrabalho que não cabe em 7 dias.

Risco a evitar: deixar a implementação técnica para o fim e não sobrar
tempo para rodar e revisar os números antes do dia 31.

## Cronograma diário

| Dia | Foco principal | Entregável do dia |
|---|---|---|
| **Qui 24/07** (hoje) | Implementar itens 1-2 do `IMPLEMENTACAO.md`: corrigir `requirements.txt` e o filtro de custo em `backtest_grafo`. Em paralelo, escrever as seções do relatório que não dependem de resultado: hipótese, contexto/problema, metodologia (grafo de correlação, passo a passo), dados usados (B3 COTAHIST) e branding do robô. | Ambiente rodando sem erro; rascunho das seções estáticas do relatório. |
| **Sex 25/07** | Implementar itens 3-5: métricas de risco (Sharpe, volatilidade, drawdown) e benchmark equal-weight, integrados ao `app_grafo.py`. | App exibindo as 4 métricas de risco + gráfico comparativo com benchmark. |
| **Sáb 26/07** | Baixar/atualizar dados reais via `b3_cotahist.py` (se necessário) e rodar o primeiro backtest completo com os números corrigidos. Anotar resultados brutos, mesmo preliminares. | Primeira rodada de resultados reais (retorno, Sharpe, drawdown, benchmark). |
| **Dom 27/07** | Implementar item 6 (filtro de liquidez) e rodar o backtest novamente. Se sobrar tempo, checagem manual rápida de sensibilidade (2-3 combinações de janela/limiar, sem precisar do grid completo do item 9). | Resultados "limpos", defensáveis se perguntarem sobre liquidez. |
| **Seg 28/07** | Análise crítica dos resultados: o que funcionou, o que não funcionou, comparação honesta com o benchmark, limitações conhecidas (liquidez, custo, robustez fora da amostra ainda não testada via walk-forward). Escrever a seção "Resultados e Análise" com números reais. | Rascunho completo da seção de resultados. |
| **Ter 29/07** | Consolidar o relatório inteiro (seções estáticas do dia 24 + seção de resultados do dia 28), escrever conclusão e próximos passos, revisar aderência ao checklist do Anexo A do edital (regras objetivas, dados consistentes, backtest funcional, análise crítica, clareza) e à seção obrigatória de uso de IA generativa (onde e como foi usada). | Primeira versão completa do pré-relatório. |
| **Qua 30/07** | Revisão fina: clareza de escrita, consistência entre texto e números, checagem cruzada de que nada no relatório cita métricas que o app não calcula. Se possível, revisão por alguém de fora do time. | Versão final revisada. |
| **Qui 31/07** | Buffer para imprevistos + envio. Não planejar trabalho novo neste dia. | Entrega. |

## Por que essa ordem, e o que fica de fora de propósito

- Os itens 7-9 do `IMPLEMENTACAO.md` (walk-forward, baseline aleatório,
  grid de sensibilidade) **não entram** neste cronograma de 7 dias. São
  diferenciais de rigor estatístico mais relevantes para as fases
  eliminatórias seguintes (quartas de final em diante, com mais tempo
  disponível), não para o pré-relatório. Tentar encaixá-los agora é o
  erro mais comum nesse tipo de prazo: gastar tempo em robustez avançada
  e chegar sem relatório escrito.
- As extensões metodológicas do `PROXIMOS_PASSOS.md` (MST, centralidade,
  detecção de comunidades, GNN) também ficam fora — o edital deixa claro
  que a avaliação do pré-relatório valoriza clareza metodológica e
  análise crítica mais do que sofisticação do modelo: *"não é sobre fazer
  o modelo mais complexo — é sobre fazer um modelo bem pensado, bem
  testado e bem explicado."*
- Por isso os 7 dias são investidos em consolidar bem os itens 1-6 do
  `IMPLEMENTACAO.md` (o mínimo de rigor: métricas de risco, benchmark,
  correção de custo, filtro de liquidez) em vez de perseguir
  complexidade adicional.