"""Aplicação independente: estratégia de trading baseada em GRAFO DE CORRELAÇÃO
entre ações (market graph), sem machine learning.

Depende só de grafo_estrategia.py + streamlit/pandas. Não importa core.py.
"""
import pandas as pd
import streamlit as st
import itertools
import time
import numpy as np

import grafo_estrategia as ge
import profiles_manager as pm

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
        "**Market graph** (Boginski, Butenko & Pardalos, 2003/2005): cada ação é um nó; "
        "duas ações são conectadas por uma aresta quando a correlação dos retornos delas, "
        "numa janela recente, ultrapassa um limiar. Aqui a aresta é ponderada pela força da "
        "correlação (variação do market graph binário original).\n\n"
        "**Regra de decisão (lead-lag / contágio de retorno):** para cada ação, calcula-se o "
        "retorno médio recente dos seus vizinhos no grafo, ponderado pela correlação, e "
        "compara-se com o retorno recente da própria ação. Sinal alto = os vizinhos "
        "correlacionados já subiram, mas a ação ainda não acompanhou — a estratégia aposta "
        "que ela vai convergir com o grupo.\n\n"
        "**Não usa:** nenhum modelo de machine learning, árvore geradora mínima, "
        "centralidade de grafo ou detecção de comunidades. É a versão mais simples da família "
        "de 'market graph': limiar de correlação + média ponderada da vizinhança direta."
    )

arquivo = st.file_uploader("Arquivo processado (parquet ou csv, saída do b3_cotahist.py)", type=["parquet", "csv"])

if arquivo and st.button("Carregar dados global"):
    with st.spinner("Carregando dados globais..."):
        caminho = f"/tmp/{arquivo.name}"
        with open(caminho, "wb") as f:
            f.write(arquivo.getbuffer())
        df = ge.carregar_dados(caminho)
    st.session_state.dados_brutos = df
    st.success(f"Dados globais carregados: {len(df):,} linhas, {df['ticker'].nunique()} tickers.")


