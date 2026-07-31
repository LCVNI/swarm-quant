# Implementação — Estratégia de Grafo de Correlação (B3)

Checklist técnico de implementação, em ordem de execução sugerida. Cada
item é autocontido (arquivo, função, lógica, critério de aceite) para
poder ser usado diretamente como instrução para um agente de código.

**Status atual:** itens 1 a 6 (o mínimo para o pré-relatório) estão
✅ **implementados e validados** no código atual. Itens 7 a 9 seguem
propositalmente pendentes — são diferenciais de rigor estatístico para as
fases eliminatórias seguintes, não para o pré-relatório.

Contexto do projeto: `grafo_estrategia.py` contém a lógica pura (sem UI),
`app_grafo.py` é a interface Streamlit que consome
`grafo_estrategia.backtest_grafo`. Manter essa separação em todas as
mudanças abaixo — nenhuma lógica de cálculo deve entrar em `app_grafo.py`.

---

## 1. ✅ Corrigir `requirements.txt`

**Arquivo:** `requirements.txt`

**Ação:** adicionar a dependência `requests`, usada por `b3_cotahist.py`
e ausente do arquivo atual.

**Conteúdo final esperado:**
```
pandas
numpy
streamlit
pyarrow
networkx
requests
```

**Critério de aceite:** `pip install -r requirements.txt` seguido de
`python b3_cotahist.py --inicio 2025 --fim 2026` não deve falhar por
`ModuleNotFoundError: requests`.

---

## 2. ✅ Corrigir filtro de custo em `backtest_grafo`

**Arquivo:** `grafo_estrategia.py`, função `backtest_grafo`.

**Problema:** a linha
```python
custo_pct_ida_volta = 2 * (taxa_b3 + corretagem_percentual * (1 + iss_pct))
```
ignora `corretagem_fixa`, que não é percentual. Ações de preço baixo com
corretagem fixa configurada passam pelo filtro `sinal_spillover >
custo_pct_ida_volta` mesmo quando o custo fixo, em termos percentuais do
valor da posição, é maior que o sinal.

**Ação:** o filtro de corte por sinal precisa ser calculado por candidato
(pois depende do valor da posição), não como uma constante global. Duas
opções:

**Opção A (recomendada — mover o filtro para depois de estimar o valor da
posição):**
1. Antes de aplicar o filtro `sinal[sinal["sinal_spillover"] >
   custo_pct_ida_volta]`, calcular o valor aproximado da posição por ativo
   usando `capital_max_por_acao` (o teto por ação já configurado) como
   proxy do tamanho da posição.
2. Calcular `custo_fixo_pct_estimado = 2 * corretagem_fixa /
   capital_max_por_acao` (ida + volta) e somar a `custo_pct_ida_volta`
   antes de filtrar.
3. Renomear a variável para `custo_pct_ida_volta_estimado` para deixar
   claro que é uma aproximação baseada no teto de posição, não no valor
   exato alocado (que só é conhecido após `_alocar_greedy`).

**Opção B (mais precisa, mais invasiva):** mover o filtro de sinal para
depois de `_alocar_greedy`, comparando `sinal_spillover` contra o custo
real calculado com `_custo_operacional` sobre `valor_alocado`, e remover do
resultado os ativos que não cobrem custo. Prefira esta opção se o tempo de
implementação permitir, pois elimina a estimativa e usa o valor real.

**Critério de aceite:** com `corretagem_fixa > 0` e `capital_max_por_acao`
pequeno, ativos cujo sinal não cobre o custo fixo proporcional não devem
mais ser selecionados. Adicionar um teste rápido (script ou notebook)
comparando o número de operações selecionadas antes/depois da correção com
os mesmos parâmetros.

---

## 3. ✅ Adicionar métricas de risco ao `backtest_grafo`

**Arquivo:** `grafo_estrategia.py`.

**Ação:** criar uma nova função `calcular_metricas_risco` e chamá-la a
partir de `backtest_grafo` (ou deixar como função separada chamada pelo
app — decidir pela primeira opção para manter tudo em
`grafo_estrategia.py`).

**Assinatura sugerida:**
```python
def calcular_metricas_risco(
    resumo: pd.DataFrame,
    capital_inicial: float,
    dias_por_periodo: int,
    taxa_livre_risco_anual: float = 0.0,
) -> dict:
    """A partir da coluna `capital_apos_periodo` de `resumo`, calcula:
    - retorno_total: (capital_final / capital_inicial) - 1
    - retorno_anualizado: composto, usando dias_por_periodo * n_periodos
    - volatilidade_anualizada: desvio padrão dos retornos por período,
      anualizado por sqrt(periodos_por_ano)
    - sharpe: (retorno_anualizado - taxa_livre_risco_anual) / volatilidade_anualizada
    - drawdown_maximo: maior queda percentual do capital acumulado em
      relação ao pico anterior, ao longo de toda a série de
      `capital_apos_periodo`
    Retorna um dict com essas 5 chaves, todas em float.
    """
```

