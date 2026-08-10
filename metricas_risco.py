"""Métricas de risco e comparação com benchmarks (SELIC e Ibovespa).

Métricas cobertas (baseado no material "Indicadores de Performance": Alfa de
Jensen, Beta, Sharpe, Drawdown + Sortino, Calmar, Profit Factor, Win Rate):

- Beta (β): sensibilidade dos retornos da estratégia ao mercado (Ibovespa).
- Alfa de Jensen (α): via CAPM — E(Rp) = Rf + β×(Rm−Rf), α = Rp − E(Rp).
  Mede geração de valor ALÉM do exigido pelo risco assumido (beta), não é
  simplesmente "retorno da estratégia menos retorno do Ibovespa".
- Sharpe: retorno em excesso (sobre a SELIC) por unidade de volatilidade TOTAL.
- Sortino: como o Sharpe, mas só penaliza volatilidade de quedas (downside).
- Calmar: retorno anualizado dividido pelo pior drawdown.
- Max Drawdown: maior queda percentual entre um pico e o vale seguinte.
- Profit Factor: lucro bruto das operações vencedoras ÷ prejuízo bruto das
  perdedoras (calculado por OPERAÇÃO, não por período — precisa de `operacoes`).
- Win Rate: % de operações individuais com lucro positivo.

Módulo independente: só depende de pandas/numpy, usável por qualquer uma das
estratégias (grafo ou ML) a partir do formato comum de `resumo`/`operacoes`
(mesmas colunas nos dois: data_decisao, data_venda_prevista, lucro_periodo,
capital_apos_periodo em resumo; lucro por linha em operacoes).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Carregamento dos benchmarks
# ---------------------------------------------------------------------------
def carregar_selic(caminho_json: str) -> pd.Series:
    """Lê o formato BCB/SGS (série 11, Selic diária): lista de
    {"data": "DD/MM/AAAA", "valor": "0.024620"}, onde valor é a taxa em % ao dia.
    Retorna Series indexada por data, com a taxa em fração decimal (não %)."""
    with open(caminho_json, encoding="utf-8") as f:
        dados = json.load(f)
    df = pd.DataFrame(dados)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = df["valor"].astype(float) / 100  # % a.d. -> fração decimal
    return df.set_index("data")["valor"].sort_index()


def carregar_ibovespa(caminho_csv: str) -> pd.DataFrame:
    """Lê CSV no formato Yahoo Finance (colunas: data, abertura, maxima, minima,
    fechamento, fechamento_ajustado, volume, ...). Descarta linhas incompletas
    (pregão do dia ainda em andamento, sem preço de abertura)."""
    df = pd.read_csv(caminho_csv, parse_dates=["data"])
    df = df[df["abertura"] > 0].sort_values("data").reset_index(drop=True)
    df["retorno_diario"] = df["fechamento_ajustado"].pct_change()
    return df.set_index("data")


# ---------------------------------------------------------------------------
# Retorno acumulado de um benchmark entre duas datas (usado por período do backtest)
# ---------------------------------------------------------------------------
def _retorno_selic_periodo(selic: pd.Series, data_inicio: pd.Timestamp, data_fim: pd.Timestamp) -> float:
    janela = selic[(selic.index > data_inicio) & (selic.index <= data_fim)]
    if janela.empty:
        return np.nan
    return float(np.prod(1 + janela) - 1)


def _retorno_ibov_periodo(ibov: pd.DataFrame, data_inicio: pd.Timestamp, data_fim: pd.Timestamp) -> float:
    precos = ibov["fechamento_ajustado"]
    antes = precos[precos.index <= data_inicio]
    depois = precos[precos.index <= data_fim]
    if antes.empty or depois.empty:
        return np.nan
    return float(depois.iloc[-1] / antes.iloc[-1] - 1)


def _anualizar(retorno_total: float, dias_totais: float) -> float:
    if dias_totais <= 0 or pd.isna(retorno_total):
        return float("nan")
    base = 1 + retorno_total
    if base <= 0:
        return float("nan")  # perda total ou pior: taxa anualizada não é definida
    return float(base ** (365 / dias_totais) - 1)


# ---------------------------------------------------------------------------
# Métricas de risco + comparação com benchmarks
# ---------------------------------------------------------------------------
def calcular_metricas_risco(
    resumo: pd.DataFrame,
    capital_inicial: float,
    selic: pd.Series | None = None,
    ibovespa: pd.DataFrame | None = None,
    operacoes: pd.DataFrame | None = None,
) -> dict:
    """`resumo`: saída padrão dos backtests (data_decisao, data_venda_prevista,
    lucro_periodo, capital_apos_periodo). `operacoes` (opcional): saída padrão
    dos backtests com uma linha por operação e coluna `lucro` — necessário só
    para Profit Factor e Win Rate (métricas por operação, não por período).
    """
    if resumo.empty:
        return {}

    n_original = len(resumo)
    r = resumo.copy()
    r["data_decisao"] = pd.to_datetime(r["data_decisao"])
    r["data_venda_prevista"] = pd.to_datetime(r["data_venda_prevista"])
    # O último período do backtest pode não ter data de venda (não há dados
    # futuros suficientes no arquivo pra "fechar" o período) — sem essa data,
    # não dá pra alinhar com o benchmark nem anualizar direito, então descarta.
    r = r.dropna(subset=["data_venda_prevista"])
    if r.empty:
        return {}
    periodos_excluidos = n_original - len(r)

    r["capital_antes"] = r["capital_apos_periodo"].shift(1).fillna(capital_inicial)
    r["retorno_periodo"] = r["lucro_periodo"] / r["capital_antes"]

    capital_final = float(r["capital_apos_periodo"].iloc[-1])
    retorno_total = capital_final / capital_inicial - 1

    n_periodos = len(r)
    dias_totais = (r["data_venda_prevista"].iloc[-1] - r["data_decisao"].iloc[0]).days
    periodos_por_ano = (n_periodos / dias_totais * 365) if dias_totais > 0 else np.nan
    retorno_anualizado = _anualizar(retorno_total, dias_totais)

    vol_periodo = float(r["retorno_periodo"].std(ddof=1)) if n_periodos > 1 else np.nan
    vol_anualizada = vol_periodo * np.sqrt(periodos_por_ano) if pd.notna(vol_periodo) else np.nan

    curva = pd.concat([pd.Series([capital_inicial]), r["capital_apos_periodo"]], ignore_index=True)
    pico = curva.cummax()
    drawdown = (curva - pico) / pico
    max_drawdown = float(drawdown.min())

    resultado = {
        "n_periodos": n_periodos,
        "periodos_excluidos_sem_data_venda": periodos_excluidos,
        "retorno_total_pct": round(retorno_total * 100, 2),
        "retorno_anualizado_pct": round(retorno_anualizado * 100, 2) if pd.notna(retorno_anualizado) else None,
        "volatilidade_anualizada_pct": round(vol_anualizada * 100, 2) if pd.notna(vol_anualizada) else None,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "calmar": round(retorno_anualizado / abs(max_drawdown), 3)
        if pd.notna(retorno_anualizado) and max_drawdown != 0 else None,
    }

    # --- Profit Factor e Win Rate: por OPERAÇÃO, não por período ---
    if operacoes is not None and not operacoes.empty and "lucro" in operacoes.columns:
        vencedoras = operacoes.loc[operacoes["lucro"] > 0, "lucro"].sum()
        perdedoras = operacoes.loc[operacoes["lucro"] < 0, "lucro"].sum()
        resultado["win_rate_pct"] = round(float((operacoes["lucro"] > 0).mean()) * 100, 1)
        resultado["profit_factor"] = round(float(vencedoras / abs(perdedoras)), 3) if perdedoras != 0 else None
        resultado["n_operacoes"] = len(operacoes)

    # --- SELIC: taxa livre de risco por período + Sharpe + Sortino ---
    retorno_selic_acumulado = None
    if selic is not None:
        r["retorno_selic_periodo"] = r.apply(
            lambda row: _retorno_selic_periodo(selic, row["data_decisao"], row["data_venda_prevista"]), axis=1
        )
        retorno_selic_acumulado = float(np.prod(1 + r["retorno_selic_periodo"].dropna()) - 1)
        resultado["retorno_selic_pct"] = round(retorno_selic_acumulado * 100, 2)
        excesso = r["retorno_periodo"] - r["retorno_selic_periodo"]
    else:
        # Sem SELIC informada: risco livre = 0 (Sharpe/Sortino "simples").
        excesso = r["retorno_periodo"]

    desvio_excesso = excesso.std(ddof=1)
    if pd.notna(desvio_excesso) and desvio_excesso != 0:
        resultado["sharpe"] = round(float(excesso.mean() / desvio_excesso * np.sqrt(periodos_por_ano)), 3)
    else:
        resultado["sharpe"] = None

    downside = excesso[excesso < 0]
    downside_dev = np.sqrt((downside ** 2).mean()) if not downside.empty else np.nan
    if pd.notna(downside_dev) and downside_dev != 0:
        resultado["sortino"] = round(float(excesso.mean() / downside_dev * np.sqrt(periodos_por_ano)), 3)
    else:
        resultado["sortino"] = None

    # --- Ibovespa: retorno no mesmo período + Beta + Alfa de Jensen (CAPM) ---
    if ibovespa is not None:
        r["retorno_ibov_periodo"] = r.apply(
            lambda row: _retorno_ibov_periodo(ibovespa, row["data_decisao"], row["data_venda_prevista"]), axis=1
        )
        retorno_ibov_acumulado = float(np.prod(1 + r["retorno_ibov_periodo"].dropna()) - 1)
        resultado["retorno_ibovespa_pct"] = round(retorno_ibov_acumulado * 100, 2)

        validos = r.dropna(subset=["retorno_periodo", "retorno_ibov_periodo"])
        beta = None
        if len(validos) > 2 and validos["retorno_ibov_periodo"].var() > 0:
            beta = float(np.cov(validos["retorno_periodo"], validos["retorno_ibov_periodo"])[0, 1]
                          / validos["retorno_ibov_periodo"].var())
            resultado["beta"] = round(beta, 3)
        else:
            resultado["beta"] = None

        # Alfa de Jensen (CAPM): precisa de Rf (Selic) + Rm (Ibovespa) + beta,
        # todos anualizados no MESMO período do backtest — não é só "retorno
        # da estratégia menos retorno do Ibovespa" (isso seria um alfa ingênuo,
        # sem descontar o risco/beta assumido).
        if beta is not None and retorno_selic_acumulado is not None:
            rf_a = _anualizar(retorno_selic_acumulado, dias_totais)
            rm_a = _anualizar(retorno_ibov_acumulado, dias_totais)
            if pd.notna(rf_a) and pd.notna(rm_a) and pd.notna(retorno_anualizado):
                retorno_esperado_capm = rf_a + beta * (rm_a - rf_a)
                alfa_jensen = retorno_anualizado - retorno_esperado_capm
                resultado["retorno_esperado_capm_pct"] = round(retorno_esperado_capm * 100, 2)
                resultado["alfa_jensen_pct_aa"] = round(alfa_jensen * 100, 2)
        if resultado.get("alfa_jensen_pct_aa") is None:
            resultado["alfa_jensen_pct_aa"] = None
            resultado.setdefault(
                "nota_alfa", "Alfa de Jensen requer SELIC + Ibovespa + beta válido; forneça a SELIC também."
            )

    return resultado