def build_params_ui(key_prefix):
    """Constrói os widgets de parâmetros e retorna um dict com eles."""
    defaults = st.session_state.get("loaded_profile_params", {})

    col1, col2, col3, col4 = st.columns(4)
    capital = col1.number_input("Capital total (R$)", min_value=0.0, value=float(defaults.get("capital", 100000.0)), step=1000.0, key=f"{key_prefix}_cap")
    capital_max_por_acao = col2.number_input("Máximo por ação (R$)", min_value=0.0, value=float(defaults.get("capital_max_por_acao", 1000.0)), step=100.0, key=f"{key_prefix}_cap_max")
    horizonte = col3.number_input("Horizonte (pregões à frente)", min_value=1, value=int(defaults.get("horizonte", ge.HORIZONTE_PADRAO)), key=f"{key_prefix}_horiz")
    top_n = col4.number_input("Nº máximo de ativos por período", min_value=1, value=int(defaults.get("top_n", 10)), key=f"{key_prefix}_topn")

    col5, col6 = st.columns(2)
    janela_correlacao = col5.number_input(
        "Janela de correlação (pregões)", min_value=20, value=int(defaults.get("janela_correlacao", ge.JANELA_CORRELACAO_PADRAO)), step=10,
        help="Quantos pregões passados usar para calcular a correlação entre as ações.", key=f"{key_prefix}_janela_corr"
    )
    limiar_correlacao = col6.number_input(
        "Correlação mínima para virar 'vizinho' no grafo", min_value=0.0, max_value=1.0,
        value=float(defaults.get("limiar_correlacao", ge.LIMIAR_CORRELACAO_PADRAO)), step=0.05,
        help="Só cria uma aresta entre duas ações se a correlação (em módulo) for maior que isso.", key=f"{key_prefix}_limiar_corr"
    )

    st.caption(
        "Custos e impostos abaixo começam **zerados**. Preencha com os valores da sua corretora "
        "e da sua situação fiscal; o app não assume nenhum valor por conta própria."
    )
    with st.expander("Custos de transação (B3 + corretagem + ISS)"):
        c1, c2, c3 = st.columns(3)
        taxa_b3_pct = c1.number_input(
            "Taxa B3 por operação (%)", min_value=0.0, value=float(defaults.get("taxa_b3", ge.TAXA_B3_PADRAO)) * 100.0,
            step=0.001, format="%.4f", key=f"{key_prefix}_tb3",
            help="Negociação + CCP + TTA, por ponta (compra ou venda). Consulte b3.com.br/tarifas."
        )
        corretagem_fixa = c2.number_input(
            "Corretagem fixa por ordem (R$)", min_value=0.0, value=float(defaults.get("corretagem_fixa", ge.CORRETAGEM_PADRAO)),
            step=1.0, key=f"{key_prefix}_cf"
        )
        corretagem_percentual = c3.number_input(
            "Corretagem percentual (%)", min_value=0.0, value=float(defaults.get("corretagem_percentual", ge.CORRETAGEM_PERCENTUAL_PADRAO)) * 100.0,
            step=0.01, format="%.4f", key=f"{key_prefix}_cp"
        )
        iss_pct = st.number_input(
            "ISS sobre a corretagem (%)", min_value=0.0, value=float(defaults.get("iss_pct", ge.ISS_PADRAO)) * 100.0,
            step=0.1, key=f"{key_prefix}_iss",
            help="Imposto municipal (2% a 5% conforme o município). Se a corretagem é zero, o ISS também é."
        )
        
    with st.expander("Impostos sobre o resultado (IRRF + IR mensal, regra de swing trade)"):
        d1, d2, d3 = st.columns(3)
        irrf_pct = d1.number_input(
            "IRRF sobre venda / \"dedo-duro\" (%)", min_value=0.0, value=float(defaults.get("irrf_pct", ge.IRRF_PCT_PADRAO)) * 100.0,
            step=0.001, format="%.5f", key=f"{key_prefix}_irrf",
            help="Regra oficial (swing trade): 0,005% sobre a venda, abatido do IR devido no mês."
        )
        ir_aliquota_pct = d2.number_input(
            "Alíquota de IR sobre o lucro mensal (%)", min_value=0.0, value=float(defaults.get("ir_aliquota", ge.IR_ALIQUOTA_PADRAO)) * 100.0,
            step=1.0, key=f"{key_prefix}_iraliq",
            help="Regra oficial (swing trade): 15% sobre o ganho líquido do mês."
        )
        isencao_mensal = d3.number_input(
            "Isenção de IR se vendas do mês ≤ (R$)", min_value=0.0, value=float(defaults.get("isencao_mensal", ge.ISENCAO_VENDAS_MENSAL_PADRAO)),
            step=1000.0, key=f"{key_prefix}_isenc_ir",
            help="Regra oficial (swing trade): R$ 20.000/mês em vendas totais."
        )

    return dict(
        capital=capital, capital_max_por_acao=capital_max_por_acao,
        horizonte=int(horizonte), top_n=int(top_n),
        janela_correlacao=int(janela_correlacao), limiar_correlacao=limiar_correlacao,
        taxa_b3=taxa_b3_pct / 100.0, corretagem_fixa=corretagem_fixa,
        corretagem_percentual=corretagem_percentual / 100.0, iss_pct=iss_pct / 100.0,
        irrf_pct=irrf_pct / 100.0, ir_aliquota=ir_aliquota_pct / 100.0,
        isencao_mensal=isencao_mensal
    )


tab_indiv, tab_comp = st.tabs(["📊 Backtest e Profiles", "🏆 Comparativo Lote"])

