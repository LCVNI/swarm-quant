
"""
Pipeline para baixar cotações históricas diárias do Ibovespa (^BVSP)
através do Yahoo Finance usando yfinance.

Exemplos:
    python ibovespa_yfinance.py --inicio 2019 --fim 2026
    python ibovespa_yfinance.py --inicio 2019 --fim 2026 --consolidar
    python ibovespa_yfinance.py --inicio 2020 --fim 2025 --sobrescrever
    python ibovespa_yfinance.py --inicio 2019 --fim 2026 --diretorio dados_ibovespa

Dependências:
    pip install yfinance pandas
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf


TICKER = "^BVSP"
FONTE = "Yahoo Finance"

COLUNAS = [
    "simbolo",
    "data",
    "abertura",
    "maxima",
    "minima",
    "fechamento",
    "fechamento_ajustado",
    "volume",
    "fonte",
]


def download_year(
    ano: int,
    destino: Path,
    sobrescrever: bool = False,
    tentativas: int = 3,
) -> Path:
    """
    Baixa os dados do Ibovespa para um determinado ano e salva em CSV.
    """

    destino.mkdir(parents=True, exist_ok=True)

    arquivo = destino / f"ibovespa_{ano}.csv"

    if arquivo.exists() and arquivo.stat().st_size > 0 and not sobrescrever:
        logging.info("%s já existe.", arquivo.name)
        return arquivo

    # O end do yfinance é exclusivo.
    inicio = f"{ano}-01-01"
    fim = f"{ano + 1}-01-01"

    erros: list[str] = []

    for tentativa in range(1, tentativas + 1):
        try:
            logging.info(
                "Baixando Ibovespa: %d (tentativa %d/%d)",
                ano,
                tentativa,
                tentativas,
            )

            df = yf.download(
                TICKER,
                start=inicio,
                end=fim,
                interval="1d",
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
            )

            if df.empty:
                raise RuntimeError(
                    f"Nenhum dado retornado para o ano {ano}."
                )

            # Algumas versões do yfinance podem retornar MultiIndex
            # mesmo quando apenas um ticker é solicitado.
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.reset_index()

            # Normaliza o nome da coluna de data.
            if "Date" in df.columns:
                df = df.rename(columns={"Date": "data"})
            elif "Datetime" in df.columns:
                df = df.rename(columns={"Datetime": "data"})

            # Garante que as colunas esperadas existem.
            colunas_yf = {
                "Open": "abertura",
                "High": "maxima",
                "Low": "minima",
                "Close": "fechamento",
                "Adj Close": "fechamento_ajustado",
                "Volume": "volume",
            }

            df = df.rename(columns=colunas_yf)

            colunas_obrigatorias = [
                "data",
                "abertura",
                "maxima",
                "minima",
                "fechamento",
                "fechamento_ajustado",
                "volume",
            ]

            faltantes = [
                coluna
                for coluna in colunas_obrigatorias
                if coluna not in df.columns
            ]

            if faltantes:
                raise RuntimeError(
                    "Colunas esperadas não encontradas: "
                    + ", ".join(faltantes)
                )

            # Mantém somente os pregões do ano solicitado.
            df["data"] = pd.to_datetime(df["data"]).dt.tz_localize(None)

            df = df[
                (df["data"] >= pd.Timestamp(f"{ano}-01-01"))
                & (df["data"] < pd.Timestamp(f"{ano + 1}-01-01"))
            ].copy()

            if df.empty:
                raise RuntimeError(
                    f"Nenhum pregão encontrado para o ano {ano}."
                )

            # Metadados.
            df.insert(0, "simbolo", TICKER)
            df["fonte"] = FONTE

            # Ordem final das colunas.
            df = df[COLUNAS]

            # Conversão numérica.
            colunas_numericas = [
                "abertura",
                "maxima",
                "minima",
                "fechamento",
                "fechamento_ajustado",
                "volume",
            ]

            for coluna in colunas_numericas:
                df[coluna] = pd.to_numeric(
                    df[coluna],
                    errors="coerce",
                )

            # Volume é inteiro.
            df["volume"] = df["volume"].astype("Int64")

            # Data no padrão YYYY-MM-DD.
            df["data"] = df["data"].dt.strftime("%Y-%m-%d")

            # Remove possíveis duplicidades.
            df = df.drop_duplicates(
                subset=["simbolo", "data"],
                keep="last",
            )

            # Ordena cronologicamente.
            df = df.sort_values("data")

            arquivo.parent.mkdir(parents=True, exist_ok=True)

            df.to_csv(
                arquivo,
                index=False,
                encoding="utf-8",
            )

            logging.info(
                "Download concluído: %s (%d linhas)",
                arquivo,
                len(df),
            )

            return arquivo

        except Exception as exc:
            erros.append(
                f"tentativa {tentativa}: {exc}"
            )

            logging.warning(
                "Falha ao baixar %d: %s",
                ano,
                exc,
            )

            if tentativa < tentativas:
                time.sleep(min(2 ** tentativa, 10))

    raise RuntimeError(
        f"Não foi possível processar o Ibovespa de {ano}.\n"
        + "\n".join(erros)
    )


def consolidate(
    files: list[Path],
    output: Path,
) -> Path:
    """
    Consolida vários CSVs anuais em um único CSV.
    """

    frames: list[pd.DataFrame] = []

    for file in files:
        logging.info("Lendo %s", file.name)

        df = pd.read_csv(file)

        frames.append(df)

    if not frames:
        raise RuntimeError(
            "Não há arquivos para consolidar."
        )

    df = pd.concat(
        frames,
        ignore_index=True,
    )

    # Remove duplicidades.
    df = df.drop_duplicates(
        subset=["simbolo", "data"],
        keep="last",
    )

    # Ordena por data.
    df = df.sort_values(
        ["simbolo", "data"]
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        output,
        index=False,
        encoding="utf-8",
    )

    logging.info(
        "Arquivo consolidado: %s (%d linhas)",
        output,
        len(df),
    )

    return output


def parse_args() -> argparse.Namespace:
    current_year = date.today().year

    parser = argparse.ArgumentParser(
        description=(
            "Baixa e converte dados históricos "
            "do Ibovespa (^BVSP) via Yahoo Finance."
        )
    )

    parser.add_argument(
        "--inicio",
        type=int,
        default=current_year,
        help="Primeiro ano a baixar.",
    )

    parser.add_argument(
        "--fim",
        type=int,
        default=current_year,
        help="Último ano a baixar.",
    )

    parser.add_argument(
        "--diretorio",
        type=Path,
        default=Path("dados_ibovespa"),
        help="Diretório onde os dados serão armazenados.",
    )

    parser.add_argument(
        "--consolidar",
        action="store_true",
        help="Cria também um CSV único com todos os anos.",
    )

    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Baixa novamente arquivos existentes.",
    )

    parser.add_argument(
        "--log-level",
        choices=[
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
        ],
        default="INFO",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if args.fim < args.inicio:
        logging.error(
            "--fim deve ser maior ou igual a --inicio."
        )
        return 2

    processed_dir = (
        args.diretorio / "processed"
    )

    outputs: list[Path] = []
    failures: list[tuple[int, str]] = []

    for ano in range(
        args.inicio,
        args.fim + 1,
    ):
        try:
            output = download_year(
                ano=ano,
                destino=processed_dir,
                sobrescrever=args.sobrescrever,
            )

            outputs.append(output)

        except Exception as exc:
            failures.append(
                (ano, str(exc))
            )

            logging.error(
                "Ano %d não processado: %s",
                ano,
                exc,
            )

    if args.consolidar and outputs:
        consolidated = (
            args.diretorio
            / f"ibovespa_{args.inicio}_{args.fim}.csv"
        )

        consolidate(
            outputs,
            consolidated,
        )

    if failures:
        logging.warning(
            "Anos com falha:"
        )

        for ano, erro in failures:
            logging.warning(
                "  %d: %s",
                ano,
                erro,
            )

        return 1

    logging.info(
        "Pipeline concluído com sucesso."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
