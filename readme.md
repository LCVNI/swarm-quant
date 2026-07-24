# Estratégia de Grafo de Correlação (B3) — Desafio Itaú Quant AI 2026

Estratégia quantitativa desenvolvida por Vagner para o Desafio Itaú Asset
Quant AI 2026. Usa teoria de grafos aplicada a correlação entre ações da B3
(market graph) para gerar sinais de trading, sem machine learning.

> **Aviso importante:** estratégia estatística experimental. Não é
> recomendação de investimento. Rode o backtest em múltiplos períodos antes
> de tirar qualquer conclusão — um bom resultado isolado pode ser só sorte.

---

## 1. Ideia central (em uma frase)

Ações que estão fortemente correlacionadas historicamente tendem a se mover
em bloco. Quando uma ação "atrasa" em relação ao retorno recente do seu
grupo correlacionado, a estratégia aposta que ela vai convergir — e compra.

## 2. Metodologia

Baseada na linha de pesquisa **market graph** (Boginski, Butenko & Pardalos,
2003/2005), da literatura de econofísica/redes complexas aplicada a
mercados financeiros.

**Passo a passo, para cada data de decisão:**

1. **Construção do grafo** — calcula a correlação de Pearson
   (`pandas.DataFrame.corr()`) entre os retornos diários de cada par de
   ações, numa janela móvel de *N* pregões (padrão: 60), usando **somente
   dados anteriores à data de decisão** (sem vazamento de informação
   futura).
2. **Threshold** — só existe aresta entre duas ações se `|correlação| ≥
   limiar` (padrão: 0,3). É a parte "market graph" propriamente dita: um
   grafo binário construído por corte de correlação, aqui com o peso da
   aresta preservado (variação ponderada do market graph original).
3. **Sinal de decisão (spillover)** — para cada ação, calcula a média
   ponderada (peso = força da correlação) do retorno recente dos seus
   vizinhos diretos (1 salto) e compara com o retorno recente da própria
   ação. Sinal alto = o grupo já subiu, a ação ainda não acompanhou.
4. **Seleção e alocação** — filtra ações cujo sinal supera o custo
   estimado de ida e volta, ordena por sinal e aloca capital via algoritmo
   guloso (greedy), respeitando um teto de capital por ação.
5. **Realização** — mantém a posição por um horizonte fixo (padrão: 5
   pregões) e realiza o resultado com o retorno efetivamente observado.

**O que a estratégia *não* usa (de propósito, por ora):** árvore geradora
mínima (Mantegna), métricas de centralidade (PageRank, betweenness),
detecção de comunidades (Louvain) ou Graph Neural Networks. É a versão mais
simples da família "market graph": limiar de correlação + média ponderada
da vizinhança direta. Veja `PROXIMOS_PASSOS.md` para o roadmap dessas
extensões.

## 3. Estrutura do repositório

```
.
├── b3_cotahist.py       # Pipeline de dados: baixa e converte COTAHIST da B3
├── grafo_estrategia.py  # Lógica da estratégia (grafo, sinal, backtest, IR)
├── app_grafo.py         # Interface Streamlit
├── requirements.txt     # Dependências Python
├── config.toml          # Configuração do Streamlit (upload até 1 GB)
└── readme.md            # Este arquivo
```

### `b3_cotahist.py` — coleta de dados

Baixa os arquivos anuais **COTAHIST** (série histórica oficial de cotações
da B3, formato de largura fixa) e converte para Parquet ou CSV.

```bash
# Baixar e converter 2020-2026 em parquet
python b3_cotahist.py --inicio 2020 --fim 2026 --formato parquet

# Filtrar só alguns tickers
python b3_cotahist.py --inicio 2025 --fim 2026 --tickers PETR4 VALE3 ITUB4

# Consolidar todos os anos num único arquivo
python b3_cotahist.py --inicio 1986 --fim 2026 --formato parquet --consolidar
```

Roda de forma independente, via linha de comando — **não** é chamado
automaticamente pelo app Streamlit. O resultado (arquivo `.parquet` ou
`.csv` em `dados_b3/processed/`) é o que você sobe manualmente no app.

### `grafo_estrategia.py` — núcleo da estratégia