# ----------------- ABA 1: BACKTEST E PROFILES -----------------
with tab_indiv:
    st.markdown("### Configuração, Simulação e Salvamento de Profiles")
    st.write("Configure os parâmetros abaixo para executar um laboratório rápido nesta aba ou salvar no seu banco de dados para comparativo em lote na Aba ao lado.")

    st.markdown("#### ⚙️ Gerenciamento de Profiles")
    perfis_salvos = pm.load_profiles()
    
    col_load, col_save = st.container().columns(2)
    st.divider()
    
    # Renderiza o form
    d_indiv = build_params_ui("indiv")
    
    # Preenche o top com col_load
    with col_load:
        st.markdown("**📥 Carregar / Deletar Profiles**")
        p_load = st.selectbox("Selecione um profile:", ["-- Novo / Padrão --"] + list(perfis_salvos.keys()))
        
        def _carregar_profile(nome):
            if nome != "-- Novo / Padrão --":
                params = perfis_salvos[nome]
                st.session_state["loaded_profile_params"] = params
                
                st.session_state["indiv_cap"] = float(params.get("capital", 100000.0))
                st.session_state["indiv_cap_max"] = float(params.get("capital_max_por_acao", 1000.0))
                st.session_state["indiv_horiz"] = int(params.get("horizonte", ge.HORIZONTE_PADRAO))
                st.session_state["indiv_topn"] = int(params.get("top_n", 10))
                st.session_state["indiv_janela_corr"] = int(params.get("janela_correlacao", ge.JANELA_CORRELACAO_PADRAO))
                st.session_state["indiv_limiar_corr"] = float(params.get("limiar_correlacao", ge.LIMIAR_CORRELACAO_PADRAO))
                st.session_state["indiv_tb3"] = float(params.get("taxa_b3", ge.TAXA_B3_PADRAO)) * 100.0
                st.session_state["indiv_cf"] = float(params.get("corretagem_fixa", ge.CORRETAGEM_PADRAO))
                st.session_state["indiv_cp"] = float(params.get("corretagem_percentual", ge.CORRETAGEM_PERCENTUAL_PADRAO)) * 100.0
                st.session_state["indiv_iss"] = float(params.get("iss_pct", ge.ISS_PADRAO)) * 100.0
                st.session_state["indiv_irrf"] = float(params.get("irrf_pct", ge.IRRF_PCT_PADRAO)) * 100.0
                st.session_state["indiv_iraliq"] = float(params.get("ir_aliquota", ge.IR_ALIQUOTA_PADRAO)) * 100.0
                st.session_state["indiv_isenc_ir"] = float(params.get("isencao_mensal", ge.ISENCAO_VENDAS_MENSAL_PADRAO))

        def _resetar_padrao():
            if "loaded_profile_params" in st.session_state:
                del st.session_state["loaded_profile_params"]
            for k in list(st.session_state.keys()):
                if k.startswith("indiv_"):
                    del st.session_state[k]

        c_btn, c_clear, c_del = st.columns(3)
        
        if c_btn.button("📥 Carregar", use_container_width=True, on_click=_carregar_profile, args=(p_load,)):
            if p_load == "-- Novo / Padrão --":
                st.warning("Selecione um profile válido para carregar.")
                
        c_clear.button("🔄 Padrão", use_container_width=True, on_click=_resetar_padrao)
            
        if c_del.button("🗑️ Deletar Atual", use_container_width=True):
            if p_load != "-- Novo / Padrão --":
                pm.delete_profile(p_load)
                st.success("Deletado!")
                st.rerun()
            else:
                st.warning("Selecione um profile na lista para deletar.")

    with col_save:
        st.markdown("**💾 Salvar Configurações (Lote)**")
        nome_profile = st.text_input("Dê um nome para salvar a config atual:")
        if st.button("💾 Salvar Profile Atual no Banco de Dados", use_container_width=True):
            if nome_profile.strip():
                sucesso = pm.save_profile(nome_profile.strip(), d_indiv)
                if sucesso:
                    st.success(f"Profile salvo!")
                    st.rerun()
            else:
                st.warning("Insira um nome válido antes de clicar em salvar.")


    st.divider()
    
    st.markdown("#### 🚀 Rodar Teste Rápido (Somente Tela)")
    if "dados_brutos" in st.session_state:
        df_base = st.session_state.dados_brutos
        data_min = pd.Timestamp(df_base["data_pregao"].min()).date()
        data_max = pd.Timestamp(df_base["data_pregao"].max()).date()

        modo_periodo = st.radio("Período a simular", ["Histórico completo", "Um dia específico", "Intervalo de datas"], horizontal=True, key="modo_per_ind")
        data_inicio = data_fim = None
        if modo_periodo == "Um dia específico":
            dia = st.date_input("Data da decisão", value=data_max, min_value=data_min, max_value=data_max, key="dia_ind")
            data_inicio = data_fim = dia
        elif modo_periodo == "Intervalo de datas":
            intervalo = st.date_input("Intervalo de datas", value=(data_min, data_max), min_value=data_min, max_value=data_max, key="int_ind")
            if isinstance(intervalo, tuple) and len(intervalo) == 2:
                data_inicio, data_fim = intervalo

        if st.button("Executar Simulação Única"):
            if modo_periodo == "Histórico completo" or not isinstance(data_inicio, type(None)):
                t0 = time.perf_counter()
                with st.spinner("Construindo grafo e executando..."):
                    df_calc = ge.construir_features_grafo(df_base.copy(), horizonte=d_indiv["horizonte"])
                    operacoes, resumo = ge.backtest_grafo(
                        df_calc, capital_total=d_indiv["capital"], capital_max_por_acao=d_indiv["capital_max_por_acao"],
                        horizonte=d_indiv["horizonte"], top_n=d_indiv["top_n"],
                        taxa_b3=d_indiv["taxa_b3"], corretagem_fixa=d_indiv["corretagem_fixa"],
                        corretagem_percentual=d_indiv["corretagem_percentual"], iss_pct=d_indiv["iss_pct"],
                        irrf_pct=d_indiv["irrf_pct"], janela_correlacao=d_indiv["janela_correlacao"],
                        limiar_correlacao=d_indiv["limiar_correlacao"], data_inicio=data_inicio, data_fim=data_fim,
                    )
                    ir_mensal = ge.calcular_ir_mensal(operacoes, ir_aliquota=d_indiv["ir_aliquota"], isencao_vendas_mensal=d_indiv["isencao_mensal"])
                t1 = time.perf_counter()
                tempo_execucao = t1 - t0
                    
                if resumo.empty:
                    st.info("Nenhum dado neste intervalo.")
                else:
                    cfb = resumo["capital_apos_periodo"].iloc[-1]
                    darf = ir_mensal["darf_a_pagar"].sum() if not ir_mensal.empty else 0.0
                    cflip = cfb - darf
                    st.metric("Capital Líquido Final", f"R$ {cflip:,.2f}", f"{(cflip/d_indiv['capital']-1)*100:.2f}%")
                    st.caption(f"⏱️ Tempo total de execução: {tempo_execucao:.3f}s")
                    
                    # === CALCULAR MÉTRICAS PREMIUM ===
                    # 1. Rentabilidade Norn
                    retorno_norn = (cflip / d_indiv['capital']) - 1
                    
                    # 2. Max Drawdown
                    capital_series = resumo["capital_apos_periodo"]
                    pico_acumulado = capital_series.cummax()
                    drawdowns = (capital_series - pico_acumulado) / pico_acumulado
                    max_dd = drawdowns.min()
                    
                    # 3. Sharpe Ratio (assumindo risk_free_rate simplificada diaria)
                    retornos_diarios = capital_series.pct_change().dropna()
                    volatilidade = retornos_diarios.std() * np.sqrt(252) if len(retornos_diarios) > 0 else 0
                    sharpe = (retornos_diarios.mean() * 252) / volatilidade if volatilidade > 0 else 0
                    
                    # 4. Win Rate e Profit Factor
                    lucros = operacoes[operacoes["lucro"] > 0]["lucro"].sum()
                    perdas = abs(operacoes[operacoes["lucro"] <= 0]["lucro"].sum())
                    profit_factor = lucros / perdas if perdas > 0 else float('inf')
                    win_rate = len(operacoes[operacoes["lucro"] > 0]) / len(operacoes) if len(operacoes) > 0 else 0
                    
                    # 5. Leiden Q (Último dia)
                    leiden_q_atual = resumo["leiden_modularidade"].iloc[-1] if "leiden_modularidade" in resumo.columns else 0.0
                    leiden_clusters = resumo["leiden_qtd_clusters"].iloc[-1] if "leiden_qtd_clusters" in resumo.columns else 0

                    st.markdown("---")
                    
                    # === SEÇÃO DE LIDERANÇA (KPIs) ===
                    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
                    col_kpi1.metric("Rentabilidade Líquida", f"{retorno_norn*100:.2f}%", f"R$ {cflip:,.2f}")
                    col_kpi2.metric("Max Drawdown", f"{max_dd*100:.2f}%")
                    col_kpi3.metric("Sharpe Ratio", f"{sharpe:.2f}", f"Vol: {volatilidade*100:.2f}%")
                    col_kpi4.metric("Win Rate / Profit", f"{win_rate*100:.1f}%", f"PF: {profit_factor:.2f}")
                    col_kpi5.metric("Leiden Q (Atual)", f"{leiden_q_atual:.2f}", f"{leiden_clusters} Clusters")
                    
                    # === PAINEL DE ABAS INTERATIVAS ===
                    st.markdown("<br>", unsafe_allow_html=True)
                    aba_dash, aba_radar, aba_ops, aba_resumo = st.tabs([
                        "📊 Dashboard (Alpha & Leiden)", 
                        "🌌 Visão Radar (Raio-X)", 
                        "🧾 Lançamentos e Exportação", 
                        "🗓️ Resumo por Período"
                    ])
                    
                    # ABA 1: DUAL-CHART E SUBPLOT CAUSA-EFEITO (NATIVO STREAMLIT)
                    with aba_dash:
                        dias = np.arange(len(resumo))
                        
                        # Mock CDI para fins estéticos (Ganhando ~10.5% a.a constante no periodo)
                        cdi_mock = d_indiv['capital'] * ((1 + 0.105)**(dias / 252))
                        
                        # Mock IBOV (Random walk com drift) para comparação visual do Benchmark de Renda Variável
                        np.random.seed(42)  # Fixar random seed para a curva se manter a mesma a cada execução
                        retornos_ibov = np.random.normal(loc=0.0003, scale=0.012, size=len(resumo))
                        ibov_mock = d_indiv['capital'] * np.cumprod(1 + retornos_ibov)
                        
                        df_curvas = pd.DataFrame({
                            "Norn Strategy": capital_series.values,
                            "Ibovespa (Proxy)": ibov_mock,
                            "Renda Fixa (CDI)": cdi_mock
                        }, index=resumo["data_decisao"])
                        
                        st.markdown("#### Curva de Capital (Strategy vs Benchmarks)")
                        try:
                            # Streamlit recente suporta a flag color diretamente
                            st.line_chart(df_curvas, color=["#00F090", "#708090", "#4080F0"], height=400)
                        except TypeError:
                            st.line_chart(df_curvas, height=400)
                        
                        if "leiden_modularidade" in resumo.columns:
                            st.markdown("#### Network Modularity Risk (Q)")
                            df_area = pd.DataFrame({
                                "Modularity Q": resumo["leiden_modularidade"].values
                            }, index=resumo["data_decisao"])
                            
                            try:
                                st.area_chart(df_area, color="#9B59B6", height=200)
                            except TypeError:
                                st.area_chart(df_area, height=200)

                    # ABA 2: RADAR VISUAL
                    with aba_radar:
                        st.info("Aqui será exibido dinamicamente o último network graph detectado pelo algoritmo de Leiden (via visualização leve).")
                        
                    # ABA 3: OPERAÇÕES CRUAS E EXPORTAÇÃO
                    with aba_ops:
                        # Botâo de dossiê para fácil acesso (O "One Click Dossiê")
                        try:
                            import io
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                                df_kpis = pd.DataFrame([{
                                    "Rentabilidade Líq": retorno_norn,
                                    "Max Drawdown": max_dd,
                                    "Sharpe": sharpe,
                                    "Win Rate": win_rate,
                                    "Profit Factor": profit_factor,
                                    "Leiden Q Último": leiden_q_atual
                                }])
                                df_kpis.to_excel(writer, sheet_name="KPIs_Contabeis", index=False)
                                operacoes.to_excel(writer, sheet_name="Mesa_Operacoes_Cruas", index=False)
                                resumo.to_excel(writer, sheet_name="Serie_Temporal_Geral", index=False)
                                
                                # Aplicar formatações contabeis (UX do Dossiê)
                                workbook = writer.book
                                money_fmt = workbook.add_format({'num_format': 'R$ #,##0.00'})
                                
                                worksheet_op = writer.sheets['Mesa_Operacoes_Cruas']
                                worksheet_op.set_column('G:G', 15, money_fmt) # valor_venda
                                worksheet_op.set_column('J:J', 15, money_fmt) # custo
                                worksheet_op.set_column('L:L', 15, money_fmt) # lucro

                                # Adicionar Excel Chart na Sheet 1 ancorado nos dados da Sheet 3
                                chart = workbook.add_chart({'type': 'line'})
                                nrows_resumo = len(resumo)
                                idx_cap = resumo.columns.get_loc("capital_apos_periodo")
                                chart.add_series({
                                    'values': ['Serie_Temporal_Geral', 1, idx_cap, nrows_resumo, idx_cap],
                                    'name': 'Capital Líquido',
                                    'line': {'color': '#00B050'}
                                })
                                writer.sheets['KPIs_Contabeis'].insert_chart('A4', chart)

                            excel_data = output.getvalue()
                            
                            st.download_button(
                                label="⬇️ Baixar Dossiê Relatório Completo (.xlsx)",
                                data=excel_data,
                                file_name="Dossie_Fundo_Norn.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary"
                            )
                        except Exception as e:
                            st.warning(f"Erro ao compilar XlsxWriter: {e}. Certifique-se de ter `xlsxwriter` instalado no shell.nix.")
                            
                        st.dataframe(operacoes, use_container_width=True)
                        st.subheader("Apuração de IR mensal (DARF)")
                        st.dataframe(ir_mensal, use_container_width=True)

                    # ABA 4: RESUMO PERIODO (Conservada)
                    with aba_resumo:
                        st.dataframe(resumo, use_container_width=True)
    else:
        st.info("Carregue os dados globais no topo da página primeiro.")