**Lógica de drawdown (referência de implementação):**
```python
serie = resumo["capital_apos_periodo"]
pico = serie.cummax()
drawdown = (serie - pico) / pico
drawdown_maximo = drawdown.min()  # valor negativo, ex: -0.18 = -18%
```

**Lógica de retornos por período (para volatilidade e Sharpe):**
```python
capital_com_inicial = pd.concat([pd.Series([capital_inicial]), serie])
retornos_periodo = capital_com_inicial.pct_change().dropna()
periodos_por_ano = 252 / dias_por_periodo  # dias_por_periodo = horizonte
volatilidade_anualizada = retornos_periodo.std() * (periodos_por_ano ** 0.5)
```

**Taxa livre de risco:** deixar como parâmetro com default 0.0 — não
buscar CDI automaticamente por API nesta etapa (evitar nova dependência de
rede); o usuário informa manualmente na UI (ver item 5).

**Critério de aceite:** rodando com um `resumo` de exemplo com valores
conhecidos de capital, os 5 valores retornados devem bater com cálculo
manual (planilha ou script de verificação separado).

---

## 4. ✅ Adicionar comparação com benchmark (Ibovespa)

**Arquivo:** `grafo_estrategia.py`.

**Problema conhecido:** o projeto não baixa dados de índice, só ações
individuais via COTAHIST. O próprio COTAHIST da B3 **não inclui** o
Ibovespa como série de índice pronta — teria que ser aproximado ou
buscado de outra fonte.

**Ação (escopo desta etapa, sem nova fonte de dados externa):** implementar
um benchmark **equal-weight** com os próprios dados já carregados, como
proxy do mercado, evitando dependência de nova API:

```python
def calcular_benchmark_equalweight(
    df_features: pd.DataFrame,
    datas_decisao: list,
    horizonte: int,
) -> pd.DataFrame:
    """Para cada data de decisão em `datas_decisao`, calcula o retorno
    médio simples (equal-weight) de `retorno_futuro` entre todos os
    tickers disponíveis naquela data, como proxy de 'comprar o mercado'.
    Retorna DataFrame com colunas: data_decisao, retorno_benchmark.
    """
```

**Observação a registrar no código (docstring) e no README:** este
benchmark é uma aproximação equal-weight do universo de ações do
COTAHIST, não o Ibovespa oficial (que é ponderado por valor de mercado
free-float). Se depois quiser o Ibovespa real, será necessário buscar a
série `^BVSP` de uma fonte externa (ex.: biblioteca `yfinance`, fora do
escopo desta etapa por adicionar dependência de rede não solicitada).

**Integração em `backtest_grafo`:** adicionar coluna `retorno_benchmark`
ao `resumo` retornado, calculada para o mesmo conjunto de datas de decisão
já usado pela estratégia.

**Critério de aceite:** `resumo` passa a ter uma coluna
`retorno_benchmark` alinhada por `data_decisao`, sem alterar as colunas
existentes.

---

## 5. ✅ Expor as novas métricas no `app_grafo.py`

**Arquivo:** `app_grafo.py`.

**Ação:**
1. Adicionar um `st.number_input` para "Taxa livre de risco anual (%)"
   próximo aos parâmetros de custo/imposto, default 0.0.
2. Após rodar `backtest_grafo`, chamar `ge.calcular_metricas_risco(resumo,
   capital_inicial=d["capital"], dias_por_periodo=d["horizonte"],
   taxa_livre_risco_anual=taxa_livre_risco_pct/100)`.
3. Exibir os resultados em `st.metric` (adicionar nova linha de colunas,
   ex. `m4, m5, m6 = st.columns(3)` com Retorno anualizado, Volatilidade
   anualizada, Sharpe, Drawdown máximo — 4 métricas, ajustar para 2 linhas
   de colunas se necessário).
4. Adicionar um `st.line_chart` sobrepondo `capital_apos_periodo` da
   estratégia (normalizado para base 100) com o capital acumulado do
   benchmark equal-weight (também normalizado para base 100), para
   comparação visual direta.

**Critério de aceite:** rodar o app, subir dados, rodar backtest, e
visualizar as 4 métricas de risco + gráfico comparativo sem erros de
runtime.

---

## 6. ✅ Filtro de liquidez

**Arquivo:** `grafo_estrategia.py`, nova função `filtrar_liquidez`,
chamada em `app_grafo.py` logo após `ge.carregar_dados` e antes de
`ge.construir_features_grafo`.

**Implementado:**
```python
def filtrar_liquidez(
    df: pd.DataFrame,
    min_negocios_medio: int = 100,
    janela_liquidez: int = 20,
) -> pd.DataFrame:
    """Remove tickers cuja média móvel de `numero_negocios` (janela de
    `janela_liquidez` pregões) fica abaixo de `min_negocios_medio` na
    data de referência."""
    df = df.copy()
    df["media_negocios"] = df.groupby("ticker")["numero_negocios"].transform(
        lambda s: s.rolling(janela_liquidez, min_periods=1).mean()
    )
    df = df[df["media_negocios"] >= min_negocios_medio].copy()
    return df.drop(columns=["media_negocios"])
```

