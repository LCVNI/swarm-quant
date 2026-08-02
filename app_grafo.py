"""Aplicação independente: estratégia de trading baseada em GRAFO DE CORRELAÇÃO
entre ações (market graph), sem machine learning.

Depende só de grafo_estrategia.py + streamlit/pandas. Não importa core.py.
"""
import pandas as pd
import streamlit as st
from pathlib import Path
import grafo_estrategia as ge

try:
    import benchmarks_externos as bx
    BENCHMARKS_AUTOMATICOS_DISPONIVEL = True
except ImportError:
    BENCHMARKS_AUTOMATICOS_DISPONIVEL = False


@st.cache_data(show_spinner=False, ttl=3600)
def _buscar_benchmarks_automaticamente(data_inicio: str, data_fim: str, brapi_token: str = "") -> pd.DataFrame:
    """Busca Selic, CDI (BCB) e Ibovespa (brapi.dev com token, ou yfinance
    sem token) para o intervalo dado. Cacheado por 1h e por
    (data_inicio, data_fim, token) — não bate na API de novo a cada clique
    em 'Rodar backtest', só quando o intervalo de dados muda.
    """
    return bx.montar_benchmarks(data_inicio, data_fim, brapi_token=brapi_token or None)

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

arquivos = st.file_uploader(
    "Arquivo(s) processado(s) (parquet ou csv, saída do b3_cotahist.py). "
    "Pode selecionar vários arquivos (ex.: um por ano) — serão combinados automaticamente.",
    type=["parquet", "csv"], accept_multiple_files=True,
)

opcoes_benchmarks = ["Não usar", "Subir arquivo (benchmarks_externos.py)"]
if BENCHMARKS_AUTOMATICOS_DISPONIVEL:
    opcoes_benchmarks.insert(1, "Buscar automaticamente (Selic/CDI/Ibovespa)")

modo_benchmarks = st.radio(
    "Benchmarks externos (Selic, CDI, Ibovespa) — além do equal-weight, sempre calculado",
    opcoes_benchmarks, horizontal=True,
)
if not BENCHMARKS_AUTOMATICOS_DISPONIVEL:
    st.caption(
        "Busca automática indisponível (arquivo `benchmarks_externos.py` não encontrado "
        "na mesma pasta do app). Você ainda pode gerar o arquivo separadamente e subir manualmente."
    )
elif modo_benchmarks == "Buscar automaticamente (Selic/CDI/Ibovespa)":
    st.caption(
        "Busca Selic e CDI na API do Banco Central. Para o Ibovespa, use um "
        "token gratuito da brapi.dev (cadastro em brapi.dev/dashboard) — mais "
        "estável, com SLA e suporte em PT-BR. Sem token, cai para o Yahoo "
        "Finance (^BVSP), que não tem garantia de estabilidade para uso "
        "programático. Requer internet no momento de clicar em 'Carregar dados'; "
        "se a busca falhar, use a opção de upload manual."
    )
    brapi_token = st.text_input(
        "Token da brapi.dev (opcional, para o Ibovespa)", type="password",
        help="Gratuito — crie em https://brapi.dev/dashboard. Deixe em branco para usar Yahoo Finance.",
    )
else:
    brapi_token = ""

arquivo_benchmarks = None
if modo_benchmarks == "Subir arquivo (benchmarks_externos.py)":
    arquivo_benchmarks = st.file_uploader(
        "Arquivo de benchmarks (parquet/csv, saída do benchmarks_externos.py)",
        type=["parquet", "csv"],
    )

col1, col2, col3, col4 = st.columns(4)
capital = col1.number_input("Capital total (R$)", min_value=0.0, value=100000.0, step=1000.0)
capital_max_por_acao = col2.number_input("Máximo por ação (R$)", min_value=0.0, value=1000.0, step=100.0)
horizonte = col3.number_input("Horizonte (pregões à frente)", min_value=1, value=ge.HORIZONTE_PADRAO)
top_n = col4.number_input("Nº máximo de ativos por período", min_value=1, value=10)