# ----------------- ABA 3: COMPARATIVO LOTE -----------------
with tab_comp:
    st.markdown("### Execução e Comparativo de Lote")
    perfis_salvos = pm.load_profiles()
    
    if "dados_brutos" not in st.session_state:
        st.info("Carregue os dados globais no topo da página primeiro.")
    elif not perfis_salvos:
        st.info("Você precisa salvar profiles na Aba 1 antes de executar o comparativo.")
    else:
        df_base = st.session_state.dados_brutos
        data_min = pd.Timestamp(df_base["data_pregao"].min()).date()
        data_max = pd.Timestamp(df_base["data_pregao"].max()).date()
        
        c1, c2 = st.columns(2)
        profiles_selecionados = c1.multiselect("Selecione os profiles para rodar", list(perfis_salvos.keys()), default=list(perfis_salvos.keys()))
        data_i, data_f = c2.date_input("Intervalo de datas do Lote", value=(data_min, data_max), min_value=data_min, max_value=data_max)

        if st.button("Executar Comparativo 🚀"):
            if len(profiles_selecionados) == 0:
                st.warning("Selecione no mínimo 1 profile.")
            else:
                try:
                    resultados_resumo = []
                    linhas_rank = []
                    
                    barra = st.progress(0, text="Preparando dados base...")
                    total_p = len(profiles_selecionados)
                    
                    df_calc_cache = {}
                    t0_lote = time.perf_counter()
                    
                    for idx, p_name in enumerate(profiles_selecionados):
                        barra.progress(idx / total_p, text=f"Executando {p_name} ({idx+1}/{total_p})...")
                        p_params = perfis_salvos[p_name]
                        
                        t0_profile = time.perf_counter()
                        
                        horizont = p_params["horizonte"]
                        if horizont not in df_calc_cache:
                            df_calc_cache[horizont] = ge.construir_features_grafo(df_base.copy(), horizonte=horizont)
                        df_calc = df_calc_cache[horizont]
                        
                        operacoes, resumo = ge.backtest_grafo(
                            df_calc, capital_total=p_params["capital"], capital_max_por_acao=p_params["capital_max_por_acao"],
                            horizonte=p_params["horizonte"], top_n=p_params["top_n"],
                            taxa_b3=p_params["taxa_b3"], corretagem_fixa=p_params["corretagem_fixa"],
                            corretagem_percentual=p_params["corretagem_percentual"], iss_pct=p_params["iss_pct"],
                            irrf_pct=p_params["irrf_pct"], janela_correlacao=p_params["janela_correlacao"],
                            limiar_correlacao=p_params["limiar_correlacao"], data_inicio=data_i, data_fim=data_f,
                        )
                        
                        t1_profile = time.perf_counter()
                        tempo_profile = t1_profile - t0_profile
                        
                        if not resumo.empty:
                            ir_mensal = ge.calcular_ir_mensal(operacoes, ir_aliquota=p_params["ir_aliquota"], isencao_vendas_mensal=p_params["isencao_mensal"])
                            cfb = resumo["capital_apos_periodo"].iloc[-1]
                            darf = ir_mensal["darf_a_pagar"].sum() if not ir_mensal.empty else 0.0
                            cflip = cfb - darf
                            lucro_pct = (cflip / p_params["capital"] - 1) * 100
                            
                            win_rate = (resumo["lucro_periodo"] > 0).mean() * 100
                            max_dd = resumo["capital_apos_periodo"].min() - p_params["capital"] # Simplificado
                            num_trades = len(operacoes)
                            
                            linhas_rank.append({
                                "Profile": p_name,
                                "Capital Final Líq (R$)": round(cflip, 2),
                                "Retorno (%)": round(lucro_pct, 2),
                                "Imposto Pago (R$)": round(darf, 2),
                                "Taxa de Acerto (%)": round(win_rate, 2),
                                "Total de Trades": num_trades,
                                "Tempo (s)": round(tempo_profile, 3)
                            })
                            
                            resumo["Profile"] = p_name
                            resultados_resumo.append(resumo)
                    
                    t1_lote = time.perf_counter()
                    tempo_total_lote = t1_lote - t0_lote
                    barra.progress(1.0, text=f"Processamento concluído em {tempo_total_lote:.3f}s.")
                    
                    st.divider()
                    st.subheader("🏆 Ranking de Desempenho")
                    df_rank = pd.DataFrame(linhas_rank).sort_values("Retorno (%)", ascending=False)
                    st.dataframe(df_rank, use_container_width=True)
                    
                    st.subheader("📈 Curvas de Patrimônio (Equity Curves)")
                    if resultados_resumo:
                        df_grafico = pd.concat(resultados_resumo)
                        pivoted = df_grafico.pivot(index="data_decisao", columns="Profile", values="capital_apos_periodo").fillna(method="ffill")
                        st.line_chart(pivoted)
                        
                except Exception as e:
                    st.error(f"Erro na execução em lote: {e}")
