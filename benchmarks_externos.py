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
import os
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


def _escolher_range_brapi(data_inicio: str, data_fim: str) -> str:
    """A brapi.dev usa períodos pré-definidos (range), não datas soltas no
    endpoint /api/quote. Escolhe o menor bucket que cobre o intervalo
    pedido; o filtro fino pelas datas exatas é feito depois, em pandas."""
    dias = (pd.Timestamp(data_fim) - pd.Timestamp(data_inicio)).days
    anos = dias / 365
    if anos <= 1:
        return "1y"
    if anos <= 2:
        return "2y"
    if anos <= 5:
        return "5y"
    if anos <= 10:
        return "10y"
    return "max"


def baixar_ibovespa_brapi(data_inicio: str, data_fim: str, token: str) -> pd.DataFrame:
    """Baixa o fechamento diário do Ibovespa via brapi.dev (API brasileira
    dedicada a dados da B3 — ações, FIIs, BDRs e índices — com SLA e
    documentação em PT-BR; alternativa mais estável ao Yahoo Finance,
    mas exige token gratuito: cadastro em https://brapi.dev/dashboard).

    NÃO TESTADO contra a API real neste ambiente (sandbox sem acesso a
    brapi.dev) — a implementação segue a documentação pública
    (https://brapi.dev/docs/acoes), mas vale validar localmente antes de
    confiar no resultado, sobretudo o formato exato da resposta JSON.
    """
    range_str = _escolher_range_brapi(data_inicio, data_fim)
    url = "https://brapi.dev/api/quote/%5EBVSP"  # ^BVSP url-encoded
    params = {"range": range_str, "interval": "1d", "token": token}

    resposta = requests.get(url, params=params, timeout=30)
    resposta.raise_for_status()
    payload = resposta.json()

    resultados = payload.get("results") or []
    if not resultados or "historicalDataPrice" not in resultados[0]:
        raise RuntimeError(
            "Resposta da brapi.dev sem 'historicalDataPrice' — verifique o "
            "token, o plano da conta, ou se o formato da resposta mudou."
        )

    hist = pd.DataFrame(resultados[0]["historicalDataPrice"])
    hist["data"] = pd.to_datetime(hist["date"], unit="s")
    hist = hist.rename(columns={"close": "ibovespa_fechamento"})[["data", "ibovespa_fechamento"]]
    hist = hist[(hist["data"] >= pd.Timestamp(data_inicio)) & (hist["data"] <= pd.Timestamp(data_fim))]
    return hist.sort_values("data").reset_index(drop=True)


def baixar_ibovespa_yfinance(data_inicio: str, data_fim: str) -> pd.DataFrame:
    """Baixa o fechamento diário do Ibovespa (ticker ^BVSP) via yfinance.
    Retorna DataFrame com colunas: data, ibovespa_fechamento.

    Não é uma fonte oficial da B3, nem a mais estável (Yahoo Finance não
    tem SLA para uso programático). Se preferir a série oficial, baixe
    manualmente em:
    b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/
    indice-ibovespa-ibovespa-estatisticas-historicas.htm
    e adapte esta função para ler o arquivo baixado.
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


def baixar_ibovespa(data_inicio: str, data_fim: str, brapi_token: str | None = None) -> pd.DataFrame:
    """Baixa o fechamento diário do Ibovespa. Tenta brapi.dev primeiro se
    houver um token disponível (parâmetro `brapi_token` ou variável de
    ambiente BRAPI_TOKEN) — API brasileira dedicada, mais estável. Se não
    houver token, ou a chamada falhar, cai para yfinance (sem cadastro,
    porém sem SLA)."""
    token = brapi_token or os.environ.get("BRAPI_TOKEN")
    if token:
        try:
            return baixar_ibovespa_brapi(data_inicio, data_fim, token)
        except Exception as exc:
            logging.warning("Falha ao baixar Ibovespa via brapi.dev, tentando yfinance: %s", exc)
    return baixar_ibovespa_yfinance(data_inicio, data_fim)


def montar_benchmarks(data_inicio: str, data_fim: str, brapi_token: str | None = None) -> pd.DataFrame:
    """Baixa Selic, CDI e Ibovespa. Se uma das três fontes falhar (o
    Ibovespa é historicamente a mais instável das três, sobretudo via
    yfinance), NÃO descarta as outras — retorna o que conseguiu baixar,
    com aviso no log. Só levanta exceção se as três falharem.

    `brapi_token`: se informado (ou via variável de ambiente
    BRAPI_TOKEN), o Ibovespa é buscado via brapi.dev em vez de yfinance —
    ver `baixar_ibovespa`.
    """
    partes = []

    try:
        logging.info("Baixando Selic (SGS %d)...", CODIGO_SELIC)
        selic = _baixar_serie_bcb_em_blocos(CODIGO_SELIC, data_inicio, data_fim).rename(columns={"valor": "selic_diaria"})
        if not selic.empty:
            partes.append(selic)
    except Exception as exc:
        logging.warning("Falha ao baixar Selic, seguindo sem ela: %s", exc)

    try:
        logging.info("Baixando CDI (SGS %d)...", CODIGO_CDI)
        cdi = _baixar_serie_bcb_em_blocos(CODIGO_CDI, data_inicio, data_fim).rename(columns={"valor": "cdi_diario"})
        if not cdi.empty:
            partes.append(cdi)
    except Exception as exc:
        logging.warning("Falha ao baixar CDI, seguindo sem ele: %s", exc)

    try:
        logging.info("Baixando Ibovespa...")
        ibov = baixar_ibovespa(data_inicio, data_fim, brapi_token=brapi_token)
        if not ibov.empty:
            partes.append(ibov)
    except Exception as exc:
        logging.warning("Falha ao baixar Ibovespa, seguindo sem ele: %s", exc)

    if not partes:
        raise RuntimeError(
            "Não foi possível baixar nenhum dos três benchmarks (Selic, CDI, Ibovespa)."
        )

    df = partes[0]
    for parte in partes[1:]:
        df = df.merge(parte, on="data", how="outer")
    return df.sort_values("data").reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Baixa benchmarks externos (Selic, CDI, Ibovespa).")
    parser.add_argument("--inicio", required=True, help="Data inicial, formato YYYY-MM-DD.")
    parser.add_argument("--fim", default=str(date.today()), help="Data final, formato YYYY-MM-DD.")
    parser.add_argument("--formato", choices=["parquet", "csv"], default="parquet")
    parser.add_argument("--saida", type=Path, default=Path("dados_b3/benchmarks_externos"))
    parser.add_argument(
        "--brapi-token", default=None,
        help="Token gratuito da brapi.dev (brapi.dev/dashboard) para buscar o Ibovespa por lá em vez do yfinance. "
             "Também pode ser definido via variável de ambiente BRAPI_TOKEN.",
    )
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    df = montar_benchmarks(args.inicio, args.fim, brapi_token=args.brapi_token)

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