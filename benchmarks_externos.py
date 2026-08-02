#!/usr/bin/env python3
"""
Baixa benchmarks externos para comparação com a estratégia de grafo:
Selic e CDI (Banco Central do Brasil, API SGS) e Ibovespa (Yahoo Finance,
ticker ^BVSP — a B3 não disponibiliza a série do índice via API pública
simples, só por download manual em b3.com.br).

Gera um único arquivo (parquet ou csv) com colunas:
    data, selic_diaria, cdi_diario, ibovespa_fechamento

Roda de forma independente, via linha de comando — mesmo padrão do
b3_cotahist.py. Não é chamado automaticamente pelo app; o arquivo gerado
é subido manualmente em app_grafo.py (upload opcional de benchmarks).

Exemplos:
    python benchmarks_externos.py --inicio 2020-01-01 --fim 2026-07-30
    python benchmarks_externos.py --inicio 2020-01-01 --fim 2026-07-30 --formato csv

Dependências:
    pip install requests yfinance pandas
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import requests

BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
# Códigos oficiais do SGS (Sistema Gerenciador de Séries Temporais do BCB,
# https://dadosabertos.bcb.gov.br): 11 = Taxa Selic diária ("over", % ao
# dia); 12 = Taxa CDI diária (% ao dia).
CODIGO_SELIC = 11
CODIGO_CDI = 12


def baixar_serie_bcb(codigo: int, data_inicio: str, data_fim: str) -> pd.DataFrame:
    """Baixa uma série diária do SGS/BCB. Datas em 'YYYY-MM-DD'.
    Retorna DataFrame com colunas: data, valor (taxa em % ao dia).

    Observação: desde 26/03/2025 o BCB limita o volume retornado por
    consulta em séries diárias longas. Se `data_fim - data_inicio` for
    muito grande (vários anos), pode ser necessário baixar em blocos
    (ex.: ano a ano) e concatenar — ver `_baixar_serie_bcb_em_blocos`.
    """
    di = pd.Timestamp(data_inicio).strftime("%d/%m/%Y")
    dfim = pd.Timestamp(data_fim).strftime("%d/%m/%Y")
    url = BCB_SGS_URL.format(codigo=codigo)
    params = {"formato": "json", "dataInicial": di, "dataFinal": dfim}

    resposta = requests.get(url, params=params, timeout=30)
    resposta.raise_for_status()
    dados = resposta.json()

    df = pd.DataFrame(dados)
    if df.empty:
        return pd.DataFrame(columns=["data", "valor"])

    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"].astype(str).str.replace(",", "."), errors="coerce")
    return df[["data", "valor"]].sort_values("data").reset_index(drop=True)


def _baixar_serie_bcb_em_blocos(codigo: int, data_inicio: str, data_fim: str, anos_por_bloco: int = 5) -> pd.DataFrame:
    """Mesma coisa que `baixar_serie_bcb`, mas em blocos de `anos_por_bloco`
    anos, para não esbarrar no limite de volume do BCB em séries longas.
    """
    inicio = pd.Timestamp(data_inicio)
    fim = pd.Timestamp(data_fim)
    blocos = []
    cursor = inicio
    while cursor < fim:
        proximo = min(cursor + pd.DateOffset(years=anos_por_bloco), fim)
        blocos.append(baixar_serie_bcb(codigo, cursor.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        cursor = proximo + pd.Timedelta(days=1)
    if not blocos:
        return pd.DataFrame(columns=["data", "valor"])
    return pd.concat(blocos, ignore_index=True).drop_duplicates(subset="data").sort_values("data")


def baixar_ibovespa(data_inicio: str, data_fim: str) -> pd.DataFrame:
    """Baixa o fechamento diário do Ibovespa (ticker ^BVSP) via yfinance.
    Retorna DataFrame com colunas: data, ibovespa_fechamento.

    Não é uma fonte oficial da B3. Se preferir a série oficial, baixe
    manualmente em:
    b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/
    indice-ibovespa-ibovespa-estatisticas-historicas.htm
    e adapte esta função para ler o arquivo baixado em vez de chamar o
    yfinance.
    """
    import yfinance as yf

    dados = yf.download("^BVSP", start=data_inicio, end=data_fim, progress=False)
    if dados.empty:
        raise RuntimeError(
            "Não foi possível baixar dados do Ibovespa via yfinance. "
            "Considere baixar manualmente a série oficial da B3 (ver docstring)."
        )

    dados = dados.reset_index()
    # yfinance pode retornar colunas em MultiIndex dependendo da versão.
    if isinstance(dados.columns, pd.MultiIndex):
        dados.columns = [c[0] for c in dados.columns]
    dados = dados[["Date", "Close"]].rename(columns={"Date": "data", "Close": "ibovespa_fechamento"})
    return dados


def montar_benchmarks(data_inicio: str, data_fim: str) -> pd.DataFrame:
    logging.info("Baixando Selic (SGS %d)...", CODIGO_SELIC)
    selic = _baixar_serie_bcb_em_blocos(CODIGO_SELIC, data_inicio, data_fim).rename(columns={"valor": "selic_diaria"})

    logging.info("Baixando CDI (SGS %d)...", CODIGO_CDI)
    cdi = _baixar_serie_bcb_em_blocos(CODIGO_CDI, data_inicio, data_fim).rename(columns={"valor": "cdi_diario"})

    logging.info("Baixando Ibovespa (yfinance, ^BVSP)...")
    ibov = baixar_ibovespa(data_inicio, data_fim)

    df = selic.merge(cdi, on="data", how="outer").merge(ibov, on="data", how="outer")
    return df.sort_values("data").reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Baixa benchmarks externos (Selic, CDI, Ibovespa).")
    parser.add_argument("--inicio", required=True, help="Data inicial, formato YYYY-MM-DD.")
    parser.add_argument("--fim", default=str(date.today()), help="Data final, formato YYYY-MM-DD.")
    parser.add_argument("--formato", choices=["parquet", "csv"], default="parquet")
    parser.add_argument("--saida", type=Path, default=Path("dados_b3/benchmarks_externos"))
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    df = montar_benchmarks(args.inicio, args.fim)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    ext = "parquet" if args.formato == "parquet" else "csv"
    saida = args.saida.with_suffix(f".{ext}")
    if args.formato == "parquet":
        df.to_parquet(saida, index=False)
    else:
        df.to_csv(saida, index=False)

    logging.info("Arquivo salvo: %s (%d linhas)", saida, len(df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())