"""
Pipeline para baixar dados históricos diários da Selic
através da API oficial do Banco Central do Brasil (SGS).

Série utilizada:
    11 - Taxa de juros - Selic (taxa diária, divulgada em % ao dia)

IMPORTANTE: esta série é a que `metricas_risco.carregar_selic` espera —
valores pequenos, tipo "0.024620" (% ao dia). A série 1178 ("Selic
anualizada base 252") é derivada da 11 pela fórmula do BCB
((SERIE(11)/100+1)^252-1)*100 e vem em % a.a. (valores tipo "13.65").
Usar a 1178 aqui faria `curva_capital_selic` compor uma taxa ANUAL como
se fosse diária (`(1 + taxa).cumprod()` por pregão), inflando a curva de
capital de forma absurda. Não troque sem também ajustar
`metricas_risco.carregar_selic`/`curva_capital_selic` de volta.

Exemplos:

    python selic_bcb.py --inicio 2019 --fim 2019

    python selic_bcb.py --inicio 2019 --fim 2025

    python selic_bcb.py --inicio 2019 --fim 2025 --consolidar

    python selic_bcb.py --inicio 2019 --fim 2025 --sobrescrever

    python selic_bcb.py \
        --inicio 2019 \
        --fim 2025 \
        --diretorio dados_selic \
        --consolidar

Dependências:
    pip install requests
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import requests


SERIE_SGS = 11

FONTE = "Banco Central do Brasil - SGS"

URL_BASE = (
    "https://api.bcb.gov.br/dados/serie/"
    f"bcdata.sgs.{SERIE_SGS}/dados"
)


def build_session() -> requests.Session:
    """
    Cria uma sessão HTTP com User-Agent.
    """

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; SELIC-BCB-Pipeline/1.0)"
            )
        }
    )

    return session


def download_year(
    session: requests.Session,
    ano: int,
    destino: Path,
    sobrescrever: bool = False,
    tentativas: int = 3,
) -> Path:
    """
    Baixa os dados da Selic de um determinado ano
    e salva o JSON original retornado pela API.
    """

    destino.mkdir(
        parents=True,
        exist_ok=True,
    )

    arquivo = destino / f"selic_{ano}.json"

    # Não baixa novamente se o arquivo já existir.
    if (
        arquivo.exists()
        and arquivo.stat().st_size > 0
        and not sobrescrever
    ):
        logging.info(
            "%s já existe.",
            arquivo.name,
        )

        return arquivo

    inicio = f"01/01/{ano}"
    fim = f"31/12/{ano}"

    params = {
        "formato": "json",
        "dataInicial": inicio,
        "dataFinal": fim,
    }

    erros: list[str] = []

    for tentativa in range(
        1,
        tentativas + 1,
    ):

        try:

            logging.info(
                "Baixando Selic %d "
                "(tentativa %d/%d)",
                ano,
                tentativa,
                tentativas,
            )

            resposta = session.get(
                URL_BASE,
                params=params,
                timeout=(20, 120),
            )

            resposta.raise_for_status()

            # Verifica se a resposta é realmente JSON.
            try:
                dados = resposta.json()
            except ValueError as exc:
                raise RuntimeError(
                    "A API retornou conteúdo que não é JSON."
                ) from exc

            if not isinstance(dados, list):
                raise RuntimeError(
                    "Formato inesperado retornado pela API."
                )

            # Valida os registros.
            for registro in dados:

                if not isinstance(
                    registro,
                    dict,
                ):
                    raise RuntimeError(
                        "Registro inválido retornado pela API."
                    )

                if "data" not in registro:
                    raise RuntimeError(
                        "Registro sem campo 'data'."
                    )

                if "valor" not in registro:
                    raise RuntimeError(
                        "Registro sem campo 'valor'."
                    )

            # Salva exatamente no formato JSON.
            parcial = arquivo.with_suffix(
                ".json.part"
            )

            with parcial.open(
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    dados,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )

                handle.write("\n")

            parcial.replace(arquivo)

            logging.info(
                "Download concluído: %s (%d registros)",
                arquivo,
                len(dados),
            )

            return arquivo

        except Exception as exc:

            erro = (
                f"tentativa {tentativa}: {exc}"
            )

            erros.append(erro)

            logging.warning(
                "Falha ao baixar %d: %s",
                ano,
                exc,
            )

            if tentativa < tentativas:
                time.sleep(
                    min(
                        2 ** tentativa,
                        10,
                    )
                )

    raise RuntimeError(
        f"Não foi possível baixar a Selic "
        f"de {ano}.\n"
        + "\n".join(erros)
    )


def consolidate(
    files: list[Path],
    output: Path,
) -> Path:
    """
    Consolida vários JSONs anuais em um único JSON.
    """

    registros: list[dict] = []

    for arquivo in files:

        logging.info(
            "Lendo %s",
            arquivo.name,
        )

        with arquivo.open(
            "r",
            encoding="utf-8",
        ) as handle:

            dados = json.load(handle)

        if not isinstance(
            dados,
            list,
        ):
            raise RuntimeError(
                f"Formato inválido em {arquivo.name}."
            )

        registros.extend(dados)

    if not registros:
        raise RuntimeError(
            "Não há registros para consolidar."
        )

    # Remove possíveis duplicidades.
    registros_unicos = {}

    for registro in registros:

        chave = registro["data"]

        registros_unicos[chave] = registro

    registros = list(
        registros_unicos.values()
    )

    # Ordena cronologicamente.
    registros.sort(
        key=lambda registro: registro["data"]
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    parcial = output.with_suffix(
        ".json.part"
    )

    with parcial.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            registros,
            handle,
            ensure_ascii=False,
            indent=2,
        )

        handle.write("\n")

    parcial.replace(output)

    logging.info(
        "Arquivo consolidado: %s (%d registros)",
        output,
        len(registros),
    )

    return output


def parse_args() -> argparse.Namespace:

    current_year = date.today().year

    parser = argparse.ArgumentParser(
        description=(
            "Baixa dados históricos da "
            "Selic através do Banco Central."
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
        default=Path("dados_selic"),
        help=(
            "Diretório onde os dados "
            "serão armazenados."
        ),
    )

    parser.add_argument(
        "--consolidar",
        action="store_true",
        help=(
            "Cria também um JSON único "
            "com todos os anos."
        ),
    )

    parser.add_argument(
        "--sobrescrever",
        action="store_true",
        help=(
            "Baixa novamente arquivos "
            "existentes."
        ),
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
        level=getattr(
            logging,
            args.log_level,
        ),
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
    )

    if args.fim < args.inicio:

        logging.error(
            "--fim deve ser maior ou igual "
            "a --inicio."
        )

        return 2

    processed_dir = (
        args.diretorio / "processed"
    )

    outputs: list[Path] = []

    failures: list[
        tuple[int, str]
    ] = []

    for ano in range(
        args.inicio,
        args.fim + 1,
    ):

        try:

            output = download_year(
                session=build_session(),
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
            / (
                f"selic_"
                f"{args.inicio}_"
                f"{args.fim}.json"
            )
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