**Integração:** em `app_grafo.py`, os dois parâmetros (`min_negocios_medio`,
`janela_liquidez`) estão expostos num expander "Filtro de liquidez"
(defaults: 100 negócios médios, janela de 20 pregões), aplicados logo após
o upload e antes do cálculo de features.

**Critério de aceite:** ✅ atendido — a mensagem de sucesso após "Carregar
dados" mostra "X de Y tickers mantidos após filtro de liquidez", com X ≤
Y por construção do filtro.

---

## 7. Walk-forward multi-período (robustez estatística)

**Arquivo:** `grafo_estrategia.py`.

**Ação:** criar função que roda `backtest_grafo` repetidamente em blocos
de tempo (ex.: por ano-calendário) e agrega os resultados.

```python
def backtest_walk_forward(
    df_features: pd.DataFrame,
    capital_total: float,
    capital_max_por_acao: float,
    blocos: list[tuple[str, str]],  # [(data_inicio, data_fim), ...]
    **kwargs_backtest_grafo,
) -> pd.DataFrame:
    """Roda backtest_grafo uma vez por bloco de (data_inicio, data_fim),
    reiniciando capital_total a cada bloco (blocos independentes, não
    compostos). Retorna DataFrame com uma linha por bloco:
    data_inicio, data_fim, retorno_periodo, sharpe_periodo,
    drawdown_maximo_periodo, n_operacoes.
    Usa calcular_metricas_risco (item 3) por bloco.
    """
```

**Integração no `app_grafo.py`:** adicionar um modo "Walk-forward
(múltiplos períodos)" no `st.radio` de período a simular, permitindo ao
usuário definir blocos anuais automaticamente (`pd.date_range` por ano
entre `data_min` e `data_max`) e exibir a tabela de resultados por bloco
+ um boxplot ou tabela de dispersão do Sharpe entre blocos.

**Critério de aceite:** rodar walk-forward em pelo menos 2 blocos anuais
e visualizar resultados individuais por bloco, não só o agregado.

---

## 8. Teste de significância contra baseline aleatório

**Arquivo:** `grafo_estrategia.py`.

**Ação:**
```python
def backtest_baseline_aleatorio(
    df_features: pd.DataFrame,
    capital_total: float,
    capital_max_por_acao: float,
    horizonte: int,
    top_n: int,
    n_simulacoes: int = 30,
    seed: int = 42,
    **kwargs_custo,
) -> pd.DataFrame:
    """Em cada data de decisão (mesmas datas que o backtest real usaria),
    seleciona top_n tickers aleatoriamente (em vez de por sinal_spillover)
    e simula o mesmo horizonte de saída com retorno_futuro real. Repete
    n_simulacoes vezes com seeds diferentes. Retorna DataFrame com uma
    linha por simulação: retorno_total, sharpe (reaproveitando
    calcular_metricas_risco).
    """
```

**Integração no `app_grafo.py`:** botão opcional "Rodar baseline
aleatório" que, após o backtest principal, roda essa função e mostra o
retorno/Sharpe da estratégia real comparado à distribuição (média +
percentis) do baseline aleatório — para argumentar se o sinal é melhor
que chance.

**Critério de aceite:** a saída inclui a posição percentual do resultado
real da estratégia dentro da distribuição do baseline (ex.: "resultado
real está no percentil 82 dos 30 baselines aleatórios").

---

## 9. Sensibilidade de parâmetros (grid search informativo)

**Arquivo:** `grafo_estrategia.py`.

**Ação:**
```python
def grid_sensibilidade(
    df_features: pd.DataFrame,
    capital_total: float,
    capital_max_por_acao: float,
    janelas_correlacao: list[int],
    limiares_correlacao: list[float],
    **kwargs_backtest_grafo,
) -> pd.DataFrame:
    """Roda backtest_grafo para cada combinação de
    (janela_correlacao, limiar_correlacao) na grade fornecida. Retorna
    DataFrame long-format com colunas: janela_correlacao,
    limiar_correlacao, retorno_total, sharpe, n_operacoes — uma linha por
    combinação.
    """
```

**Integração no `app_grafo.py`:** seção opcional "Análise de
sensibilidade" com dois `st.multiselect`/`st.slider` para escolher as
grades de janela e limiar, e exibir um heatmap (`st.dataframe` com
gradiente de cor, ou `plotly`/`altair` se já disponível) de Sharpe por
combinação.

**Critério de aceite:** rodar com uma grade pequena (ex.: 2 janelas × 2
limiares = 4 combinações) e confirmar que a tabela de saída tem 4 linhas
com valores distintos entre si.

---

## Ordem de execução recomendada

1 → 2 → 3 → 5 (parcial, só métricas de risco) → 4 → 5 (completar com
benchmark) → 6 → 7 → 8 → 9.

Itens 1-6 são o mínimo para o pré-relatório e **já estão concluídos**.
Itens 7-9 seguem pendentes de propósito — são diferenciais de rigor
metodológico mais relevantes para as fases eliminatórias seguintes
(quartas de final em diante).