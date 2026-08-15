"""Estratégias baseadas em GRAFO DE CORRELAÇÃO entre ações (market graph), sem ML.

Módulo AUTOSSUFICIENTE: não importa nada de core.py, propositalmente, para
poder ser desenvolvido/mantido por um time separado do time de ML. Duplica
localmente as poucas funções de custo/alocação/imposto que também existem em
core.py (mesma fórmula, mesma fonte legal), para as estratégias ficarem
comparáveis sem acoplar os dois códigos.

Base teórica comum: "market graph" (Boginski, Butenko & Pardalos, 2003/2005) —
grafo onde dois ativos são conectados por uma aresta quando a correlação dos
seus retornos, numa janela recente, ultrapassa um limiar.

Cinco estratégias de decisão, todas comparáveis (mesmo motor de custo/imposto/
alocação, `_backtest_com_sinal`), do jeito mais simples ao mais complexo:

1. `backtest_spillover_threshold`: contágio de retorno via vizinhança direta
   no grafo de correlação limiarizado (a estratégia original).
2. `backtest_spillover_mst`: mesma ideia, mas a vizinhança vem de uma Árvore
   Geradora Mínima (Mantegna, 1999) em vez do limiar — cada ativo só "escuta"
   suas conexões mais essenciais, não todas acima do limiar.
3. `backtest_centralidade`: seleciona os ativos mais "centrais" (importantes
   na estrutura da rede) e, dentro desses, ranqueia por momentum.
4. `backtest_comunidade`: detecta clusters de ativos que se movem juntos
   (Louvain) e aposta em contágio DENTRO do cluster, não só entre vizinhos
   diretos.
5. `backtest_gnn_simplificado`: uma única camada de "convolução em grafo"
   (agregação ponderada dos vizinhos) alimentando uma regressão Ridge (L2
   forte) treinada em walk-forward. É uma GNN de verdade na estrutura, mas
   deliberadamente rasa e regularizada — ver aviso na função sobre por que
   não usei uma rede profunda (PyTorch/DGL).
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

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


def construir_features_grafo(df: pd.DataFrame, horizonte: int = HORIZONTE_PADRAO) -> pd.DataFrame:
    """Só o que a estratégia de grafo precisa: retorno_1d (monta o grafo),
    retorno_5d (sinal de curto prazo) e retorno_futuro (realização real).
    
    Respeita 'retorno_valido' vindo do módulo universo.py para não costurar GAPs.
    """
    g = df.groupby("ticker", group_keys=False)["preco_fechamento"]
    df["retorno_1d"] = g.pct_change(1)
    df["retorno_5d"] = g.pct_change(5)
    df["retorno_futuro"] = g.transform(lambda s: s.shift(-horizonte) / s - 1)
    
    if "retorno_valido" in df.columns:
        invalido = ~df["retorno_valido"].fillna(True)
        # Se a própria mudança for através de um período inválido, zera-se o sinal
        df.loc[invalido, ["retorno_1d", "retorno_5d", "retorno_futuro"]] = np.nan
        
    return df


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

    Versão vetorizada: usa máscara triangular superior (np.triu) + stack do Pandas
    para eliminar laços O(N²) em Python puro. A inserção de arestas é feita em
    lote via nx.from_pandas_edgelist (C-level).
    """
    janela_dados = retornos_pivot[retornos_pivot.index < data_referencia].tail(janela)
    if len(janela_dados) < max(20, janela // 3):
        return nx.Graph()

    corr = janela_dados.corr(min_periods=max(20, janela // 3))

    # 1. Máscara Matricial: triangular superior (exclui diagonal e espelho)
    mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)

    # 2. Aplainamento (Stack): transforma a matriz em Series (source, target) -> weight
    #    Renomeia eixos para evitar conflito de nome duplicado ('ticker') no reset_index
    corr.index.name = "source"
    corr.columns.name = "target"
    arestas = corr.where(mask).stack().reset_index(name="weight")

    # 3. Broadcasting de Filtro: filtra NaN e aplica limiar de correlação
    arestas = arestas[arestas["weight"].abs() >= limiar_correlacao]

    # 4. Inserção em Volume (Batch Edges): monta o grafo de uma só vez
    grafo = nx.from_pandas_edgelist(arestas, source="source", target="target", edge_attr="weight")

    # Garante que todos os nós existam, mesmo sem arestas (nós isolados)
    grafo.add_nodes_from(corr.columns)
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


def construir_grafo_mst(
    retornos_pivot: pd.DataFrame, data_referencia: pd.Timestamp, janela: int = JANELA_CORRELACAO_PADRAO,
) -> nx.Graph:
    """Árvore Geradora Mínima sobre a distância de correlação de Mantegna (1999):
    d(i,j) = sqrt(2 * (1 - correlação(i,j))). Mantém só as conexões mais essenciais
    de cada ativo (ao contrário do limiar, que mantém TODAS as correlações fortes).
    Fonte: Mantegna, "Hierarchical structure in financial markets" (1999).

    Versão vetorizada: usa máscara triangular superior (np.triu) + stack do Pandas
    para eliminar laços O(N²) em Python puro. A inserção de arestas é feita em
    lote via nx.from_pandas_edgelist (C-level).
    """
    janela_dados = retornos_pivot[retornos_pivot.index < data_referencia].tail(janela)
    if len(janela_dados) < max(20, janela // 3):
        return nx.Graph()

    corr = janela_dados.corr(min_periods=max(20, janela // 3)).clip(-1, 1)
    distancia = np.sqrt(2 * (1 - corr))

    # 1. Máscara Matricial: triangular superior (exclui diagonal e espelho)
    mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)

    # 2. Aplainamento (Stack): DataFrames empilhados com weight (distância) e correlação
    #    Renomeia eixos para evitar conflito de nome duplicado ('ticker') no reset_index
    corr.index.name = "source"
    corr.columns.name = "target"
    distancia.index.name = "source"
    distancia.columns.name = "target"
    dist_stack = distancia.where(mask).stack().reset_index(name="weight")
    corr_stack = corr.where(mask).stack().reset_index(name="correlacao")

    # Junta distância + correlação num único DataFrame
    arestas_df = dist_stack.copy()
    arestas_df["correlacao"] = corr_stack["correlacao"]

    # Remove pares com distância NaN
    arestas_df = arestas_df.dropna(subset=["weight"])

    if arestas_df.empty:
        return nx.Graph()

    # 3. Inserção em Volume: monta o grafo completo de uma só vez
    grafo_completo = nx.from_pandas_edgelist(
        arestas_df, source="source", target="target",
        edge_attr=["weight", "correlacao"],
    )
    return nx.minimum_spanning_tree(grafo_completo, weight="weight")


def _sinal_por_vizinhanca(grafo: nx.Graph, retornos_recentes: pd.Series, coluna_peso: str = "weight") -> pd.DataFrame:
    """Igual a calcular_sinal_grafo, mas genérico o suficiente pra reaproveitar
    na MST (onde o peso relevante para ponderar é a correlação, guardada no
    atributo 'correlacao', não a distância guardada em 'weight')."""
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
                pesos.append(abs(grafo[ticker][v][coluna_peso]))
                retornos_viz.append(r)
        if not pesos or sum(pesos) == 0:
            continue
        media_vizinhos = float(np.average(retornos_viz, weights=pesos))
        sinal = media_vizinhos - float(retornos_recentes[ticker])
        linhas.append({"ticker": ticker, "sinal": round(sinal, 4)})
    return pd.DataFrame(linhas)


def calcular_centralidade(grafo: nx.Graph) -> dict[str, float]:
    """Centralidade de autovetor (quão conectado a outros ativos IMPORTANTES);
    cai para grau simples se o grafo não convergir (grafos desconexos/pequenos)."""
    try:
        return nx.eigenvector_centrality(grafo, weight="weight", max_iter=500)
    except (nx.PowerIterationFailedConvergence, nx.AmbiguousSolution):
        return dict(nx.degree_centrality(grafo))


def calcular_comunidades(grafo: nx.Graph, seed: int = 42) -> dict[str, int]:
    """Algoritmo de Louvain: agrupa ativos em clusters que se movem juntos."""
    comunidades = nx.algorithms.community.louvain_communities(grafo, weight="weight", seed=seed)
    return {ticker: i for i, com in enumerate(comunidades) for ticker in com}


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
# Motor genérico de backtest: recebe uma função que gera o sinal do dia, e
# cuida do resto (alocação, custo, IR, realização) igual pra todas as
# estratégias — evita reescrever essa lógica 4 vezes.
# ---------------------------------------------------------------------------
def _backtest_com_sinal(
    df_features: pd.DataFrame,
    gerar_sinal: "callable[[pd.DataFrame, pd.DataFrame, pd.Timestamp], pd.DataFrame]",
    capital_total: float,
    capital_max_por_acao: float,
    horizonte: int = HORIZONTE_PADRAO,
    top_n: int = 10,
    taxa_b3: float = TAXA_B3_PADRAO,
    corretagem_fixa: float = CORRETAGEM_PADRAO,
    corretagem_percentual: float = CORRETAGEM_PERCENTUAL_PADRAO,
    iss_pct: float = ISS_PADRAO,
    irrf_pct: float = IRRF_PCT_PADRAO,
    min_dias_treino: int = 120,
    data_inicio: str | pd.Timestamp | None = None,
    data_fim: str | pd.Timestamp | None = None,
    coluna_extra_operacao: str = "sinal",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`gerar_sinal(candidatos_dia, retornos_pivot, data_decisao)` deve retornar
    um DataFrame com colunas ["ticker", "sinal"] (sinal em unidade de retorno,
    comparável ao custo de ida e volta). Maior sinal = maior prioridade de compra.
    """
    base = df_features.dropna(subset=["retorno_1d", "retorno_5d", "retorno_futuro"]).copy()
    datas = np.sort(base["data_pregao"].unique())
    retornos_pivot = _pivot_retornos(df_features)
    custo_pct_ida_volta = 2 * (taxa_b3 + corretagem_percentual * (1 + iss_pct))

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
        if candidatos_dia.empty:
            i += horizonte
            continue

        sinal = gerar_sinal(candidatos_dia, retornos_pivot, data_decisao)
        if sinal is None or sinal.empty or "sinal" not in sinal.columns:
            i += horizonte
            continue
        sinal = sinal[sinal["sinal"] > custo_pct_ida_volta].sort_values("sinal", ascending=False).head(top_n)
        if sinal.empty:
            i += horizonte
            continue

        candidatos = candidatos_dia.merge(sinal, on="ticker").sort_values("sinal", ascending=False)
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
                "sinal": round(float(ativo["sinal"]), 4),
                "retorno_realizado": round(float(ativo["retorno_futuro"]), 4),
                "custo": round(custo, 2),
                "irrf": round(irrf, 2),
                "lucro": round(lucro, 2),
            })

        capital_disponivel += lucro_periodo
        resumo.append({
            "data_decisao": pd.Timestamp(data_decisao).date(),
            "data_venda_prevista": data_venda.date() if pd.notna(data_venda) else None,
            "n_operacoes": len(selecionados),
            "lucro_periodo": round(lucro_periodo, 2),
            "capital_apos_periodo": round(capital_disponivel, 2),
        })
        i += horizonte

    return pd.DataFrame(operacoes), pd.DataFrame(resumo)


# ---------------------------------------------------------------------------
# 1) Contágio via vizinhança direta no grafo limiarizado (estratégia original)
# ---------------------------------------------------------------------------
def backtest_spillover_threshold(
    df_features: pd.DataFrame, capital_total: float, capital_max_por_acao: float,
    horizonte: int = HORIZONTE_PADRAO, top_n: int = 10, taxa_b3: float = TAXA_B3_PADRAO,
    corretagem_fixa: float = CORRETAGEM_PADRAO, corretagem_percentual: float = CORRETAGEM_PERCENTUAL_PADRAO,
    iss_pct: float = ISS_PADRAO, irrf_pct: float = IRRF_PCT_PADRAO,
    janela_correlacao: int = JANELA_CORRELACAO_PADRAO, limiar_correlacao: float = LIMIAR_CORRELACAO_PADRAO,
    min_dias_treino: int = 120, data_inicio=None, data_fim=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def gerar_sinal(candidatos_dia, retornos_pivot, data_decisao):
        grafo = construir_grafo_correlacao(retornos_pivot, data_decisao, janela_correlacao, limiar_correlacao)
        if grafo.number_of_edges() == 0:
            return pd.DataFrame()
        retornos_recentes = candidatos_dia.set_index("ticker")["retorno_5d"]
        return _sinal_por_vizinhanca(grafo, retornos_recentes, coluna_peso="weight")

    return _backtest_com_sinal(
        df_features, gerar_sinal, capital_total, capital_max_por_acao, horizonte, top_n,
        taxa_b3, corretagem_fixa, corretagem_percentual, iss_pct, irrf_pct,
        min_dias_treino, data_inicio, data_fim,
    )


# Alias por compatibilidade com a aplicação já existente (app_grafo.py).
backtest_grafo = backtest_spillover_threshold


# ---------------------------------------------------------------------------
# 2) Contágio via Árvore Geradora Mínima (Mantegna, 1999)
# ---------------------------------------------------------------------------
def backtest_spillover_mst(
    df_features: pd.DataFrame, capital_total: float, capital_max_por_acao: float,
    horizonte: int = HORIZONTE_PADRAO, top_n: int = 10, taxa_b3: float = TAXA_B3_PADRAO,
    corretagem_fixa: float = CORRETAGEM_PADRAO, corretagem_percentual: float = CORRETAGEM_PERCENTUAL_PADRAO,
    iss_pct: float = ISS_PADRAO, irrf_pct: float = IRRF_PCT_PADRAO,
    janela_correlacao: int = JANELA_CORRELACAO_PADRAO,
    min_dias_treino: int = 120, data_inicio=None, data_fim=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def gerar_sinal(candidatos_dia, retornos_pivot, data_decisao):
        mst = construir_grafo_mst(retornos_pivot, data_decisao, janela_correlacao)
        if mst.number_of_edges() == 0:
            return pd.DataFrame()
        retornos_recentes = candidatos_dia.set_index("ticker")["retorno_5d"]
        return _sinal_por_vizinhanca(mst, retornos_recentes, coluna_peso="correlacao")

    return _backtest_com_sinal(
        df_features, gerar_sinal, capital_total, capital_max_por_acao, horizonte, top_n,
        taxa_b3, corretagem_fixa, corretagem_percentual, iss_pct, irrf_pct,
        min_dias_treino, data_inicio, data_fim,
    )


# ---------------------------------------------------------------------------
# 3) Seleção por centralidade (ativos "estruturalmente importantes" na rede)
#    + ranqueamento por momentum próprio dentro desse grupo.
# ---------------------------------------------------------------------------
def backtest_centralidade(
    df_features: pd.DataFrame, capital_total: float, capital_max_por_acao: float,
    horizonte: int = HORIZONTE_PADRAO, top_n: int = 10, taxa_b3: float = TAXA_B3_PADRAO,
    corretagem_fixa: float = CORRETAGEM_PADRAO, corretagem_percentual: float = CORRETAGEM_PERCENTUAL_PADRAO,
    iss_pct: float = ISS_PADRAO, irrf_pct: float = IRRF_PCT_PADRAO,
    janela_correlacao: int = JANELA_CORRELACAO_PADRAO, limiar_correlacao: float = LIMIAR_CORRELACAO_PADRAO,
    fracao_mais_centrais: float = 0.3,
    min_dias_treino: int = 120, data_inicio=None, data_fim=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Regra: entre os `fracao_mais_centrais` ativos mais centrais do grafo do
    dia, o sinal de compra é o próprio momentum recente (retorno_5d) — aposta
    em CONTINUAÇÃO de tendência dos ativos "líderes" de mercado, não em
    convergência (é o oposto do racional das estratégias de spillover acima)."""
    def gerar_sinal(candidatos_dia, retornos_pivot, data_decisao):
        grafo = construir_grafo_correlacao(retornos_pivot, data_decisao, janela_correlacao, limiar_correlacao)
        if grafo.number_of_edges() == 0:
            return pd.DataFrame()
        centralidade = calcular_centralidade(grafo)
        if not centralidade:
            return pd.DataFrame()
        n_mais_centrais = max(1, int(len(centralidade) * fracao_mais_centrais))
        mais_centrais = {t for t, _ in sorted(centralidade.items(), key=lambda kv: kv[1], reverse=True)[:n_mais_centrais]}

        retornos_recentes = candidatos_dia.set_index("ticker")["retorno_5d"]
        linhas = [
            {"ticker": t, "centralidade": round(centralidade[t], 4), "sinal": round(float(retornos_recentes[t]), 4)}
            for t in mais_centrais
            if t in retornos_recentes.index and pd.notna(retornos_recentes.get(t))
        ]
        return pd.DataFrame(linhas)

    return _backtest_com_sinal(
        df_features, gerar_sinal, capital_total, capital_max_por_acao, horizonte, top_n,
        taxa_b3, corretagem_fixa, corretagem_percentual, iss_pct, irrf_pct,
        min_dias_treino, data_inicio, data_fim,
    )


# ---------------------------------------------------------------------------
# 4) Contágio dentro do cluster (comunidade de Louvain), não só vizinho direto
# ---------------------------------------------------------------------------
def backtest_comunidade(
    df_features: pd.DataFrame, capital_total: float, capital_max_por_acao: float,
    horizonte: int = HORIZONTE_PADRAO, top_n: int = 10, taxa_b3: float = TAXA_B3_PADRAO,
    corretagem_fixa: float = CORRETAGEM_PADRAO, corretagem_percentual: float = CORRETAGEM_PERCENTUAL_PADRAO,
    iss_pct: float = ISS_PADRAO, irrf_pct: float = IRRF_PCT_PADRAO,
    janela_correlacao: int = JANELA_CORRELACAO_PADRAO, limiar_correlacao: float = LIMIAR_CORRELACAO_PADRAO,
    min_dias_treino: int = 120, data_inicio=None, data_fim=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def gerar_sinal(candidatos_dia, retornos_pivot, data_decisao):
        grafo = construir_grafo_correlacao(retornos_pivot, data_decisao, janela_correlacao, limiar_correlacao)
        if grafo.number_of_edges() == 0:
            return pd.DataFrame()
        comunidade_de = calcular_comunidades(grafo)
        retornos_recentes = candidatos_dia.set_index("ticker")["retorno_5d"]

        por_comunidade: dict[int, list[float]] = {}
        for t, com in comunidade_de.items():
            r = retornos_recentes.get(t, np.nan)
            if pd.notna(r):
                por_comunidade.setdefault(com, []).append(r)

        linhas = []
        for t, com in comunidade_de.items():
            r = retornos_recentes.get(t, np.nan)
            membros = por_comunidade.get(com, [])
            if pd.isna(r) or len(membros) < 2:
                continue
            media_comunidade = float(np.mean(membros))
            linhas.append({"ticker": t, "comunidade": com, "sinal": round(media_comunidade - float(r), 4)})
        return pd.DataFrame(linhas)

    return _backtest_com_sinal(
        df_features, gerar_sinal, capital_total, capital_max_por_acao, horizonte, top_n,
        taxa_b3, corretagem_fixa, corretagem_percentual, iss_pct, irrf_pct,
        min_dias_treino, data_inicio, data_fim,
    )


# ---------------------------------------------------------------------------
# 5) GNN simplificada: 1 camada de convolução em grafo + regressão Ridge
# ---------------------------------------------------------------------------
def backtest_gnn_simplificado(
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
    alpha_ridge: float = 5.0,
    min_periodos_treino: int = 15,
    min_dias_treino: int = 120,
    data_inicio: str | pd.Timestamp | None = None,
    data_fim: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aviso sobre a escolha de design: uma GNN "de verdade" (PyTorch Geometric/DGL,
    múltiplas camadas, treino por gradiente) foi deliberadamente EVITADA aqui.
    Motivo: já vimos neste projeto (aba de Validação do modelo de ML) que mesmo
    um gradient boosting relativamente simples decora ruído quando os dados são
    poucos e o sinal é fraco — uma rede profunda, com muito mais parâmetros,
    tende a piorar esse problema, não melhorar, no volume de dados típico de
    uma carteira de ações.

    O que ISSO faz, de fato: para cada ativo, agrega o retorno recente dos
    vizinhos no grafo de correlação (uma "camada de convolução em grafo",
    matematicamente H' = A_norm @ H) e usa [retorno_próprio, retorno_agregado
    dos vizinhos] como entrada de uma regressão Ridge (regularização L2 forte,
    `alpha_ridge`) treinada em walk-forward — só com decisões passadas cujo
    alvo já esteja resolvido, mesma regra de segurança usada no modelo de ML
    do core.py. É uma GNN de UMA camada, rasa e fortemente regularizada de
    propósito, não um substituto direto para uma rede profunda.
    """
    base = df_features.dropna(subset=["retorno_1d", "retorno_5d", "retorno_futuro"]).copy()
    datas = np.sort(base["data_pregao"].unique())
    retornos_pivot = _pivot_retornos(df_features)
    custo_pct_ida_volta = 2 * (taxa_b3 + corretagem_percentual * (1 + iss_pct))

    capital_disponivel = capital_total
    operacoes: list[dict] = []
    resumo: list[dict] = []
    painel_historico: list[pd.DataFrame] = []  # snapshots de períodos passados, p/ treino

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

        # "Camada de convolução": para cada ticker, agrega retorno_1d/retorno_5d
        # dos vizinhos (média ponderada pela correlação) — igual ao princípio
        # de uma GCN de 1 camada, só que sem framework de deep learning.
        retornos_1d = candidatos_dia.set_index("ticker")["retorno_1d"]
        retornos_5d = candidatos_dia.set_index("ticker")["retorno_5d"]
        linhas_painel = []
        for ticker in grafo.nodes:
            if ticker not in retornos_1d.index or pd.isna(retornos_1d.get(ticker)):
                continue
            vizinhos = list(grafo.neighbors(ticker))
            pesos = [abs(grafo[ticker][v]["weight"]) for v in vizinhos if v in retornos_1d.index]
            if not vizinhos or not pesos or sum(pesos) == 0:
                continue
            viz_1d = [retornos_1d.get(v) for v in vizinhos if v in retornos_1d.index and pd.notna(retornos_1d.get(v))]
            viz_5d = [retornos_5d.get(v) for v in vizinhos if v in retornos_5d.index and pd.notna(retornos_5d.get(v))]
            if not viz_1d:
                continue
            linhas_painel.append({
                "ticker": ticker,
                "retorno_1d": float(retornos_1d[ticker]),
                "retorno_5d": float(retornos_5d[ticker]),
                "viz_retorno_1d": float(np.mean(viz_1d)),
                "viz_retorno_5d": float(np.mean(viz_5d)) if viz_5d else float(np.mean(viz_1d)),
                "retorno_futuro": candidatos_dia.set_index("ticker").loc[ticker, "retorno_futuro"]
                if ticker in candidatos_dia["ticker"].values else np.nan,
                "preco_fechamento": candidatos_dia.set_index("ticker").loc[ticker, "preco_fechamento"],
            })
        painel_dia = pd.DataFrame(linhas_painel)

        colunas_x = ["retorno_1d", "retorno_5d", "viz_retorno_1d", "viz_retorno_5d"]
        # Treino: só períodos passados cujo alvo já esteja resolvido (mesmo
        # buffer de segurança do core.backtest: fim do período <= decisão atual).
        treino_disponivel = pd.concat(painel_historico, ignore_index=True) if painel_historico else pd.DataFrame()
        treino_disponivel = treino_disponivel.dropna(subset=colunas_x + ["retorno_futuro"]) \
            if not treino_disponivel.empty else treino_disponivel

        if len(treino_disponivel) >= min_periodos_treino * 5 and not painel_dia.empty:
            modelo = Ridge(alpha=alpha_ridge)
            modelo.fit(treino_disponivel[colunas_x], treino_disponivel["retorno_futuro"])
            candidatos_validos = painel_dia.dropna(subset=colunas_x).copy()
            if not candidatos_validos.empty:
                candidatos_validos["sinal"] = modelo.predict(candidatos_validos[colunas_x])
                sinal = candidatos_validos[candidatos_validos["sinal"] > custo_pct_ida_volta] \
                    .sort_values("sinal", ascending=False).head(top_n)

                if not sinal.empty:
                    selecionados = _alocar_greedy(sinal, capital_disponivel, capital_max_por_acao)
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
                            "sinal": round(float(ativo["sinal"]), 4),
                            "retorno_realizado": round(float(ativo["retorno_futuro"]), 4),
                            "custo": round(custo, 2),
                            "irrf": round(irrf, 2),
                            "lucro": round(lucro, 2),
                        })

                    capital_disponivel += lucro_periodo
                    resumo.append({
                        "data_decisao": pd.Timestamp(data_decisao).date(),
                        "data_venda_prevista": data_venda.date() if pd.notna(data_venda) else None,
                        "n_operacoes": len(selecionados),
                        "lucro_periodo": round(lucro_periodo, 2),
                        "capital_apos_periodo": round(capital_disponivel, 2),
                    })

        # Guarda o snapshot deste período (mesmo sem ter operado) para treinar
        # decisões futuras, só depois que o alvo dele estiver resolvido — o
        # buffer é automático aqui porque só olhamos períodos ANTERIORES ao atual.
        if not painel_dia.empty:
            painel_historico.append(painel_dia)

        i += horizonte

    return pd.DataFrame(operacoes), pd.DataFrame(resumo)
