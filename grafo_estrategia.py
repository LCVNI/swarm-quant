"""Estratégia baseada em GRAFO DE CORRELAÇÃO entre ações (market graph), sem ML.

Módulo AUTOSSUFICIENTE: não importa nada de core.py, propositalmente, para
poder ser desenvolvido/mantido por um time separado do time de ML. Duplica
localmente as poucas funções de custo/alocação/imposto que também existem em
core.py (mesma fórmula, mesma fonte legal), para as duas estratégias ficarem
comparáveis sem acoplar os dois códigos.

Metodologia: "market graph" (Boginski, Butenko & Pardalos, 2003/2005) — grafo
onde dois ativos são conectados por uma aresta não-direcionada quando a
correlação dos seus retornos, numa janela recente, ultrapassa um limiar.
Aqui a aresta é ponderada pela força da correlação (não é o market graph
binário original).

Regra de decisão (lead-lag / contágio de retorno): para cada ticker, calcula
o retorno médio recente dos vizinhos no grafo, ponderado pela correlação, e
compara com o retorno recente do próprio ticker. Sinal alto = vizinhos
correlacionados já subiram, o ticker ainda não acompanhou.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constantes próprias do módulo (duplicadas de core.py de propósito — ver
# docstring acima). Fontes das mesmas em core.py / conversas anteriores:
# B3 (b3.com.br/tarifas), Receita Federal (gov.br/receitafederal), LC 116/03.
# ---------------------------------------------------------------------------
MERCADO_VISTA = 10
HORIZONTE_PADRAO = 5
JANELA_CORRELACAO_PADRAO = 60
LIMIAR_CORRELACAO_PADRAO = 0.3

TAXA_B3_PADRAO = 0.0
CORRETAGEM_PADRAO = 0.0
CORRETAGEM_PERCENTUAL_PADRAO = 0.0
ISS_PADRAO = 0.0
IRRF_PCT_PADRAO = 0.0
IRRF_MINIMO = 1.0
IR_ALIQUOTA_PADRAO = 0.0
ISENCAO_VENDAS_MENSAL_PADRAO = 0.0


# ---------------------------------------------------------------------------
# Dados e features (só o necessário para a estratégia de grafo: retornos)
# ---------------------------------------------------------------------------
def carregar_dados(caminho: str) -> pd.DataFrame:
    df = pd.read_parquet(caminho) if caminho.endswith(".parquet") else pd.read_csv(
        caminho, parse_dates=["data_pregao"]
    )
    df = df[df["tipo_mercado"] == MERCADO_VISTA].copy()
    return df.sort_values(["ticker", "data_pregao"])


def filtrar_liquidez(
    df: pd.DataFrame,
    min_negocios_medio: int = 100,
    janela_liquidez: int = 20,
) -> pd.DataFrame:
    """Remove tickers cuja média móvel de `numero_negocios` (janela de
    `janela_liquidez` pregões) fica abaixo de `min_negocios_medio` na data
    de referência. Evita que ações pouco líquidas entrem no grafo de
    correlação (correlações espúrias) e no backtest (preços de fechamento
    pouco representativos de uma execução real).
    """
    df = df.copy()
    df["media_negocios"] = df.groupby("ticker")["numero_negocios"].transform(
        lambda s: s.rolling(janela_liquidez, min_periods=1).mean()
    )
    df = df[df["media_negocios"] >= min_negocios_medio].copy()
    return df.drop(columns=["media_negocios"])


def construir_features_grafo(df: pd.DataFrame, horizonte: int = HORIZONTE_PADRAO) -> pd.DataFrame:
    """Só o que a estratégia de grafo precisa: retorno_1d (monta o grafo),
    retorno_5d (sinal de curto prazo) e retorno_futuro (realização real)."""
    g = df.groupby("ticker", group_keys=False)["preco_fechamento"]
    df["retorno_1d"] = g.pct_change(1)
    df["retorno_5d"] = g.pct_change(5)
    df["retorno_futuro"] = g.transform(lambda s: s.shift(-horizonte) / s - 1)
    return df


LIMITE_RETORNO_DIARIO_PADRAO = 0.80  # 80% num único pregão


def sanitizar_outliers_retorno(
    df: pd.DataFrame, limite_retorno_diario: float = LIMITE_RETORNO_DIARIO_PADRAO
) -> tuple[pd.DataFrame, int]:
    """O COTAHIST bruto da B3 NÃO ajusta preços para desdobramentos,
    grupamentos ou bonificações. Um evento desses aparece como um
    'retorno' de centenas de % num único pregão — não é um movimento real
    de mercado, é um artefato de dado não ajustado. Como o sinal de
    spillover rankeia pelas maiores divergências, a estratégia é atraída
    justamente para esses artefatos, distorcendo o backtest inteiro.

    Neutraliza (vira NaN) qualquer valor de retorno_1d, retorno_5d ou
    retorno_futuro cujo módulo ultrapasse `limite_retorno_diario`,
    coluna por coluna (não descarta o ticker inteiro, só o ponto
    suspeito — outros dias do mesmo ticker continuam válidos). Linhas
    com NaN nessas colunas já são excluídas do backtest via
    `backtest_grafo` (dropna em `retorno_1d`/`retorno_5d`/`retorno_futuro`).

    Retorna (df_corrigido, n_valores_neutralizados) para você poder
    reportar quantos pontos suspeitos foram encontrados.
    """
    df = df.copy()
    n_afetados = 0
    for col in ("retorno_1d", "retorno_5d", "retorno_futuro"):
        suspeitos = df[col].abs() > limite_retorno_diario
        n_afetados += int(suspeitos.sum())
        df.loc[suspeitos, col] = np.nan
    return df, n_afetados


def _pivot_retornos(df: pd.DataFrame, coluna: str = "retorno_1d") -> pd.DataFrame:
    return df.pivot(index="data_pregao", columns="ticker", values=coluna)


# ---------------------------------------------------------------------------
# Grafo e sinal
# ---------------------------------------------------------------------------
def construir_grafo_correlacao(
    retornos_pivot: pd.DataFrame,
    data_referencia: pd.Timestamp,
    janela: int = JANELA_CORRELACAO_PADRAO,
    limiar_correlacao: float = LIMIAR_CORRELACAO_PADRAO,
) -> nx.Graph:
    """Grafo de correlação usando só dados ANTERIORES a `data_referencia` (sem vazamento).

    Extração de arestas vetorizada com numpy (só a triangular superior da
    matriz de correlação, sem diagonal) em vez de um loop duplo em Python
    puro sobre todos os pares de tickers — mesmo grafo, mesmos pesos,
    mesmo critério de corte, só mais rápido para universos grandes.
    """
    janela_dados = retornos_pivot[retornos_pivot.index < data_referencia].tail(janela)
    grafo = nx.Graph()
    if len(janela_dados) < max(20, janela // 3):
        return grafo

    corr = janela_dados.corr(min_periods=max(20, janela // 3))
    grafo.add_nodes_from(corr.columns)

    colunas = corr.columns.to_numpy()
    valores = corr.to_numpy()
    n = len(colunas)
    if n < 2:
        return grafo

    i_idx, j_idx = np.triu_indices(n, k=1)
    pesos = valores[i_idx, j_idx]
    mascara = np.isfinite(pesos) & (np.abs(pesos) >= limiar_correlacao)

    for i, j, peso in zip(i_idx[mascara], j_idx[mascara], pesos[mascara]):
        grafo.add_edge(colunas[i], colunas[j], weight=float(peso))

    return grafo


def calcular_sinal_grafo(grafo: nx.Graph, retornos_recentes: pd.Series) -> pd.DataFrame:
    """`retornos_recentes`: Series ticker -> retorno recente (ex: retorno_5d) na data de decisão."""
    linhas = []
    for ticker in grafo.nodes:
        if ticker not in retornos_recentes.index or pd.isna(retornos_recentes.get(ticker)):
            continue
        vizinhos = list(grafo.neighbors(ticker))
        if not vizinhos:
            continue

        pesos, retornos_viz = [], []
        for v in vizinhos:
            r = retornos_recentes.get(v, np.nan)
            if pd.notna(r):
                pesos.append(abs(grafo[ticker][v]["weight"]))
                retornos_viz.append(r)
        if not pesos or sum(pesos) == 0:
            continue

        media_vizinhos = float(np.average(retornos_viz, weights=pesos))
        retorno_proprio = float(retornos_recentes[ticker])
        linhas.append({
            "ticker": ticker,
            "grau": len(vizinhos),
            "retorno_vizinhos": round(media_vizinhos, 4),
            "retorno_proprio": round(retorno_proprio, 4),
            "sinal_spillover": round(media_vizinhos - retorno_proprio, 4),
        })

    return pd.DataFrame(linhas).sort_values("sinal_spillover", ascending=False)


# ---------------------------------------------------------------------------
# Custo, alocação e IR (duplicados de core.py — ver docstring do módulo)
# ---------------------------------------------------------------------------
def _custo_operacional(
    valor_financeiro: float, taxa_b3: float, corretagem_fixa: float,
    corretagem_percentual: float, iss_pct: float,
) -> float:
    corretagem = corretagem_fixa + valor_financeiro * corretagem_percentual
    return valor_financeiro * taxa_b3 + corretagem + corretagem * iss_pct


def _alocar_greedy(candidatos: pd.DataFrame, capital_disponivel: float, capital_max_por_acao: float) -> pd.DataFrame:
    linhas = []
    capital_restante = capital_disponivel
    for _, ativo in candidatos.iterrows():
        if capital_restante < ativo["preco_fechamento"]:
            continue
        valor_alvo = min(capital_max_por_acao, capital_restante)
        quantidade = int(valor_alvo // ativo["preco_fechamento"])
        if quantidade <= 0:
            continue
        valor_efetivo = quantidade * ativo["preco_fechamento"]
        capital_restante -= valor_efetivo
        linha = ativo.to_dict()
        linha["quantidade_acoes"] = quantidade
        linha["valor_alocado"] = round(valor_efetivo, 2)
        linhas.append(linha)
    return pd.DataFrame(linhas)


def calcular_ir_mensal(
    operacoes: pd.DataFrame,
    ir_aliquota: float = IR_ALIQUOTA_PADRAO,
    isencao_vendas_mensal: float = ISENCAO_VENDAS_MENSAL_PADRAO,
) -> pd.DataFrame:
    """Apuração mensal de IR (regra de swing trade em ações): compensação de
    prejuízo sem prazo de validade + isenção se vendas do mês <= limite.
    Mesma regra de core.calcular_ir_mensal (Lei 11.033/2004, Art. 3º, II)."""
    if operacoes.empty:
        return pd.DataFrame()

    op = operacoes.dropna(subset=["data_venda"]).copy()
    op["data_venda"] = pd.to_datetime(op["data_venda"])
    op["mes"] = op["data_venda"].dt.to_period("M")

    mensal = op.groupby("mes").agg(vendas_mes=("valor_venda", "sum"), lucro_mes=("lucro", "sum"),
                                    irrf_retido_mes=("irrf", "sum")).reset_index().sort_values("mes")

    linhas = []
    prejuizo_acumulado = 0.0
    for _, row in mensal.iterrows():
        resultado = row["lucro_mes"] - prejuizo_acumulado
        if resultado <= 0:
            prejuizo_acumulado = -resultado
            ganho_tributavel = 0.0
        else:
            prejuizo_acumulado = 0.0
            ganho_tributavel = resultado

        isento = row["vendas_mes"] <= isencao_vendas_mensal
        ir_devido = 0.0 if isento else ganho_tributavel * ir_aliquota
        darf = max(0.0, ir_devido - row["irrf_retido_mes"])

        linhas.append({
            "mes": str(row["mes"]),
            "vendas_mes": round(row["vendas_mes"], 2),
            "lucro_mes": round(row["lucro_mes"], 2),
            "isento": isento,
            "prejuizo_acumulado_apos": round(prejuizo_acumulado, 2),
            "irrf_retido_mes": round(row["irrf_retido_mes"], 2),
            "ir_devido": round(ir_devido, 2),
            "darf_a_pagar": round(darf, 2),
        })

    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Métricas e Benchmark
# ---------------------------------------------------------------------------
def calcular_metricas_risco(
    resumo: pd.DataFrame,
    capital_inicial: float,
    dias_por_periodo: int,
    taxa_livre_risco_anual: float = 0.0,
) -> dict:
    """A partir da coluna `capital_apos_periodo` de `resumo`, calcula:
    - retorno_total: (capital_final / capital_inicial) - 1
    - retorno_anualizado: composto, usando dias_por_periodo * n_periodos
    - volatilidade_anualizada: desvio padrão dos retornos por período, anualizado
    - sharpe: (retorno_anualizado - taxa_livre_risco_anual) / volatilidade_anualizada
    - drawdown_maximo: maior queda percentual do capital acumulado
    """
    if resumo.empty:
        return {
            "retorno_total": 0.0,
            "retorno_anualizado": 0.0,
            "volatilidade_anualizada": 0.0,
            "sharpe": 0.0,
            "drawdown_maximo": 0.0,
        }

    serie = resumo["capital_apos_periodo"]
    capital_final = serie.iloc[-1]
    retorno_total = (capital_final / capital_inicial) - 1

    n_periodos = len(serie)
    dias_totais = n_periodos * dias_por_periodo
    anos_totais = dias_totais / 252

    if anos_totais > 0:
        retorno_anualizado = (capital_final / capital_inicial) ** (1 / anos_totais) - 1
    else:
        retorno_anualizado = retorno_total

    capital_com_inicial = pd.concat([pd.Series([capital_inicial]), serie])
    retornos_periodo = capital_com_inicial.pct_change().dropna()
    periodos_por_ano = 252 / dias_por_periodo

    volatilidade_anualizada = retornos_periodo.std() * (periodos_por_ano ** 0.5)
    if pd.isna(volatilidade_anualizada) or volatilidade_anualizada == 0:
        volatilidade_anualizada = 0.0
        sharpe = 0.0
    else:
        sharpe = (retorno_anualizado - taxa_livre_risco_anual) / volatilidade_anualizada

    pico = serie.cummax()
    drawdown = (serie - pico) / pico
    drawdown_maximo = drawdown.min()

    return {
        "retorno_total": float(retorno_total),
        "retorno_anualizado": float(retorno_anualizado),
        "volatilidade_anualizada": float(volatilidade_anualizada),
        "sharpe": float(sharpe),
        "drawdown_maximo": float(drawdown_maximo),
    }


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
    linhas = []
    for data_decisao in datas_decisao:
        dt_decisao = pd.Timestamp(data_decisao)
        candidatos_dia = df_features[df_features["data_pregao"] == dt_decisao]
        retorno_medio = candidatos_dia["retorno_futuro"].mean() if not candidatos_dia.empty else 0.0
        linhas.append({
            "data_decisao": data_decisao,
            "retorno_benchmark": float(retorno_medio) if pd.notna(retorno_medio) else 0.0
        })
    return pd.DataFrame(linhas)


def calcular_benchmarks_externos(
    df_benchmarks: pd.DataFrame,
    resumo: pd.DataFrame,
) -> pd.DataFrame:
    """Recebe o `resumo` já retornado por `backtest_grafo` e um
    `df_benchmarks` (saída de `benchmarks_externos.py`, colunas: `data`,
    `selic_diaria`, `cdi_diario` em % ao dia, `ibovespa_fechamento` em
    nível do índice). Para cada linha de `resumo` (um período de decisão
    -> venda), calcula o retorno de cada benchmark no MESMO intervalo de
    datas, para comparação justa:
    - retorno_selic / retorno_cdi: taxas diárias compostas no período
      (produtório de (1 + taxa/100) - 1).
    - retorno_ibovespa: variação percentual do fechamento entre a data de
      decisão e a data de venda prevista.
    Retorna `resumo` com essas 3 colunas novas. Períodos sem
    `data_venda_prevista` (fim do histórico) ficam com retorno 0.0.
    """
    if df_benchmarks.empty or resumo.empty:
        vazio = resumo.copy()
        for col in ("retorno_selic", "retorno_cdi", "retorno_ibovespa"):
            vazio[col] = 0.0
        return vazio

    bench = df_benchmarks.copy()
    bench["data"] = pd.to_datetime(bench["data"])
    bench = bench.set_index("data").sort_index()

    linhas = []
    for _, row in resumo.iterrows():
        ini = pd.Timestamp(row["data_decisao"])
        fim = row.get("data_venda_prevista")
        fim = pd.Timestamp(fim) if pd.notna(fim) else None

        if fim is None:
            linhas.append({"retorno_selic": 0.0, "retorno_cdi": 0.0, "retorno_ibovespa": 0.0})
            continue

        janela = bench[(bench.index > ini) & (bench.index <= fim)]

        retorno_selic = 0.0
        if "selic_diaria" in janela.columns and not janela["selic_diaria"].dropna().empty:
            retorno_selic = float((1 + janela["selic_diaria"].fillna(0) / 100).prod() - 1)

        retorno_cdi = 0.0
        if "cdi_diario" in janela.columns and not janela["cdi_diario"].dropna().empty:
            retorno_cdi = float((1 + janela["cdi_diario"].fillna(0) / 100).prod() - 1)

        retorno_ibovespa = 0.0
        if "ibovespa_fechamento" in bench.columns:
            preco_ini = bench.loc[bench.index <= ini, "ibovespa_fechamento"].dropna()
            preco_fim = bench.loc[bench.index <= fim, "ibovespa_fechamento"].dropna()
            if len(preco_ini) and len(preco_fim):
                retorno_ibovespa = float(preco_fim.iloc[-1] / preco_ini.iloc[-1] - 1)

        linhas.append({
            "retorno_selic": retorno_selic,
            "retorno_cdi": retorno_cdi,
            "retorno_ibovespa": retorno_ibovespa,
        })

    extras = pd.DataFrame(linhas)
    return pd.concat([resumo.reset_index(drop=True), extras], axis=1)


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def backtest_grafo(
    df_features: pd.DataFrame,
    capital_total: float,
    capital_max_por_acao: float,
    horizonte: int = HORIZONTE_PADRAO,
    top_n: int = 10,
    taxa_b3: float = TAXA_B3_PADRAO,
    corretagem_fixa: float = CORRETAGEM_PADRAO,
    corretagem_percentual: float = CORRETAGEM_PERCENTUAL_PADRAO,
    iss_pct: float = ISS_PADRAO,
    irrf_pct: float = IRRF_PCT_PADRAO,
    janela_correlacao: int = JANELA_CORRELACAO_PADRAO,
    limiar_correlacao: float = LIMIAR_CORRELACAO_PADRAO,
    min_dias_treino: int = 120,
    data_inicio: str | pd.Timestamp | None = None,
    data_fim: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mesmo formato de saída do core.backtest (comparável lado a lado).

    Sem treino de modelo: em cada decisão, monta o grafo de correlação (só
    com passado), calcula o sinal de spillover, compra os top_n com sinal
    positivo o suficiente pra cobrir custos, mantém `horizonte` pregões e
    realiza com o retorno real (`retorno_futuro`).
    """
    base = df_features.dropna(subset=["retorno_1d", "retorno_5d", "retorno_futuro"]).copy()
    datas = np.sort(base["data_pregao"].unique())
    retornos_pivot = _pivot_retornos(df_features)
    
    custo_fixo_pct_estimado = 2 * corretagem_fixa / capital_max_por_acao if capital_max_por_acao > 0 else 0.0
    custo_pct_ida_volta_estimado = 2 * (taxa_b3 + corretagem_percentual * (1 + iss_pct)) + custo_fixo_pct_estimado

    capital_disponivel = capital_total
    operacoes = []
    resumo = []

    i = min_dias_treino
    if data_inicio is not None:
        i = max(i, int(np.searchsorted(datas, np.datetime64(pd.Timestamp(data_inicio)))))
    limite_fim = np.datetime64(pd.Timestamp(data_fim)) if data_fim is not None else None

    while i < len(datas):
        data_decisao = datas[i]
        if limite_fim is not None and data_decisao > limite_fim:
            break

        candidatos_dia = base[base["data_pregao"] == data_decisao]
        grafo = construir_grafo_correlacao(retornos_pivot, data_decisao, janela_correlacao, limiar_correlacao)
        if grafo.number_of_edges() == 0 or candidatos_dia.empty:
            i += horizonte
            continue

        retornos_recentes = candidatos_dia.set_index("ticker")["retorno_5d"]
        sinal = calcular_sinal_grafo(grafo, retornos_recentes)
        sinal = sinal[sinal["sinal_spillover"] > custo_pct_ida_volta_estimado].head(top_n)
        if sinal.empty:
            i += horizonte
            continue

        candidatos = candidatos_dia.merge(sinal, on="ticker").sort_values("sinal_spillover", ascending=False)
        selecionados = _alocar_greedy(candidatos, capital_disponivel, capital_max_por_acao)
        data_venda = pd.Timestamp(datas[i + horizonte]) if i + horizonte < len(datas) else pd.NaT

        lucro_periodo = 0.0
        for _, ativo in selecionados.iterrows():
            preco_compra = ativo["preco_fechamento"]
            valor_compra = ativo["valor_alocado"]
            preco_venda_real = preco_compra * (1 + ativo["retorno_futuro"])
            valor_venda = ativo["quantidade_acoes"] * preco_venda_real

            custo = _custo_operacional(valor_compra, taxa_b3, corretagem_fixa, corretagem_percentual, iss_pct) + \
                _custo_operacional(valor_venda, taxa_b3, corretagem_fixa, corretagem_percentual, iss_pct)
            irrf = valor_venda * irrf_pct
            irrf = irrf if irrf >= IRRF_MINIMO else 0.0

            lucro = valor_venda - valor_compra - custo
            lucro_periodo += lucro
            operacoes.append({
                "data_compra": pd.Timestamp(data_decisao).date(),
                "data_venda": data_venda.date() if pd.notna(data_venda) else None,
                "ticker": ativo["ticker"],
                "preco_compra": round(preco_compra, 2),
                "quantidade": int(ativo["quantidade_acoes"]),
                "preco_venda": round(preco_venda_real, 2),
                "valor_venda": round(valor_venda, 2),
                "sinal_spillover": round(ativo["sinal_spillover"], 4),
                "retorno_realizado": round(float(ativo["retorno_futuro"]), 4),
                "custo": round(custo, 2),
                "irrf": round(irrf, 2),
                "lucro": round(lucro, 2),
            })

        capital_alocado = float(selecionados["valor_alocado"].sum()) if not selecionados.empty else 0.0
        pct_capital_alocado = capital_alocado / capital_disponivel if capital_disponivel > 0 else 0.0

        capital_disponivel += lucro_periodo
        resumo.append({
            "data_decisao": pd.Timestamp(data_decisao).date(),
            "data_venda_prevista": data_venda.date() if pd.notna(data_venda) else None,
            "n_operacoes": len(selecionados),
            "n_arestas_grafo": grafo.number_of_edges(),
            "capital_alocado": round(capital_alocado, 2),
            "pct_capital_alocado": round(pct_capital_alocado, 4),
            "lucro_periodo": round(lucro_periodo, 2),
            "capital_apos_periodo": round(capital_disponivel, 2),
        })
        i += horizonte

    df_resumo = pd.DataFrame(resumo)
    if not df_resumo.empty:
        df_bench = calcular_benchmark_equalweight(df_features, df_resumo["data_decisao"].tolist(), horizonte)
        df_resumo = df_resumo.merge(df_bench, on="data_decisao", how="left")

    return pd.DataFrame(operacoes), df_resumo