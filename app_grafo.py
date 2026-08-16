"""Aplicação independente: estratégia de trading baseada em GRAFO DE CORRELAÇÃO
entre ações (market graph), sem machine learning.

Depende só de grafo_estrategia.py + streamlit/pandas. Não importa core.py.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import grafo_estrategia as ge
import metricas_risco as mr
import universo as uv

st.set_page_config(page_title="Estratégia de Grafo de Correlação (B3)", layout="wide")

# ── Fase 4: CSS para exportação PDF via navegador ──────────────────────────
st.markdown("""
<style>
@media print {
    /* Oculta sidebar, header, footer e controles interativos */
    section[data-testid="stSidebar"],
    header[data-testid="stHeader"],
    .stDeployButton,
    div[data-testid="stToolbar"],
    .stButton > button:not(.print-trigger),
    .stFileUploader,
    .stNumberInput,
    .stSelectbox,
    .stRadio,
    footer { display: none !important; }

    /* Remove margens para maximizar espaço */
    .block-container { padding: 0 !important; max-width: 100% !important; }

    /* Gráficos 16:9 */
    div[data-testid="stVegaLiteChart"] { width: 100% !important; aspect-ratio: 16/9; }

    /* Protege gráficos, tabelas e métricas contra corte entre páginas */
    div[data-testid="stVegaLiteChart"],
    div[data-testid="stDataFrame"],
    div[data-testid="stMetric"],
    div[data-testid="stExpander"] {
        page-break-inside: avoid !important;
        break-inside: avoid !important;
    }

    /* Visibilidade condicional: oculta interativo, mostra estático */
    .screen-only { display: none !important; }
    .print-only  { display: block !important; }
}

