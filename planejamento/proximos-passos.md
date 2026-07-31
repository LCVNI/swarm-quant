# Próximos Passos — Estratégia de Grafo de Correlação (B3)

Roadmap priorizado para levar o projeto de "backtest funcional" a
"backtest defensável perante uma banca quant", alinhado aos critérios do
Desafio Itaú Asset Quant AI 2026 (peso: Modelagem 20%, Backtest 15%,
Análise dos resultados 15%).

Organizado por prioridade, não por complexidade — os primeiros itens têm
o maior retorno por esforço.

---

## Prioridade 1 — Bloqueadores e rigor mínimo de backtest ✅ concluída

Sem isso, o projeto não rodaria de ponta a ponta ou não resistiria a uma
pergunta básica da banca sobre risco. Todos os itens abaixo já estão
implementados no código atual.

- [x] **Adicionar `requests` ao `requirements.txt`** — feito.
- [x] **Métricas de risco ajustado** — `calcular_metricas_risco` em
  `grafo_estrategia.py`, exibida em `app_grafo.py`: retorno anualizado,
  volatilidade anualizada, Sharpe (com taxa livre de risco configurável) e
  drawdown máximo.
- [x] **Comparação com benchmark** — `calcular_benchmark_equalweight`
  (proxy equal-weight do universo de ações), plotado junto com a evolução
  do capital da estratégia em `app_grafo.py`.
- [x] **Corrigir o filtro de custo** em `backtest_grafo` — o custo fixo de
  corretagem agora entra no filtro, proporcionalizado por
  `capital_max_por_acao`.
- [x] **Filtro de liquidez** — `filtrar_liquidez` em `grafo_estrategia.py`,
  exposto em `app_grafo.py` com contagem de tickers mantidos.

## Prioridade 2 — Robustez estatística

Ataca diretamente o critério "Backtest: rigor e mitigação de vieses".

- [ ] **Walk-forward / múltiplos períodos automatizado** — hoje o app só
  avisa no texto para "rodar em vários períodos manualmente". Automatizar:
  rodar o backtest em N janelas (ex.: por ano, ou blocos móveis) e reportar
  a distribuição de resultados, não um número único.
- [ ] **Teste de significância do sinal** — comparar o sinal de spillover
  contra um baseline aleatório (ex.: comprar top_n ações aleatórias no
  mesmo dia) para checar se a diferença de retorno é estatisticamente
  relevante e não ruído.
- [ ] **Sensibilidade de parâmetros** — variar janela de correlação e
  limiar em grade (grid) e mostrar como o resultado muda, para demonstrar
  que a estratégia não foi ajustada (overfit) a uma combinação específica.

## Prioridade 3 — Integração e usabilidade

Não afeta a nota diretamente, mas facilita demo e reduz risco de erro
manual na apresentação.

- [ ] **Unificar pipeline** — hoje é: rodar `b3_cotahist.py` no terminal →
  subir o arquivo manualmente no Streamlit. Dá para adicionar um botão no
  próprio `app_grafo.py` que dispara o download/atualização de dados
  direto (com aviso de tempo de execução).
- [ ] **Cache dos grafos por data** — `construir_grafo_correlacao` é
  chamado uma vez por decisão dentro do loop; para backtests de período
  longo isso pode ficar lento. Vale perfilar antes de otimizar
  prematuramente.

## Prioridade 4 — Extensões metodológicas (roadmap de pesquisa)

Já listadas no `readme.md` original como direção futura da linha "market
graph" — não são necessárias para uma entrega válida, mas são o caminho
natural de aprofundamento caso o tempo permita, e ajudam no critério
"Conceito da estratégia (criatividade e inovação)":

- [ ] **Árvore Geradora Mínima (MST)**, abordagem de Mantegna — simplifica
  o grafo de correlação numa estrutura hierárquica, popular em
  econofísica.
- [ ] **Métricas de centralidade** (PageRank, autovetor, betweenness) —
  ranquear ações por importância estrutural na rede, não só por
  vizinhança direta.
- [ ] **Detecção de comunidades** (ex.: Louvain) — identificar clusters de
  ações que se movem juntas, indo além da vizinhança de 1 salto.
- [ ] **Graph Neural Networks** — linha mais complexa, com risco de
  overfitting maior; só faz sentido depois que as versões mais simples
  estiverem validadas e bem documentadas.

## Prioridade 5 — Documentação para a banca

- [ ] **Registrar o uso de IA generativa** — o edital exige (Seção 8) que
  a equipe descreva objetivamente em qual etapa a IA foi usada e qual foi
  a contribuição prática (ex.: revisão de código, estruturação da
  documentação, análise de resultados). Vale já anotar isso à medida que
  for usando, para não reconstruir depois.
- [ ] **Esclarecer o status do PDF "Macro Nexus Allocation"** — se ainda
  circular como material do projeto, deixar explícito que representa a
  tese anterior e não a estratégia atual (ver `README.md`, seção 5), para
  evitar que a banca avalie o projeto por um documento desatualizado.

---

**Resumo de foco para o pré-relatório (31/07/2026):** a Prioridade 1 está
concluída — Sharpe, drawdown, benchmark, correção do filtro de custo e
filtro de liquidez já estão implementados e integrados ao `app_grafo.py`.
O foco agora é rodar o backtest com esses ajustes sobre os dados reais e
escrever a análise crítica dos resultados. Os itens de Prioridade 2
(walk-forward, teste de significância, sensibilidade de parâmetros)
seguem fora do escopo deste pré-relatório, reservados para as fases
eliminatórias seguintes.