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

OTIMIZAÇÃO v2 (Fases A+B do plano_otimizacao_performance.md):
  - Fase A: Substituição do loop O(N²) Python por máscaras booleanas NumPy.
  - Fase B: Instanciação direta no iGraph (C-Core), eliminando o NetworkX
    do hot path. Pipe: NumPy → iGraph → leidenalg. Sem ponte de tradução.
"""
from __future__ import annotations

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


def construir_features_grafo(df: pd.DataFrame, horizonte: int = HORIZONTE_PADRAO) -> pd.DataFrame:
    """Só o que a estratégia de grafo precisa: retorno_1d (monta o grafo),
    retorno_5d (sinal de curto prazo) e retorno_futuro (realização real)."""
    g = df.groupby("ticker", group_keys=False)["preco_fechamento"]
    df["retorno_1d"] = g.pct_change(1)
    df["retorno_5d"] = g.pct_change(5)
    df["retorno_futuro"] = g.transform(lambda s: s.shift(-horizonte) / s - 1)
    return df


def _pivot_retornos(df: pd.DataFrame, coluna: str = "retorno_1d") -> pd.DataFrame:
    return df.pivot(index="data_pregao", columns="ticker", values=coluna)


# ---------------------------------------------------------------------------
# Grafo e sinal — PIPELINE OTIMIZADO (NumPy → iGraph → Leiden)
# ---------------------------------------------------------------------------
def construir_grafo_correlacao(
    retornos_pivot: pd.DataFrame,
    data_referencia: pd.Timestamp,
    janela: int = JANELA_CORRELACAO_PADRAO,
    limiar_correlacao: float = LIMIAR_CORRELACAO_PADRAO,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Constrói as arestas do grafo de correlação via máscaras NumPy vetorizadas.

    FASE A da otimização: elimina o loop duplo O(N²) em Python puro.
    Retorna uma tupla (tickers, indices_row, indices_col, pesos) onde:
      - tickers: array de strings com os nomes dos tickers (nós do grafo)
      - indices_row, indices_col: arrays de inteiros com as coordenadas das arestas
      - pesos: array de floats com os pesos (correlações) de cada aresta

    Usa somente dados ANTERIORES a `data_referencia` (sem vazamento).
    """
    janela_dados = retornos_pivot[retornos_pivot.index < data_referencia].tail(janela)
    min_periodos = max(20, janela // 3)

    if len(janela_dados) < min_periodos:
        return np.array([]), np.array([], dtype=int), np.array([], dtype=int), np.array([])

    corr = janela_dados.corr(min_periods=min_periodos)
    tickers = corr.columns.values  # array numpy de strings

    # --- FASE A: Máscara Booleana Trigonal (NumPy C-Core) ---
    matriz = corr.values.copy()
    np.fill_diagonal(matriz, np.nan)  # Remove autocorrelação (diagonal = 1.0)

    # Máscara triangular superior: evita contar arestas em dobro (A-B e B-A)
    mask_triu = np.triu(np.ones(matriz.shape, dtype=bool), k=1)

    # Máscara de validade: passou do limiar E não é NaN
    mask_valida = (np.abs(matriz) >= limiar_correlacao) & mask_triu & ~np.isnan(matriz)

    # Extrai coordenadas e pesos instantaneamente (sem loop For)
    indices_row, indices_col = np.where(mask_valida)
    pesos = np.abs(matriz[indices_row, indices_col])  # abs(): Leiden exige pesos positivos

    return tickers, indices_row, indices_col, pesos


def detectar_comunidades_leiden(
    tickers: np.ndarray,
    indices_row: np.ndarray,
    indices_col: np.ndarray,
    pesos: np.ndarray,
) -> tuple[dict, float, int]:
    """Detecta comunidades via Leiden diretamente no iGraph (C-Core).

    FASE B da otimização: instancia o grafo diretamente no iGraph usando
    TupleList, eliminando completamente o NetworkX e a ponte from_networkx().
    Pipe: NumPy arrays → iGraph.TupleList (C) → leidenalg (C++).

    Retorna: dicionario {ticker: cluster_id}, modularidade Q, e numero de clusters.
    """
    try:
        import igraph as ig
        import leidenalg
    except ImportError:
        raise ImportError("Por favor instale as bibliotecas 'igraph' e 'leidenalg' para detecção de comunidades.")

    if len(tickers) <= 1 or len(pesos) == 0:
        return {t: 0 for t in tickers}, 0.0, 1

    # --- FASE B: Instanciação direta no iGraph (sem NetworkX) ---
    # Mapeia índices numéricos de volta para nomes de tickers
    tickers_row = tickers[indices_row]
    tickers_col = tickers[indices_col]

    # Empacota em tuplas e injeta direto na engine C do iGraph
    arestas_com_pesos = list(zip(tickers_row, tickers_col, pesos))
    g_ig = ig.Graph.TupleList(arestas_com_pesos, weights=True)

    # Garante que nós isolados (sem arestas) entrem no grafo
    nomes_no_grafo = set(g_ig.vs["name"])
    nomes_faltantes = [t for t in tickers if t not in nomes_no_grafo]
    if nomes_faltantes:
        g_ig.add_vertices(nomes_faltantes)

    # Extrai pesos das arestas para o Leiden
    weights = g_ig.es['weight'] if g_ig.ecount() > 0 and 'weight' in g_ig.edge_attributes() else None

    partition = leidenalg.find_partition(
        g_ig,
        leidenalg.ModularityVertexPartition,
        weights=weights
    )

    mapeamento = {nome: cluster for nome, cluster in zip(g_ig.vs['name'], partition.membership)}
    q = partition.modularity
    n_clusters = len(partition)

    return mapeamento, q, n_clusters


def calcular_sinal_grafo(
    tickers_grafo: np.ndarray,
    retornos_recentes: pd.Series,
    mapeamento_leiden: dict,
) -> pd.DataFrame:
    """Calcula o sinal de spillover baseado nos clusters Leiden.

    O spillover subtrai a performance da Ação contra a do seu Macro-Cluster inteiro.
    Recebe a lista de tickers do grafo (array NumPy) ao invés de um objeto NetworkX.
    """
    linhas = []

    # Pre-agrega retornos válidos de cada cluster
    retornos_por_cluster: dict[int, list[float]] = {}
    for ticker, cluster_id in mapeamento_leiden.items():
        if ticker in retornos_recentes.index and pd.notna(retornos_recentes.get(ticker)):
            if cluster_id not in retornos_por_cluster:
                retornos_por_cluster[cluster_id] = []
            retornos_por_cluster[cluster_id].append(retornos_recentes[ticker])

    for ticker in tickers_grafo:
        if ticker not in retornos_recentes.index or pd.isna(retornos_recentes.get(ticker)):
            continue

        cluster_do_ticker = mapeamento_leiden.get(ticker)
        if cluster_do_ticker is None or cluster_do_ticker not in retornos_por_cluster:
            continue

        # Pega a "família" da ação (o continente Leiden)
        retornos_do_silo = list(retornos_por_cluster[cluster_do_ticker])
        r_proprio = retornos_recentes[ticker]

        # Remove a própria ação pra não poluir a média dos "outros"
        if len(retornos_do_silo) > 1:
            retornos_do_silo.remove(r_proprio)
            media_vizinhos = float(np.average(retornos_do_silo))
        else:
            continue  # Se for um cluster de 1 nó isolado, não há sinal estrutural

        retorno_proprio = float(r_proprio)
        linhas.append({
            "ticker": ticker,
            "grau": len(retornos_do_silo),  # Grau agora significa 'tamanho do cluster vizinho'
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

    OTIMIZADO v2: Pipeline NumPy → iGraph → Leiden (sem NetworkX no loop).
    """
    import time as _time  # Profiler temporário

    base = df_features.dropna(subset=["retorno_1d", "retorno_5d", "retorno_futuro"]).copy()
    datas = np.sort(base["data_pregao"].unique())
    retornos_pivot = _pivot_retornos(df_features)
    custo_pct_ida_volta = 2 * (taxa_b3 + corretagem_percentual * (1 + iss_pct))

    capital_disponivel = capital_total
    operacoes = []
    resumo = []

    # --- PROFILER: acumuladores de tempo por etapa ---
    _t_corr = 0.0
    _t_leiden = 0.0
    _t_sinal = 0.0
    _t_alocacao = 0.0
    _n_iteracoes = 0

    i = min_dias_treino
    if data_inicio is not None:
        i = max(i, int(np.searchsorted(datas, np.datetime64(pd.Timestamp(data_inicio)))))
    limite_fim = np.datetime64(pd.Timestamp(data_fim)) if data_fim is not None else None

    while i < len(datas):
        data_decisao = datas[i]
        if limite_fim is not None and data_decisao > limite_fim:
            break

        candidatos_dia = base[base["data_pregao"] == data_decisao]

        # --- ETAPA 1: Construção do Grafo (Correlação + NumPy) ---
        _t0 = _time.perf_counter()
        tickers, idx_row, idx_col, pesos = construir_grafo_correlacao(
            retornos_pivot, data_decisao, janela_correlacao, limiar_correlacao
        )
        n_arestas = len(pesos)
        _t_corr += _time.perf_counter() - _t0

        if n_arestas == 0 or candidatos_dia.empty:
            i += horizonte
            continue

        # --- ETAPA 2: Detecção de Comunidades (iGraph + Leiden) ---
        _t0 = _time.perf_counter()
        mapeamento_leiden, Q, n_clusters = detectar_comunidades_leiden(
            tickers, idx_row, idx_col, pesos
        )
        _t_leiden += _time.perf_counter() - _t0

        # --- ETAPA 3: Cálculo do Sinal Spillover ---
        _t0 = _time.perf_counter()
        retornos_recentes = candidatos_dia.set_index("ticker")["retorno_5d"]
        sinal = calcular_sinal_grafo(tickers, retornos_recentes, mapeamento_leiden)
        sinal = sinal[sinal["sinal_spillover"] > custo_pct_ida_volta].head(top_n)
        _t_sinal += _time.perf_counter() - _t0

        if sinal.empty:
            i += horizonte
            continue

        # --- ETAPA 4: Alocação e Contabilização ---
        _t0 = _time.perf_counter()
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
        _t_alocacao += _time.perf_counter() - _t0

        capital_disponivel += lucro_periodo
        _n_iteracoes += 1
        resumo.append({
            "data_decisao": pd.Timestamp(data_decisao).date(),
            "data_venda_prevista": data_venda.date() if pd.notna(data_venda) else None,
            "n_operacoes": len(selecionados),
            "n_arestas_grafo": n_arestas,
            "leiden_qtd_clusters": n_clusters,
            "leiden_modularidade": round(Q, 4),
            "lucro_periodo": round(lucro_periodo, 2),
            "capital_apos_periodo": round(capital_disponivel, 2),
        })
        i += horizonte

    # --- PROFILER: Relatório Final ---
    _t_total = _t_corr + _t_leiden + _t_sinal + _t_alocacao
    print(f"\n{'='*60}")
    print(f"  PROFILER DE PERFORMANCE — {_n_iteracoes} iterações")
    print(f"{'='*60}")
    print(f"  Correlação + NumPy mask : {_t_corr:8.3f}s  ({_t_corr/_t_total*100:5.1f}%)" if _t_total > 0 else "")
    print(f"  iGraph + Leiden         : {_t_leiden:8.3f}s  ({_t_leiden/_t_total*100:5.1f}%)" if _t_total > 0 else "")
    print(f"  Sinal Spillover         : {_t_sinal:8.3f}s  ({_t_sinal/_t_total*100:5.1f}%)" if _t_total > 0 else "")
    print(f"  Alocação + Contabil.    : {_t_alocacao:8.3f}s  ({_t_alocacao/_t_total*100:5.1f}%)" if _t_total > 0 else "")
    print(f"{'─'*60}")
    print(f"  TOTAL PIPELINE          : {_t_total:8.3f}s")
    print(f"  Média por iteração      : {_t_total/_n_iteracoes*1000:8.1f}ms" if _n_iteracoes > 0 else "")
    print(f"{'='*60}\n")

    return pd.DataFrame(operacoes), pd.DataFrame(resumo)