col5, col6, col7 = st.columns(3)
janela_correlacao = col5.number_input(
    "Janela de correlação (pregões)", min_value=20, value=ge.JANELA_CORRELACAO_PADRAO, step=10,
    help="Quantos pregões passados usar para calcular a correlação entre as ações.",
)
limiar_correlacao = col6.number_input(
    "Correlação mínima para virar 'vizinho' no grafo", min_value=0.0, max_value=1.0,
    value=ge.LIMIAR_CORRELACAO_PADRAO, step=0.05,
    help="Só cria uma aresta entre duas ações se a correlação (em módulo) for maior que isso.",
)
taxa_livre_risco = col7.number_input(
    "Taxa livre de risco anual (%)", min_value=0.0, value=0.0, step=0.5,
    help="Usada para calcular o Índice Sharpe.",
)

st.caption(
    "Custos e impostos abaixo começam **zerados**. Preencha com os valores da sua corretora "
    "e da sua situação fiscal; o app não assume nenhum valor por conta própria."
)

with st.expander("Filtro de liquidez"):
    l1, l2 = st.columns(2)
    min_negocios_medio = l1.number_input(
        "Média mínima de negócios por pregão", min_value=0, value=100, step=10,
        help="Tickers cuja média móvel de número de negócios ficar abaixo disso são excluídos do grafo e do backtest.",
    )
    janela_liquidez = l2.number_input(
        "Janela da média de liquidez (pregões)", min_value=1, value=20, step=5,
        help="Quantos pregões passados usar para calcular a média móvel de número de negócios.",
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

if arquivos and st.button("Carregar dados"):
    with st.spinner("Carregando dados e calculando retornos..."):
        frames = []
        for arquivo in arquivos:
            caminho = Path(arquivo.name)
            with caminho.open("wb") as f:
                f.write(arquivo.getbuffer())
            frames.append(ge.carregar_dados(str(caminho)))

        df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        # Se os arquivos tiverem datas sobrepostas (ex.: dois exports do mesmo
        # período), mantém só uma linha por (ticker, data, mercado).
        df = df.drop_duplicates(subset=["ticker", "data_pregao", "tipo_mercado"], keep="last")
        df = df.sort_values(["ticker", "data_pregao"])

        n_tickers_antes = df["ticker"].nunique()
        df = ge.filtrar_liquidez(
            df, min_negocios_medio=int(min_negocios_medio), janela_liquidez=int(janela_liquidez)
        )
        n_tickers_depois = df["ticker"].nunique()
        df = ge.construir_features_grafo(df, horizonte=int(horizonte))

        df_benchmarks = None
        erro_benchmarks = None
        if modo_benchmarks == "Buscar automaticamente (Selic/CDI/Ibovespa)":
            try:
                data_ini_str = df["data_pregao"].min().strftime("%Y-%m-%d")
                data_fim_str = df["data_pregao"].max().strftime("%Y-%m-%d")
                df_benchmarks = _buscar_benchmarks_automaticamente(data_ini_str, data_fim_str, brapi_token)
            except Exception as exc:
                erro_benchmarks = str(exc)
        elif modo_benchmarks == "Subir arquivo (benchmarks_externos.py)" and arquivo_benchmarks is not None:
            caminho_bench = Path(arquivo_benchmarks.name)
            with caminho_bench.open("wb") as f:
                f.write(arquivo_benchmarks.getbuffer())
            df_benchmarks = (
                pd.read_parquet(caminho_bench) if caminho_bench.suffix == ".parquet"
                else pd.read_csv(caminho_bench, parse_dates=["data"])
            )

    st.session_state.dados_grafo = dict(
        df=df, capital=capital, capital_max_por_acao=capital_max_por_acao,
        horizonte=int(horizonte), top_n=int(top_n),
        janela_correlacao=int(janela_correlacao), limiar_correlacao=limiar_correlacao,
        taxa_b3=taxa_b3_pct / 100, corretagem_fixa=corretagem_fixa,
        corretagem_percentual=corretagem_percentual / 100, iss_pct=iss_pct / 100,
        irrf_pct=irrf_pct / 100, ir_aliquota=ir_aliquota_pct / 100,
        isencao_mensal=isencao_mensal, taxa_livre_risco=taxa_livre_risco / 100,
        df_benchmarks=df_benchmarks,
    )
    if erro_benchmarks:
        st.warning(
            f"Não foi possível buscar nenhum benchmark externo automaticamente ({erro_benchmarks}). "
            "O backtest segue normalmente com o benchmark equal-weight; gere o arquivo com "
            "`benchmarks_externos.py` e suba manualmente se quiser tentar de novo."
        )
    msg_bench = ""
    if df_benchmarks is not None:
        obtidos = []
        if "selic_diaria" in df_benchmarks.columns and df_benchmarks["selic_diaria"].notna().any():
            obtidos.append("Selic")
        if "cdi_diario" in df_benchmarks.columns and df_benchmarks["cdi_diario"].notna().any():
            obtidos.append("CDI")
        if "ibovespa_fechamento" in df_benchmarks.columns and df_benchmarks["ibovespa_fechamento"].notna().any():
            obtidos.append("Ibovespa")
        if obtidos:
            msg_bench = f" + benchmarks externos ({', '.join(obtidos)})"
        faltando = {"Selic", "CDI", "Ibovespa"} - set(obtidos)
        if faltando:
            st.warning(f"Não foi possível obter: {', '.join(sorted(faltando))}. Os demais benchmarks disponíveis seguem normalmente.")
    st.success(
        f"Dados carregados de {len(arquivos)} arquivo(s){msg_bench}: {len(df):,} linhas, "
        f"{n_tickers_depois} de {n_tickers_antes} tickers mantidos após filtro de liquidez."
    )

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

    if st.button("Rodar backtest"):
        with st.spinner("Construindo grafos de correlação e simulando..."):
            operacoes, resumo = ge.backtest_grafo(
                df, capital_total=d["capital"], capital_max_por_acao=d["capital_max_por_acao"],
                horizonte=d["horizonte"], top_n=d["top_n"],
                taxa_b3=d["taxa_b3"], corretagem_fixa=d["corretagem_fixa"],
                corretagem_percentual=d["corretagem_percentual"], iss_pct=d["iss_pct"],
                irrf_pct=d["irrf_pct"], janela_correlacao=d["janela_correlacao"],
                limiar_correlacao=d["limiar_correlacao"], data_inicio=data_inicio, data_fim=data_fim,
            )
            ir_mensal = ge.calcular_ir_mensal(
                operacoes, ir_aliquota=d["ir_aliquota"], isencao_vendas_mensal=d["isencao_mensal"]
            )
            if d.get("df_benchmarks") is not None and not resumo.empty:
                resumo = ge.calcular_benchmarks_externos(d["df_benchmarks"], resumo)
            st.session_state.resultado_backtest_grafo = (operacoes, resumo, ir_mensal, d["capital"])

    if "resultado_backtest_grafo" in st.session_state:
        operacoes, resumo, ir_mensal, capital_inicial = st.session_state.resultado_backtest_grafo
        if resumo.empty:
            st.info("Nenhum período simulável com esses parâmetros (janela de correlação ou período curtos demais).")
        else:
            capital_final_bruto = resumo["capital_apos_periodo"].iloc[-1]
            total_darf = ir_mensal["darf_a_pagar"].sum() if not ir_mensal.empty else 0.0
            capital_final_liquido = capital_final_bruto - total_darf

            metricas_risco = ge.calcular_metricas_risco(
                resumo, 
                capital_inicial=capital_inicial, 
                dias_por_periodo=d["horizonte"], 
                taxa_livre_risco_anual=d["taxa_livre_risco"]
            )

            m1, m2, m3 = st.columns(3)
            m1.metric("Capital final (antes de IR)", f"R$ {capital_final_bruto:,.2f}",
                      f"{(capital_final_bruto/capital_inicial-1)*100:.2f}%")
            m2.metric("DARF total pago no período", f"R$ {total_darf:,.2f}")
            m3.metric("Capital final (líquido de IR)", f"R$ {capital_final_liquido:,.2f}",
                      f"{(capital_final_liquido/capital_inicial-1)*100:.2f}%")

            m4, m5, m6, m7 = st.columns(4)
            m4.metric("Retorno anualizado", f"{metricas_risco['retorno_anualizado']*100:.2f}%")
            m5.metric("Volatilidade anual", f"{metricas_risco['volatilidade_anualizada']*100:.2f}%")
            m6.metric("Sharpe", f"{metricas_risco['sharpe']:.2f}")
            m7.metric("Drawdown máximo", f"{metricas_risco['drawdown_maximo']*100:.2f}%")

            periodos_positivos = float((resumo["lucro_periodo"] > 0).mean())
            st.caption(f"Períodos com lucro operacional positivo: {periodos_positivos:.1%} de {len(resumo)} decisões.")

            if "pct_capital_alocado" in resumo.columns:
                pct_medio_alocado = float(resumo["pct_capital_alocado"].mean())
                st.caption(
                    f"Capital efetivamente alocado: em média {pct_medio_alocado:.1%} do capital "
                    "disponível por período. Se esse número estiver bem abaixo de 100%, a "
                    "estratégia está deixando capital ocioso — a comparação com o benchmark "
                    "equal-weight (que assume 100% investido) fica menos justa. Considere "
                    "aumentar 'Máximo por ação' e/ou 'Nº máximo de ativos por período' para "
                    "que top_n × máximo por ação se aproxime do capital total."
                )

            grafico_df = pd.DataFrame(index=resumo["data_decisao"])
            grafico_df["Estratégia"] = (resumo["capital_apos_periodo"].values / capital_inicial) * 100

            if "retorno_benchmark" in resumo.columns:
                retornos_bench = resumo["retorno_benchmark"].values
                acumulado_bench = 100 * (1 + retornos_bench).cumprod()
                grafico_df["Benchmark (Equal-Weight)"] = acumulado_bench

            nomes_benchmarks_externos = {
                "retorno_selic": "Selic",
                "retorno_cdi": "CDI",
                "retorno_ibovespa": "Ibovespa",
            }
            for coluna, nome in nomes_benchmarks_externos.items():
                if coluna in resumo.columns:
                    grafico_df[nome] = 100 * (1 + resumo[coluna].values).cumprod()

            st.line_chart(grafico_df)

            st.subheader("Resumo por período")
            st.dataframe(resumo, use_container_width=True)

            st.subheader("Apuração de IR mensal (DARF)")
            if ir_mensal.empty:
                st.info("Nenhuma venda com data suficiente para apurar IR mensal.")
            else:
                st.dataframe(ir_mensal, use_container_width=True)

            st.subheader("Todas as operações simuladas")
            st.dataframe(operacoes, use_container_width=True)

            st.divider()
            st.subheader("Extração de Dados")
            csv_resumo = resumo.to_csv(index=False).encode('utf-8')
            csv_operacoes = operacoes.to_csv(index=False).encode('utf-8')
            
            c_down1, c_down2 = st.columns(2)
            c_down1.download_button(
                label="Baixar Resumo do Backtest (CSV)",
                data=csv_resumo,
                file_name="backtest_resumo.csv",
                mime="text/csv",
            )
            c_down2.download_button(
                label="Baixar Operações (CSV)",
                data=csv_operacoes,
                file_name="backtest_operacoes.csv",
                mime="text/csv",
            )