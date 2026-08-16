"""Roda as 5 estratégias de grafo de correlação com o tratamento de eventos
societários aplicado, e imprime uma tabela comparativa (equivalente ao modo
"Comparar as 5 estratégias" do app_grafo.py, mas via linha de comando).

Uso:
    python rodar_backtest_realista.py caminho/para/cotahist.parquet \
        --data-inicio 2019-01-01 --data-fim 2025-12-31 \
        --capital 100000 --capital-max-por-acao 10000

Reaproveita 100% do motor de backtest, custos, alocação e métricas já
existentes no projeto (grafo_estrategia.py, universo.py, metricas_risco.py) —
a única coisa nova é a chamada a `construir_features_grafo_realista` no lugar
de `construir_features_grafo`.
"""
from __future__ import annotations

import argparse

import pandas as pd

import grafo_estrategia as ge
import metricas_risco as mr
import universo as uv
from tratamento_eventos_societarios import construir_features_grafo_realista

ESTRATEGIAS = {
    "1. Vizinhança direta (limiar de correlação)": ge.backtest_spillover_threshold,
    "2. Árvore Geradora Mínima (Mantegna)": ge.backtest_spillover_mst,
    "3. Centralidade + momentum": ge.backtest_centralidade,
    "4. Comunidades (Louvain)": ge.backtest_comunidade,
    "5. GNN simplificada (1 camada + Ridge)": ge.backtest_gnn_simplificado,
}


def _rodar_estrategia(fn, **kwargs):
    import inspect
    aceitos = set(inspect.signature(fn).parameters)
    return fn(**{k: v for k, v in kwargs.items() if k in aceitos})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dados", help="parquet/csv do COTAHIST processado (saída de b3_cotahist.py)")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--capital-max-por-acao", type=float, default=10_000.0)
    ap.add_argument("--horizonte", type=int, default=ge.HORIZONTE_PADRAO)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--janela-correlacao", type=int, default=ge.JANELA_CORRELACAO_PADRAO)
    ap.add_argument("--limiar-correlacao", type=float, default=ge.LIMIAR_CORRELACAO_PADRAO)
    ap.add_argument("--data-inicio", default=None)
    ap.add_argument("--data-fim", default=None)
    ap.add_argument("--limiar-evento", type=float, default=0.60,
                     help="Limiar de retorno diário acima do qual uma decisão é "
                          "tratada como contaminada por evento societário.")
    ap.add_argument("--taxa-b3", type=float, default=0.0)
    ap.add_argument("--corretagem-fixa", type=float, default=0.0)
    ap.add_argument("--corretagem-percentual", type=float, default=0.0)
    ap.add_argument("--iss-pct", type=float, default=0.0)
    ap.add_argument("--irrf-pct", type=float, default=0.0)
    ap.add_argument("--ir-aliquota", type=float, default=0.0)
    ap.add_argument("--isencao-mensal", type=float, default=0.0)
    args = ap.parse_args()

    # --- Carregamento + filtro de universo (igual ao app_grafo.py, filtro ligado) ---
    df = ge.carregar_dados(args.dados)
    df = uv.ajustar_por_fator_cotacao(df)
    df, relatorio_filtro = uv.filtrar_universo(df)
    df = uv.marcar_descontinuidades(df, max_dias_gap=10)
    print("\n=== Relatório do filtro de universo ===")
    print(relatorio_filtro.to_string(index=False))

    # --- Features + tratamento de eventos societários (a novidade) ---
    df = construir_features_grafo_realista(df, horizonte=args.horizonte, limiar_evento=args.limiar_evento)

    kwargs_comuns = dict(
        df_features=df, capital_total=args.capital, capital_max_por_acao=args.capital_max_por_acao,
        horizonte=args.horizonte, top_n=args.top_n,
        taxa_b3=args.taxa_b3, corretagem_fixa=args.corretagem_fixa,
        corretagem_percentual=args.corretagem_percentual, iss_pct=args.iss_pct,
        irrf_pct=args.irrf_pct, janela_correlacao=args.janela_correlacao,
        limiar_correlacao=args.limiar_correlacao,
        data_inicio=args.data_inicio, data_fim=args.data_fim,
    )

    linhas = []
    for nome, fn in ESTRATEGIAS.items():
        print(f"\nRodando: {nome} ...")
        operacoes, resumo = _rodar_estrategia(fn, **kwargs_comuns)
        if resumo.empty:
            linhas.append({"Estratégia": nome, "Nº operações": 0,
                            "Capital final líquido": args.capital, "Retorno (%)": 0.0})
            continue

        ir_mensal = ge.calcular_ir_mensal(
            operacoes, ir_aliquota=args.ir_aliquota, isencao_vendas_mensal=args.isencao_mensal
        )
        capital_final = resumo["capital_apos_periodo"].iloc[-1]
        darf = ir_mensal["darf_a_pagar"].sum() if not ir_mensal.empty else 0.0
        capital_liquido = capital_final - darf

        metricas = mr.calcular_metricas_risco(resumo, args.capital, operacoes=operacoes)

        linhas.append({
            "Estratégia": nome,
            "Nº operações": len(operacoes),
            "Capital final líquido": round(capital_liquido, 2),
            "Retorno (%)": round((capital_liquido / args.capital - 1) * 100, 2),
            "Sharpe": metricas.get("sharpe"),
            "Sortino": metricas.get("sortino"),
            "Calmar": metricas.get("calmar"),
            "Máx. drawdown (%)": metricas.get("max_drawdown_pct"),
            "Win rate (%)": metricas.get("win_rate_pct"),
            "Profit factor": metricas.get("profit_factor"),
        })

    comparativo = pd.DataFrame(linhas).sort_values("Retorno (%)", ascending=False)
    print("\n=== Comparativo (com tratamento de eventos societários aplicado) ===")
    print(comparativo.to_string(index=False))
    comparativo.to_csv("comparativo_realista.csv", index=False)
    print("\nSalvo em comparativo_realista.csv")
    print(
        "\nValide o efeito da mitigação rodando diagnostico_artefatos.py --operacoes "
        "nas operações exportadas antes e depois desta mudança."
    )


if __name__ == "__main__":
    main()