Módulo **autossuficiente**: não importa nada de um eventual `core.py` de
outro time, de propósito, para permitir que times diferentes (grafo vs.
ML) evoluam sem se acoplar. Por isso duplica localmente as fórmulas de
custo, alocação e imposto (mesma fórmula, mesma fonte legal).

Principais funções:

| Função | O que faz |
|---|---|
| `carregar_dados` | Lê o parquet/csv e filtra só mercado à vista (`tipo_mercado == 10`) |
| `construir_features_grafo` | Calcula `retorno_1d`, `retorno_5d` e `retorno_futuro` (shift para trás, usado só na realização) |
| `construir_grafo_correlacao` | Monta o grafo de correlação usando só dados passados |
| `calcular_sinal_grafo` | Calcula o sinal de spillover por ação |
| `backtest_grafo` | Loop de simulação completo: decide, aloca, realiza, avança |
| `calcular_ir_mensal` | Apuração de IR mensal (regra de swing trade, Lei 11.033/2004, Art. 3º, II) |

### `app_grafo.py` — interface

Streamlit puro. Sobe o arquivo processado, expõe todos os parâmetros
(janela de correlação, limiar, horizonte, capital, custos de corretagem,
impostos) e roda `backtest_grafo` sob demanda. Custos e impostos começam
**zerados** por padrão — o usuário preenche com os valores reais da sua
corretora e situação fiscal.

## 4. Como rodar

```bash
pip install -r requirements.txt
pip install requests   # necessário para b3_cotahist.py — ver seção 6

# 1. Baixar dados (uma vez)
python b3_cotahist.py --inicio 2018 --fim 2026 --formato parquet

# 2. Rodar o app
python -m streamlit run app_grafo.py
```

No app: suba o parquet gerado no passo 1 → clique em "Carregar dados" →
ajuste os parâmetros → clique em "Rodar backtest".

## 5. Relação com outros documentos do projeto

- **`Macro_Nexus_Allocation__Trinecore.pdf`**: descreve uma estratégia
  **anterior e diferente** desta — alocação dinâmica entre ações,
  debêntures e renda fixa via um "grafo macroeconômico" (Selic, IPCA, PIB,
  crédito etc., com dados do BCB/IBGE/Tesouro/ANBIMA). Essa proposta foi
  **substituída** pela estratégia de correlação entre ações implementada
  aqui. Os dois documentos não são compatíveis entre si — se o PDF ainda
  circular como material do projeto, é preciso deixar claro que ele
  representa a tese antiga, não a atual.
- **`Edital_QuantAI2026_ItauAsset.pdf`**: edital oficial do desafio. Esta
  estratégia atende aos requisitos de hipótese testável, dados públicos e
  verificáveis (B3), e backtest sem vazamento de informação futura. Ver
  `PROXIMOS_PASSOS.md` para os pontos que ainda faltam para atender bem os
  critérios de avaliação (peso em "Backtest" e "Análise dos resultados").

## 6. Limitações conhecidas

- `requirements.txt` não lista `requests`, que é usado por
  `b3_cotahist.py` para baixar os arquivos da B3 — instale manualmente
  (`pip install requests`) ou adicione ao arquivo.
- O filtro de custo mínimo (`sinal_spillover > custo_pct_ida_volta`)
  considera apenas a parte percentual do custo de transação, ignorando a
  corretagem fixa. Se você configurar corretagem fixa > 0, o filtro pode
  subestimar o custo real de operações pequenas.
- Não há filtro de liquidez: ações pouco negociadas podem gerar
  correlações espúrias e preços de fechamento pouco representativos de uma
  execução real.
- O app não calcula métricas de risco ajustado (Sharpe, volatilidade,
  drawdown máximo) nem compara o resultado com um benchmark (ex.:
  Ibovespa). Ver `PROXIMOS_PASSOS.md`.

## 7. Fontes

- Boginski, V.; Butenko, S.; Pardalos, P. M. (2003, 2005) — *Market graph*,
  base metodológica do grafo de correlação.
- B3 — tabela de tarifas: https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/
- Receita Federal — regra de swing trade (IR/IRRF): https://www.gov.br/receitafederal
- Lei 11.033/2004, Art. 3º, II — isenção de IR em vendas mensais até
  R$ 20.000 (ações, regra de swing trade).