/* Fora do print: mostra interativo, oculta estático */
.print-only { display: none; }
</style>
""", unsafe_allow_html=True)

st.title("Estratégia B3 baseada em grafo de correlação")

st.warning(
    "⚠️ **Aviso:** estratégia estatística experimental, não é recomendação de investimento. "
    "Estudos acadêmicos (FGV EESP) mostram que a maioria dos investidores de curto prazo "
    "perde dinheiro na bolsa brasileira. Rode o backtest em vários períodos antes de confiar "
    "no resultado — um bom resultado num único período pode ser só sorte."
)

with st.expander("Metodologia (o que é isso, tecnicamente)"):
    st.markdown(
        "**Base comum, 'market graph'** (Boginski, Butenko & Pardalos, 2003/2005): cada ação "
        "é um nó; duas ações são conectadas por uma aresta quando a correlação dos retornos "
        "delas, numa janela recente, ultrapassa um limiar.\n\n"
        "**5 estratégias de decisão disponíveis**, todas comparáveis (mesmo motor de custo/"
        "imposto/alocação):\n"
        "1. Contágio via vizinhança direta no grafo limiarizado (spillover clássico)\n"
        "2. Contágio via Árvore Geradora Mínima (Mantegna, 1999)\n"
        "3. Seleção por centralidade + momentum (aposta em continuação, não convergência)\n"
        "4. Contágio dentro de comunidades detectadas por Louvain\n"
        "5. GNN simplificada (1 camada de agregação de vizinhos + regressão Ridge, walk-forward)\n\n"
        "Nenhuma das 5 usa modelo de machine learning profundo — a estratégia 5 é a única com "
        "algum treino estatístico, e é deliberadamente rasa/regularizada (ver docstring da "
        "função `backtest_gnn_simplificado` no código para o porquê)."
    )

arquivo = st.file_uploader("Arquivo processado (parquet ou csv, saída do b3_cotahist.py)", type=["parquet", "csv"])

# ── Fase 3: Filtro de Universo Investível ──────────────────────────────────
with st.expander("Filtros de Universo Investível (Fase 3)", expanded=False):
    aplicar_filtro = st.checkbox("Restringir a ativos líquidos e reais (recomendado)", value=True,
                                 help="Remove fundos, BDRs, papéis em RJ e ativos de pouquíssima liquidez.")
    col_u1, col_u2, col_u3 = st.columns(3)
    preco_min = col_u1.number_input("Preço Mínimo (R$)", value=1.0, step=0.5,
                                    help="Descarta ações negociadas na casa de centavos (onde 1 tick = 20% variação).")
    vol_min = col_u2.number_input("Volume Mediano (R$ na janela)", value=1_000_000.0, step=100000.0)
    neg_min = col_u3.number_input("Nº de Negócios (mediano)", value=100, step=10)
    
    col_u4, col_u5 = st.columns(2)
    sufixo_acao = col_u4.checkbox("Exigir formato de Ação (exclui 11, BDRs)", value=False)
    janela_liq = col_u5.number_input("Janela móvel de liquidez (dias)", value=60, step=10,
                                     help="Calcula a mediana dinamicamente usando os pregões passados, evitando viés futuro.")
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("Benchmarks para métricas de risco (opcional: SELIC e Ibovespa)"):
    col_selic, col_ibov = st.columns(2)
    arquivo_selic = col_selic.file_uploader(
        "SELIC diária (JSON, formato BCB/SGS série 11)", type=["json"],
        help='Lista de {"data": "DD/MM/AAAA", "valor": "0.024620"}, valor em % ao dia.',
    )
    arquivo_ibov = col_ibov.file_uploader(
        "Ibovespa histórico (CSV, formato Yahoo Finance)", type=["csv"],
        help="Colunas: data, abertura, maxima, minima, fechamento, fechamento_ajustado, volume.",
    )
    st.caption(
        "Sem esses arquivos, ainda calculo volatilidade/Sharpe/drawdown da estratégia sozinha "
        "(risco livre = 0), só não comparo com SELIC nem Ibovespa (alpha/beta ficam de fora)."
    )

col1, col2, col3, col4 = st.columns(4)
capital = col1.number_input("Capital total (R$)", min_value=0.0, value=100000.0, step=1000.0)
capital_max_por_acao = col2.number_input("Máximo por ação (R$)", min_value=0.0, value=1000.0, step=100.0)
horizonte = col3.number_input("Horizonte (pregões à frente)", min_value=1, value=ge.HORIZONTE_PADRAO)
top_n = col4.number_input("Nº máximo de ativos por período", min_value=1, value=10)

col5, col6 = st.columns(2)
janela_correlacao = col5.number_input(
    "Janela de correlação (pregões)", min_value=20, value=ge.JANELA_CORRELACAO_PADRAO, step=10,
    help="Quantos pregões passados usar para calcular a correlação entre as ações.",
)
limiar_correlacao = col6.number_input(
    "Correlação mínima para virar 'vizinho' no grafo", min_value=0.0, max_value=1.0,
    value=ge.LIMIAR_CORRELACAO_PADRAO, step=0.05,
    help="Só cria uma aresta entre duas ações se a correlação (em módulo) for maior que isso.",
)

st.caption(
    "Custos e impostos abaixo começam **zerados**. Preencha com os valores da sua corretora "
    "e da sua situação fiscal; o app não assume nenhum valor por conta própria."
)

with st.expander("Custos de transação (B3 + corretagem + ISS)"):
    c1, c2, c3 = st.columns(3)
    taxa_b3_pct = c1.number_input(
        "Taxa B3 por operação (%)", min_value=0.0, value=ge.TAXA_B3_PADRAO * 100,
        step=0.001, format="%.4f",
        help="Negociação + CCP + TTA, por ponta (compra ou venda). Consulte b3.com.br/tarifas.",
    )
    corretagem_fixa = c2.number_input(
        "Corretagem fixa por ordem (R$)", min_value=0.0, value=ge.CORRETAGEM_PADRAO, step=1.0,
    )
    corretagem_percentual = c3.number_input(
        "Corretagem percentual (%)", min_value=0.0, value=ge.CORRETAGEM_PERCENTUAL_PADRAO * 100,
        step=0.01, format="%.4f",
    )
    iss_pct = st.number_input(
        "ISS sobre a corretagem (%)", min_value=0.0, value=ge.ISS_PADRAO * 100, step=0.1,
        help="Imposto municipal (2% a 5% conforme o município). Se a corretagem é zero, o ISS também é.",
    )

with st.expander("Impostos sobre o resultado (IRRF + IR mensal, regra de swing trade)"):
    d1, d2, d3 = st.columns(3)
    irrf_pct = d1.number_input(
        "IRRF sobre venda / \"dedo-duro\" (%)", min_value=0.0, value=ge.IRRF_PCT_PADRAO * 100,
        step=0.001, format="%.5f",
        help="Regra oficial (swing trade): 0,005% sobre a venda, abatido do IR devido no mês.",
    )
    ir_aliquota_pct = d2.number_input(
        "Alíquota de IR sobre o lucro mensal (%)", min_value=0.0, value=ge.IR_ALIQUOTA_PADRAO * 100,
        step=1.0, help="Regra oficial (swing trade): 15% sobre o ganho líquido do mês.",
    )
    isencao_mensal = d3.number_input(
        "Isenção de IR se vendas do mês ≤ (R$)", min_value=0.0, value=ge.ISENCAO_VENDAS_MENSAL_PADRAO,
        step=1000.0, help="Regra oficial (swing trade): R$ 20.000/mês em vendas totais.",
    )

if arquivo and st.button("Carregar dados"):
    with st.spinner("Carregando dados e calculando retornos..."):
        caminho = f"/tmp/{arquivo.name}"
        with open(caminho, "wb") as f:
            f.write(arquivo.getbuffer())
        df = ge.carregar_dados(caminho)

        # ── Fase 3: Aplicação real dos filtros ────────────────────────────────
        if aplicar_filtro:
            df = uv.ajustar_por_fator_cotacao(df)
            df, relatorio_filtro = uv.filtrar_universo(
                df,
                preco_minimo=float(preco_min),
                volume_mediano_minimo=float(vol_min),
                negocios_minimos=int(neg_min),
                janela_liquidez=int(janela_liq),
                exigir_sufixo_acao=sufixo_acao,
            )
            df = uv.marcar_descontinuidades(df, max_dias_gap=10)
            st.session_state.relatorio_filtro = relatorio_filtro
        else:
            if "relatorio_filtro" in st.session_state:
                del st.session_state["relatorio_filtro"]
        # ───────────────────────────────────────────────────────────────────

        df = ge.construir_features_grafo(df, horizonte=int(horizonte))

        selic = None
        if arquivo_selic is not None:
            caminho_selic = f"/tmp/{arquivo_selic.name}"
            with open(caminho_selic, "wb") as f:
                f.write(arquivo_selic.getbuffer())
            selic = mr.carregar_selic(caminho_selic)

        ibovespa = None
        if arquivo_ibov is not None:
            caminho_ibov = f"/tmp/{arquivo_ibov.name}"
            with open(caminho_ibov, "wb") as f:
                f.write(arquivo_ibov.getbuffer())
            ibovespa = mr.carregar_ibovespa(caminho_ibov)

    st.session_state.dados_grafo = dict(
        df=df, capital=capital, capital_max_por_acao=capital_max_por_acao,
        horizonte=int(horizonte), top_n=int(top_n),
        janela_correlacao=int(janela_correlacao), limiar_correlacao=limiar_correlacao,
        taxa_b3=taxa_b3_pct / 100, corretagem_fixa=corretagem_fixa,
        corretagem_percentual=corretagem_percentual / 100, iss_pct=iss_pct / 100,
        irrf_pct=irrf_pct / 100, ir_aliquota=ir_aliquota_pct / 100,
        isencao_mensal=isencao_mensal, selic=selic, ibovespa=ibovespa,
    )
    msg = f"Dados carregados: {len(df):,} linhas, {df['ticker'].nunique()} tickers."
    if selic is not None:
        msg += f" SELIC: {len(selic)} dias."
    if ibovespa is not None:
        msg += f" Ibovespa: {len(ibovespa)} dias."
    st.success(msg)

if "dados_grafo" in st.session_state:
    d = st.session_state.dados_grafo
    df = d["df"]

    st.divider()
    st.subheader("Backtest")

    modo_periodo = st.radio(
        "Período a simular", ["Histórico completo", "Um dia específico", "Intervalo de datas"],
        horizontal=True,
    )
    data_min = pd.Timestamp(df["data_pregao"].min()).date()
    data_max = pd.Timestamp(df["data_pregao"].max()).date()
    data_inicio = data_fim = None
    if modo_periodo == "Um dia específico":
        dia = st.date_input("Data da decisão de compra", value=data_max, min_value=data_min, max_value=data_max)
        data_inicio = data_fim = dia
    elif modo_periodo == "Intervalo de datas":
        intervalo = st.date_input(
            "Intervalo de datas de decisão", value=(data_min, data_max),
            min_value=data_min, max_value=data_max,
        )
        if isinstance(intervalo, tuple) and len(intervalo) == 2:
            data_inicio, data_fim = intervalo
        else:
            st.info("Selecione a data final do intervalo para continuar.")

    ESTRATEGIAS = {
        "1. Vizinhança direta (limiar de correlação)": ge.backtest_spillover_threshold,
        "2. Árvore Geradora Mínima (Mantegna)": ge.backtest_spillover_mst,
        "3. Centralidade + momentum": ge.backtest_centralidade,
        "4. Comunidades (Louvain)": ge.backtest_comunidade,
        "5. GNN simplificada (1 camada + Ridge)": ge.backtest_gnn_simplificado,
    }

    def _rodar_estrategia(nome_fn, **kwargs):
        # A estratégia de MST não usa limiar_correlacao; as demais usam. Filtra
        # os kwargs que a função realmente aceita, pra reaproveitar a mesma chamada.
        import inspect
        aceitos = set(inspect.signature(nome_fn).parameters)
        return nome_fn(**{k: v for k, v in kwargs.items() if k in aceitos})

    modo = st.radio("Modo", ["Rodar uma estratégia", "Comparar as 5 estratégias"], horizontal=True)
    viz_avancada = st.toggle("📊 Visualização Institucional (Log-scale, Drawdown, Facetas)", value=False,
                              help="Liga gráficos Plotly com eixo logarítmico, subplot de drawdown, facetamento por estratégia e resampling semanal. Desligado = gráfico simples original.")

    kwargs_comuns = dict(
        df_features=df, capital_total=d["capital"], capital_max_por_acao=d["capital_max_por_acao"],
        horizonte=d["horizonte"], top_n=d["top_n"],
        taxa_b3=d["taxa_b3"], corretagem_fixa=d["corretagem_fixa"],
        corretagem_percentual=d["corretagem_percentual"], iss_pct=d["iss_pct"],
        irrf_pct=d["irrf_pct"], janela_correlacao=d["janela_correlacao"],
        limiar_correlacao=d["limiar_correlacao"], data_inicio=data_inicio, data_fim=data_fim,
    )

    if modo == "Rodar uma estratégia":
        escolha = st.selectbox("Estratégia", list(ESTRATEGIAS.keys()))
        if st.button("Rodar backtest"):
            with st.spinner("Construindo grafos e simulando..."):
                operacoes, resumo = _rodar_estrategia(ESTRATEGIAS[escolha], **kwargs_comuns)
                ir_mensal = ge.calcular_ir_mensal(
                    operacoes, ir_aliquota=d["ir_aliquota"], isencao_vendas_mensal=d["isencao_mensal"]
                )
                st.session_state.resultado_backtest_grafo = (operacoes, resumo, ir_mensal, d["capital"])

        if "resultado_backtest_grafo" in st.session_state:
            operacoes, resumo, ir_mensal, capital_inicial = st.session_state.resultado_backtest_grafo
            if resumo.empty:
                st.info("Nenhum período simulável com esses parâmetros (janela de correlação ou período curtos demais).")
            else:
                capital_final_bruto = resumo["capital_apos_periodo"].iloc[-1]
                total_darf = ir_mensal["darf_a_pagar"].sum() if not ir_mensal.empty else 0.0
                capital_final_liquido = capital_final_bruto - total_darf

                m1, m2, m3 = st.columns(3)
                m1.metric("Capital final (antes de IR)", f"R$ {capital_final_bruto:,.2f}",
                          f"{(capital_final_bruto/capital_inicial-1)*100:.2f}%")
                m2.metric("DARF total pago no período", f"R$ {total_darf:,.2f}")
                m3.metric("Capital final (líquido de IR)", f"R$ {capital_final_liquido:,.2f}",
                          f"{(capital_final_liquido/capital_inicial-1)*100:.2f}%")

                periodos_positivos = float((resumo["lucro_periodo"] > 0).mean())
                st.caption(f"Períodos com lucro operacional positivo: {periodos_positivos:.1%} de {len(resumo)} decisões.")

                metricas = mr.calcular_metricas_risco(
                    resumo, capital_inicial, selic=d.get("selic"), ibovespa=d.get("ibovespa"), operacoes=operacoes
                )
                if metricas:
                    st.subheader("Risco e comparação com benchmarks")
                    if metricas.get("periodos_excluidos_sem_data_venda"):
                        st.caption(
                            f"{metricas['periodos_excluidos_sem_data_venda']} período(s) excluído(s) "
                            "desta análise por não ter data de venda definida (fim do histórico)."
                        )
                    rm1, rm2, rm3, rm4 = st.columns(4)
                    rm1.metric("Sharpe", metricas.get("sharpe", "—"))
                    rm2.metric("Sortino", metricas.get("sortino", "—"))
                    rm3.metric("Calmar", metricas.get("calmar", "—"))
                    rm4.metric("Máximo drawdown", f"{metricas.get('max_drawdown_pct', '—')}%")

                    rm5, rm6, rm7, rm8 = st.columns(4)
                    rm5.metric("Retorno anualizado", f"{metricas.get('retorno_anualizado_pct', '—')}%")
                    rm6.metric("Volatilidade anualizada", f"{metricas.get('volatilidade_anualizada_pct', '—')}%")
                    rm7.metric("Win rate", f"{metricas.get('win_rate_pct', '—')}%")
                    rm8.metric("Profit factor", metricas.get("profit_factor", "—"))

                    if "retorno_selic_pct" in metricas:
                        st.caption(f"Retorno SELIC no mesmo período: {metricas['retorno_selic_pct']}%")
                    if "retorno_ibovespa_pct" in metricas:
                        rb1, rb2, rb3, rb4 = st.columns(4)
                        rb1.metric("Retorno Ibovespa (mesmo período)", f"{metricas['retorno_ibovespa_pct']}%")
                        rb2.metric("Beta (vs. Ibovespa)", metricas.get("beta", "—"))
                        rb3.metric("Retorno esperado (CAPM)", f"{metricas.get('retorno_esperado_capm_pct', '—')}%")
                        rb4.metric("Alfa de Jensen (a.a.)", f"{metricas.get('alfa_jensen_pct_aa', '—')}%")
                        st.caption(
                            "Alfa de Jensen = retorno anualizado da estratégia − retorno esperado pelo CAPM "
                            "(dado o beta assumido). Positivo = gerou valor além do risco; negativo = destruiu "
                            "valor mesmo tomando aquele risco."
                        )
                    if d.get("selic") is None or d.get("ibovespa") is None:
                        st.caption(
                            "Envie os arquivos de SELIC e/ou Ibovespa (expander acima) para ver Alfa de "
                            "Jensen, Beta e a comparação completa com os dois benchmarks."
                        )

                # ── Fase 1: curva de capital com benchmarks ─────────────
                st.subheader("Evolução do capital")
                _r = resumo.copy()
                _r["data_decisao"] = pd.to_datetime(_r["data_decisao"])
                curva_df = _r.set_index("data_decisao")[["capital_apos_periodo"]].rename(
                    columns={"capital_apos_periodo": "Estratégia"}
                )
                _data_min_bt = _r["data_decisao"].min()
                _data_max_bt = _r["data_decisao"].max()
                if d.get("selic") is not None:
                    _selic_curva = mr.curva_capital_selic(d["selic"], _data_min_bt, _data_max_bt, capital_inicial)
                    if not _selic_curva.empty:
                        curva_df = curva_df.join(_selic_curva.rename("SELIC"), how="outer")
                if d.get("ibovespa") is not None:
                    _ibov_curva = mr.curva_capital_ibovespa(d["ibovespa"], _data_min_bt, _data_max_bt, capital_inicial)
                    if not _ibov_curva.empty:
                        curva_df = curva_df.join(_ibov_curva.rename("Ibovespa"), how="outer")
                
                # Corrige "código de barras": DatetimeIndex ordenado garante que o ffill desça o tempo sem errar o benchmark
                curva_df = curva_df.sort_index().ffill().fillna(capital_inicial)
                # Normaliza para base 100
                curva_df_norm = (curva_df / capital_inicial) * 100

                if viz_avancada:
                    # ── Item E: Resampling semanal (só visual) ──
                    curva_plot = curva_df_norm.resample('W').last().dropna(how='all')
                    # ── Item B+C: Plotly com log-scale + subplot de drawdown ──
                    dd_series = mr.serie_drawdown(resumo, capital_inicial) * 100  # em %
                    dd_series = dd_series.groupby(dd_series.index).last()  # remove datas duplicadas
                    dd_plot = dd_series.resample('W').last().dropna()
                    fig = make_subplots(
                        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        row_heights=[0.7, 0.3],
                        subplot_titles=("Capital (Base 100, Log)", "Drawdown (%)")
                    )
                    for col in curva_plot.columns:
                        fig.add_trace(go.Scatter(
                            x=curva_plot.index, y=curva_plot[col], name=col, mode="lines"
                        ), row=1, col=1)
                    fig.add_trace(go.Scatter(
                        x=dd_plot.index, y=dd_plot.values, name="Drawdown",
                        fill="tozeroy", line=dict(color="crimson", width=1),
                        fillcolor="rgba(220,20,60,0.3)", showlegend=False,
                    ), row=2, col=1)
                    fig.update_yaxes(type="log", title_text="Base 100 (log)", row=1, col=1)
                    fig.update_yaxes(title_text="DD %", row=2, col=1)
                    fig.update_xaxes(title_text="Data", row=2, col=1)
                    fig.update_layout(
                        template="plotly_dark", height=700, hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        margin=dict(l=60, r=30, t=60, b=40),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.line_chart(curva_df_norm)

                # ── Fase 2: gráficos complementares ────────────────────
                with st.expander("Análise complementar (gráficos)", expanded=True):
                    # DARF mensal
                    if not ir_mensal.empty:
                        st.markdown("##### DARF mensal (R$)")
                        darf_chart = ir_mensal.set_index("mes")[["darf_a_pagar"]]
                        st.bar_chart(darf_chart)

                    # Drawdown
                    st.markdown("##### Drawdown ao longo do tempo")
                    dd_series = mr.serie_drawdown(resumo, capital_inicial)
                    st.area_chart(dd_series.rename("Drawdown (%)"))

                    # Distribuição de lucro por operação
                    if not operacoes.empty and "lucro" in operacoes.columns:
                        st.markdown("##### Distribuição do lucro por operação")
                        hist_vals, hist_bins = np.histogram(operacoes["lucro"].dropna(), bins=30)
                        bin_labels = [f"{hist_bins[i]:.0f}" for i in range(len(hist_vals))]
                        st.bar_chart(pd.DataFrame({"Frequência": hist_vals}, index=bin_labels))

                    # Retorno mensal
                    st.markdown("##### Retorno mensal")
                    _r_mensal = resumo.copy()
                    _r_mensal["data_decisao"] = pd.to_datetime(_r_mensal["data_decisao"])
                    _r_mensal["mes"] = _r_mensal["data_decisao"].dt.to_period("M").astype(str)
                    retorno_mes = _r_mensal.groupby("mes")["lucro_periodo"].sum()
                    st.bar_chart(retorno_mes.rename("Lucro mensal (R$)"))

                    # Dispersão sinal vs retorno realizado
                    if not operacoes.empty and "sinal" in operacoes.columns and "retorno_realizado" in operacoes.columns:
                        st.markdown("##### Sinal previsto vs. retorno realizado")
                        scatter_df = operacoes[["sinal", "retorno_realizado"]].dropna()
                        st.scatter_chart(scatter_df, x="sinal", y="retorno_realizado")

                st.subheader("Resumo por período")
                st.dataframe(resumo, use_container_width=True)
                
                # ── Exibe o log do filtro da Fase 3 se ativado ───────────
                if "relatorio_filtro" in st.session_state:
                    st.subheader("Impacto do Filtro de Universo (Auditoria)")
                    st.dataframe(st.session_state.relatorio_filtro, use_container_width=True)
                # ────────────────────────────────────────────────────────

                st.subheader("Apuração de IR mensal (DARF)")
                if ir_mensal.empty:
                    st.info("Nenhuma venda com data suficiente para apurar IR mensal.")
                else:
                    st.dataframe(ir_mensal, use_container_width=True)
                st.subheader("Todas as operações simuladas")
                st.dataframe(operacoes, use_container_width=True)

                # ── Fase 4: botão PDF ──────────────────────────────────
                st.markdown("---")
                import streamlit.components.v1 as components
                components.html(
                    """
                    <button onclick="window.parent.print()" style="padding:10px 24px;font-size:16px;background:#1f77b4;color:white;border:none;border-radius:6px;cursor:pointer;width:100%;">
                    📄 Gerar PDF do Relatório (via Navegador)
                    </button>
                    """,
                    height=50
                )

    else:
        st.caption(
            "Roda as 5 estratégias com os MESMOS parâmetros (capital, custos, impostos, período), "
            "pra comparação justa. Pode demorar mais que rodar uma só."
        )
        if st.button("Comparar as 5 estratégias"):
            linhas_comparacao = []
            curvas = {}
            detalhes = {}
            barra = st.progress(0.0, text="Iniciando...")
            for idx, (nome, fn) in enumerate(ESTRATEGIAS.items()):
                barra.progress(idx / len(ESTRATEGIAS), text=f"Rodando: {nome}")
                operacoes, resumo = _rodar_estrategia(fn, **kwargs_comuns)
                ir_mensal = ge.calcular_ir_mensal(
                    operacoes, ir_aliquota=d["ir_aliquota"], isencao_vendas_mensal=d["isencao_mensal"]
                )
                if resumo.empty:
                    linhas_comparacao.append({
                        "Estratégia": nome, "Nº operações": 0, "Capital final líquido": d["capital"],
                        "Retorno (%)": 0.0, "Win rate (%)": None,
                    })
                    continue
                capital_final = resumo["capital_apos_periodo"].iloc[-1]
                darf = ir_mensal["darf_a_pagar"].sum() if not ir_mensal.empty else 0.0
                capital_liquido = capital_final - darf
                metricas = mr.calcular_metricas_risco(
                    resumo, d["capital"], selic=d.get("selic"), ibovespa=d.get("ibovespa"), operacoes=operacoes
                )
                linhas_comparacao.append({
                    "Estratégia": nome,
                    "Nº operações": len(operacoes),
                    "Capital final líquido": round(capital_liquido, 2),
                    "Retorno (%)": round((capital_liquido / d["capital"] - 1) * 100, 2),
                    "Win rate (%)": metricas.get("win_rate_pct"),
                    "Profit factor": metricas.get("profit_factor"),
                    "Sharpe": metricas.get("sharpe"),
                    "Sortino": metricas.get("sortino"),
                    "Calmar": metricas.get("calmar"),
                    "Máx. drawdown (%)": metricas.get("max_drawdown_pct"),
                    "Beta vs Ibov": metricas.get("beta"),
                    "Alfa de Jensen (%a.a.)": metricas.get("alfa_jensen_pct_aa"),
                })
                _r_curva = resumo.copy()
                _r_curva["data_decisao"] = pd.to_datetime(_r_curva["data_decisao"])
                curvas[nome] = _r_curva.set_index("data_decisao")["capital_apos_periodo"]
                detalhes[nome] = (operacoes, resumo, ir_mensal)
            barra.progress(1.0, text="Concluído.")

            comparativo = pd.DataFrame(linhas_comparacao).sort_values("Retorno (%)", ascending=False)
            st.subheader("Comparação entre estratégias")
            st.dataframe(comparativo, use_container_width=True)
            melhor = comparativo.iloc[0]["Estratégia"]
            st.success(f"Melhor resultado neste período/dados: **{melhor}**")
            st.caption(
                "Cuidado ao generalizar a partir de um único período: rode em janelas de tempo "
                "diferentes (ou intervalos de data distintos) antes de concluir que uma estratégia "
                "é consistentemente melhor — pode ser só sorte naquele recorte específico."
            )
            if d.get("selic") is None or d.get("ibovespa") is None:
                st.caption(
                    "Colunas de Sharpe/volatilidade aparecem mesmo sem SELIC/Ibovespa (risco livre "
                    "= 0). Alpha e Beta ficam vazios até você enviar o arquivo do Ibovespa."
                )

            if curvas:
                # ── Fase 1: adicionar benchmarks à comparação ──────────
                if d.get("selic") is not None or d.get("ibovespa") is not None:
                    _todas_datas = pd.concat([s for s in curvas.values()], axis=1)
                    _data_min_cmp = _todas_datas.index.min()
                    _data_max_cmp = _todas_datas.index.max()
                    if d.get("selic") is not None:
                        _s = mr.curva_capital_selic(d["selic"], _data_min_cmp, _data_max_cmp, d["capital"])
                        if not _s.empty:
                            curvas["SELIC"] = _s
                    if d.get("ibovespa") is not None:
                        _ib = mr.curva_capital_ibovespa(d["ibovespa"], _data_min_cmp, _data_max_cmp, d["capital"])
                        if not _ib.empty:
                            curvas["Ibovespa"] = _ib

                st.subheader("Evolução do capital por estratégia (Base 100)")
                _cap = d.get("capital", 100000.0)
                curvas_df = pd.DataFrame(curvas)
                curvas_df = curvas_df.sort_index().ffill().fillna(_cap)
                curvas_df_norm = (curvas_df / _cap) * 100

                if viz_avancada:
                    # ── Item E: Resampling semanal ──
                    curvas_plot = curvas_df_norm.resample('W').last().dropna(how='all')

                    # ── Item B+C: Plotly consolidado com log-scale + Drawdown comparativo ──
                    _nomes_estrat = [c for c in curvas_df.columns if c not in ("SELIC", "Ibovespa")]
                    dd_dict = {}
                    for _nome_e in _nomes_estrat:
                        if _nome_e in detalhes:
                            _, _res_e, _ = detalhes[_nome_e]
                            _dd = mr.serie_drawdown(_res_e, _cap) * 100
                            _dd = _dd.groupby(_dd.index).last()  # remove datas duplicadas
                            dd_dict[_nome_e] = _dd
                    dd_df = pd.DataFrame(dd_dict)
                    if not dd_df.empty:
                        dd_df = dd_df.sort_index().ffill().fillna(0.0)
                        dd_plot = dd_df.resample('W').last().dropna(how='all')
                    else:
                        dd_plot = pd.DataFrame()

                    fig_comp = make_subplots(
                        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        row_heights=[0.7, 0.3],
                        subplot_titles=("Capital (Base 100, Log)", "Drawdown Comparativo (%)")
                    )
                    for col in curvas_plot.columns:
                        fig_comp.add_trace(go.Scatter(
                            x=curvas_plot.index, y=curvas_plot[col], name=col, mode="lines"
                        ), row=1, col=1)
                    if not dd_plot.empty:
                        for col in dd_plot.columns:
                            fig_comp.add_trace(go.Scatter(
                                x=dd_plot.index, y=dd_plot[col], name=f"DD {col[:6]}",
                                mode="lines", line=dict(width=1),
                            ), row=2, col=1)
                    fig_comp.update_yaxes(type="log", title_text="Base 100 (log)", row=1, col=1)
                    fig_comp.update_yaxes(title_text="DD %", row=2, col=1)
                    fig_comp.update_xaxes(title_text="Data", row=2, col=1)
                    fig_comp.update_layout(
                        template="plotly_dark", height=750, hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        margin=dict(l=60, r=30, t=60, b=40),
                    )
                    st.plotly_chart(fig_comp, use_container_width=True)

                    # ── Item D: Facetamento (Small Multiples) ──
                    st.subheader("Visão individual: Estratégia vs Benchmarks")
                    _benchmarks = [c for c in curvas_plot.columns if c in ("SELIC", "Ibovespa")]
                    tabs = st.tabs([n[:25] for n in _nomes_estrat])
                    for tab, nome_e in zip(tabs, _nomes_estrat):
                        with tab:
                            fig_facet = go.Figure()
                            if nome_e in curvas_plot.columns:
                                fig_facet.add_trace(go.Scatter(
                                    x=curvas_plot.index, y=curvas_plot[nome_e],
                                    name=nome_e, mode="lines", line=dict(width=2.5)
                                ))
                            for bm in _benchmarks:
                                fig_facet.add_trace(go.Scatter(
                                    x=curvas_plot.index, y=curvas_plot[bm],
                                    name=bm, mode="lines", line=dict(width=1.5, dash="dot")
                                ))
                            fig_facet.update_yaxes(type="log", title_text="Base 100 (log)")
                            fig_facet.update_layout(
                                template="plotly_dark", height=400, hovermode="x unified",
                                title=nome_e,
                                margin=dict(l=50, r=20, t=50, b=30),
                            )
                            st.plotly_chart(fig_facet, use_container_width=True)
                else:
                    st.line_chart(curvas_df_norm)

            st.session_state.comparacao_grafo = detalhes

            # ── Fase 4: botão PDF na comparação ────────────────────
            st.markdown("---")
            import streamlit.components.v1 as components
            components.html(
                """
                <button onclick="window.parent.print()" style="padding:10px 24px;font-size:16px;background:#1f77b4;color:white;border:none;border-radius:6px;cursor:pointer;width:100%;">
                📄 Gerar PDF do Relatório (via Navegador)
                </button>
                """,
                height=50
            )

        if "comparacao_grafo" in st.session_state:
            with st.expander("Ver detalhes de cada estratégia (operações e IR)", expanded=True):
                nome_detalhe = st.selectbox("Estratégia para detalhar", list(st.session_state.comparacao_grafo.keys()))
                operacoes, resumo, ir_mensal = st.session_state.comparacao_grafo[nome_detalhe]
                st.dataframe(resumo, use_container_width=True)
                if not ir_mensal.empty:
                    st.dataframe(ir_mensal, use_container_width=True)
                st.dataframe(operacoes, use_container_width=True)