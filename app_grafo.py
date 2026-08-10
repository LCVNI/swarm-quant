"""Aplicação independente: estratégia de trading baseada em GRAFO DE CORRELAÇÃO
entre ações (market graph), sem machine learning.

Depende só de grafo_estrategia.py + streamlit/pandas. Não importa core.py.
"""
import pandas as pd
import streamlit as st

import grafo_estrategia as ge
import metricas_risco as mr

st.set_page_config(page_title="Estratégia de Grafo de Correlação (B3)", layout="wide")
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

                st.line_chart(resumo.set_index("data_decisao")["capital_apos_periodo"])
                st.subheader("Resumo por período")
                st.dataframe(resumo, use_container_width=True)
                st.subheader("Apuração de IR mensal (DARF)")
                if ir_mensal.empty:
                    st.info("Nenhuma venda com data suficiente para apurar IR mensal.")
                else:
                    st.dataframe(ir_mensal, use_container_width=True)
                st.subheader("Todas as operações simuladas")
                st.dataframe(operacoes, use_container_width=True)

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
                curvas[nome] = resumo.set_index("data_decisao")["capital_apos_periodo"]
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
                st.subheader("Evolução do capital por estratégia")
                st.line_chart(pd.DataFrame(curvas))

            st.session_state.comparacao_grafo = detalhes

        if "comparacao_grafo" in st.session_state:
            with st.expander("Ver detalhes de cada estratégia (operações e IR)"):
                nome_detalhe = st.selectbox("Estratégia para detalhar", list(st.session_state.comparacao_grafo.keys()))
                operacoes, resumo, ir_mensal = st.session_state.comparacao_grafo[nome_detalhe]
                st.dataframe(resumo, use_container_width=True)
                st.dataframe(ir_mensal, use_container_width=True) if not ir_mensal.empty else None
                st.dataframe(operacoes, use_container_width=True)
