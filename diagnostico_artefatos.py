"""Diagnóstico: quanto do resultado do backtest vem de retornos implausíveis?

o COTAHIST traz preços NÃO ajustados para eventos corporativos
(desdobramento, grupamento, bonificação). Um grupamento de 10:1 faz o preço
saltar 10x da noite para o dia; um desdobramento faz cair 90%. Nenhum dos dois
é retorno econômico, mas `retorno_futuro = preco[t+h]/preco[t] - 1` lê os dois
como se fossem. Se uma posição estiver aberta na data do evento, o backtest
registra um lucro (ou prejuízo) fictício, potencialmente enorme.

O arquivo COTAHIST tem a coluna `fator_cotacao` justamente para isso: quando ela
muda para um ticker, houve evento que altera a base de cotação.

Uso:
    python diagnostico_artefatos.py caminho/para/cotahist.parquet
    python diagnostico_artefatos.py dados.parquet --operacoes operacoes.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

LIMIAR_RETORNO_SUSPEITO = 0.60  # |retorno| em 1 pregão acima disso é candidato a artefato


def carregar(caminho: str) -> pd.DataFrame:
    df = pd.read_parquet(caminho) if caminho.endswith(".parquet") else pd.read_csv(
        caminho, parse_dates=["data_pregao"]
    )
    if "tipo_mercado" in df.columns:
        df = df[df["tipo_mercado"] == 10].copy()
    return df.sort_values(["ticker", "data_pregao"])


def checar_fator_cotacao(df: pd.DataFrame) -> pd.DataFrame:
    """Lista os tickers/datas em que `fator_cotacao` mudou (evento corporativo)."""
    if "fator_cotacao" not in df.columns:
        print("AVISO: coluna `fator_cotacao` ausente no arquivo. Regere o parquet com "
              "o b3_cotahist.py, que já extrai esse campo, para habilitar esta checagem.")
        return pd.DataFrame()

    g = df.groupby("ticker", group_keys=False)
    df = df.copy()
    df["fator_anterior"] = g["fator_cotacao"].shift(1)
    mudou = df[df["fator_anterior"].notna() & (df["fator_cotacao"] != df["fator_anterior"])]
    return mudou[["ticker", "data_pregao", "fator_anterior", "fator_cotacao", "preco_fechamento"]]


BDI_NOMES = {
    2: "LOTE PADRAO (ações)", 5: "SANCIONADAS", 6: "CONCORDATARIAS",
    7: "RECUPERACAO EXTRAJUDICIAL", 8: "RECUPERACAO JUDICIAL", 9: "RAET",
    10: "DIREITOS E RECIBOS", 11: "INTERVENCAO", 12: "FUNDOS IMOBILIARIOS",
    13: "FIAGRO (fundos do agronegócio)",
    14: "CERT.INVEST/TIT.DIV.PUBLICA", 18: "OBRIGACOES", 22: "BONUS PRIVADOS",
    26: "APOLICES/TITULOS PUBLICOS", 32: "EXERC. OPCAO COMPRA INDICE",
    33: "EXERC. OPCAO VENDA INDICE",
    34: "BDR nao patrocinado (DRN)", 35: "BDR patrocinado (DR1/DR2/DR3)",
    36: "BDR de ETF (DRE)",
    38: "EXERC. OPCAO COMPRA",
    42: "EXERC. OPCAO VENDA", 46: "LEILAO DE NAO COTADOS",
    58: "misto/situacao especial (ver amostra)",
}
# Códigos 2, 5-12, 14, 18, 22, 26, 32, 33, 38, 42, 46: tabela anexa do layout
# oficial do COTAHIST (B3). Códigos 13, 34, 35, 36 e 58 não constam nessa
# tabela; foram identificados empiricamente pela coluna `especificacao` e pelo
# sufixo dos tickers na base 2019-2026:
#   34 -> especificacao DRN, tickers *34 (BDR nao patrocinado nivel I)
#   35 -> especificacao DR1/DR3, tickers *31/*32/*33 (BDR patrocinado)
#   36 -> especificacao DRE, tickers *39 (BDR de ETF)
#   13 -> especificacao CI, tickers FIAGRO (*11 e seus direitos *12)
#   58 -> MISTO: contém ações reais (AZUL4, CCXC3) junto com recibos (AZUL53,
#         AZUL54). Por ser misto, filtrar só BDI 2 abre BURACO na série desses
#         tickers — ver `marcar_descontinuidades` em universo.py.


def amostrar_tickers_por_bdi(df: pd.DataFrame, codigos: list[int], n: int = 8) -> None:
    """Lista alguns tickers de cada código BDI, para identificar instrumentos
    cujo código não consta na tabela oficial."""
    colunas_extra = [c for c in ("especificacao", "nome_resumido") if c in df.columns]
    for codigo in codigos:
        sub = df[df["codigo_bdi"] == codigo]
        if sub.empty:
            continue
        tickers = sorted(sub["ticker"].unique())[:n]
        print(f"\n  BDI {codigo}: {', '.join(tickers)}")
        if colunas_extra:
            exemplo = sub.drop_duplicates("ticker").head(3)[["ticker"] + colunas_extra]
            print(exemplo.to_string(index=False))


def composicao_por_bdi(df: pd.DataFrame) -> pd.DataFrame:
    """Quantas linhas/tickers há de cada tipo de instrumento (código BDI).
    Fonte da tabela: layout oficial do COTAHIST (B3)."""
    if "codigo_bdi" not in df.columns:
        print("AVISO: coluna `codigo_bdi` ausente. Sem ela não dá para separar ações "
              "de direitos/recibos, FIIs e papéis de empresas em recuperação.")
        return pd.DataFrame()
    comp = df.groupby("codigo_bdi").agg(
        linhas=("ticker", "size"), tickers=("ticker", "nunique")
    ).reset_index()
    comp["instrumento"] = comp["codigo_bdi"].map(BDI_NOMES).fillna("(desconhecido)")
    comp["pct_linhas"] = (comp["linhas"] / len(df) * 100).round(2)
    return comp.sort_values("linhas", ascending=False)[
        ["codigo_bdi", "instrumento", "linhas", "pct_linhas", "tickers"]
    ]


def _perto_de_inteiro(r: float) -> bool:
    """True se a razão de preço (ou seu inverso) estiver perto de um inteiro —
    assinatura típica de desdobramento/grupamento (2:1, 10:1, 1000:1...).
    Protegido contra inf/nan/zero, que aparecem quando o preço anterior era 0."""
    if not np.isfinite(r) or r <= 0:
        return False
    candidatos = [abs(r - round(r))]
    if r > 1e-9:
        inverso = 1 / r
        if np.isfinite(inverso) and inverso < 1e9:
            candidatos.append(abs(inverso - round(inverso)))
    return min(candidatos) < 0.05


def precos_invalidos(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas com preço de fechamento zero ou negativo. Não deveriam existir e
    quebram qualquer cálculo de retorno (divisão por zero -> retorno infinito)."""
    return df[df["preco_fechamento"] <= 0][
        ["ticker", "data_pregao", "preco_fechamento"]
    ]


def retornos_extremos(df: pd.DataFrame, limiar: float = LIMIAR_RETORNO_SUSPEITO) -> pd.DataFrame:
    df = df.copy()
    df["retorno_1d"] = df.groupby("ticker", group_keys=False)["preco_fechamento"].pct_change()
    df = df[np.isfinite(df["retorno_1d"])]
    extremos = df[df["retorno_1d"].abs() > limiar].copy()
    extremos["razao_preco"] = 1 + extremos["retorno_1d"]
    extremos["perto_de_inteiro"] = extremos["razao_preco"].apply(_perto_de_inteiro)
    return extremos[["ticker", "data_pregao", "preco_fechamento", "retorno_1d",
                     "razao_preco", "perto_de_inteiro"]].sort_values("retorno_1d", ascending=False)


def concentracao_do_lucro(operacoes: pd.DataFrame) -> None:
    """Quanto do lucro total veio das poucas operações de maior magnitude."""
    if operacoes.empty or "lucro" not in operacoes.columns:
        return
    ops = operacoes.sort_values("lucro", ascending=False)
    lucro_total = ops["lucro"].sum()
    print(f"\nLucro total das operações: R$ {lucro_total:,.2f}")
    for n in (1, 5, 10, 20):
        if len(ops) >= n:
            parcela = ops["lucro"].head(n).sum()
            print(f"  Top {n:>2} operações: R$ {parcela:>14,.2f}  "
                  f"({parcela / lucro_total * 100:>6.1f}% do lucro total)")

    if "retorno_realizado" in ops.columns:
        suspeitas = ops[ops["retorno_realizado"].abs() > LIMIAR_RETORNO_SUSPEITO]
        if not suspeitas.empty:
            lucro_suspeito = suspeitas["lucro"].sum()
            print(f"\n  Operações com |retorno| > {LIMIAR_RETORNO_SUSPEITO:.0%}: {len(suspeitas)}")
            print(f"  Lucro vindo delas: R$ {lucro_suspeito:,.2f} "
                  f"({lucro_suspeito / lucro_total * 100:.1f}% do total)")
            print("\n  Maiores:")
            print(suspeitas[["data_compra", "ticker", "preco_compra", "preco_venda",
                             "retorno_realizado", "lucro"]].head(10).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dados", help="parquet/csv do COTAHIST processado")
    ap.add_argument("--operacoes", help="CSV com as operações exportadas do backtest")
    ap.add_argument("--limiar", type=float, default=LIMIAR_RETORNO_SUSPEITO)
    args = ap.parse_args()

    df = carregar(args.dados)
    print(f"Base: {len(df):,} linhas | {df['ticker'].nunique()} tickers | "
          f"{df['data_pregao'].min().date()} a {df['data_pregao'].max().date()}")

    print("\n=== 1. Composição da base por tipo de instrumento (código BDI) ===")
    comp = composicao_por_bdi(df)
    if not comp.empty:
        print(comp.to_string(index=False))
        so_acoes = comp[comp["codigo_bdi"] == 2]
        if not so_acoes.empty:
            print(f"\n  Ações em lote padrão são {so_acoes['pct_linhas'].iloc[0]:.1f}% da base. "
                  "O restante NÃO deveria estar no universo de uma estratégia de ações.")
        desconhecidos = comp.loc[comp["instrumento"] == "(desconhecido)", "codigo_bdi"].tolist()
        if desconhecidos:
            print(f"\n  Códigos BDI fora da tabela oficial do layout: {desconhecidos}")
            print("  Amostras de tickers para identificação:")
            amostrar_tickers_por_bdi(df, desconhecidos)

    print("\n=== 2. Mudanças de fator_cotacao (evento corporativo confirmado) ===")
    eventos = checar_fator_cotacao(df)
    if not eventos.empty:
        print(f"{len(eventos)} evento(s) detectado(s), em {eventos['ticker'].nunique()} ticker(s).")
        print(eventos.head(15).to_string(index=False))
    elif "fator_cotacao" in df.columns:
        print("Nenhuma mudança de fator_cotacao encontrada.")

    print(f"\n=== 3. Preços de fechamento inválidos (zero ou negativo) ===")
    invalidos = precos_invalidos(df)
    if invalidos.empty:
        print("Nenhum. Bom sinal.")
    else:
        print(f"{len(invalidos)} linha(s) em {invalidos['ticker'].nunique()} ticker(s). "
              "Essas linhas geram retorno infinito e contaminam qualquer cálculo que as use.")
        print(invalidos.head(15).to_string(index=False))
        print("\n  Tickers afetados:", ", ".join(sorted(invalidos["ticker"].unique())[:25]))

    print(f"\n=== 4. Retornos diários acima de {args.limiar:.0%} (candidatos a artefato) ===")
    extremos = retornos_extremos(df, args.limiar)
    if extremos.empty:
        print("Nenhum retorno diário extremo encontrado.")
    else:
        n_inteiro = int(extremos["perto_de_inteiro"].sum())
        print(f"{len(extremos)} ocorrência(s); {n_inteiro} com razão de preço perto de um "
              f"inteiro (assinatura típica de desdobramento/grupamento).")
        print(f"Tickers distintos afetados: {extremos['ticker'].nunique()}")
        print(extremos.head(20).to_string(index=False))

        if "codigo_bdi" in df.columns:
            por_bdi = extremos.merge(
                df[["ticker", "data_pregao", "codigo_bdi"]], on=["ticker", "data_pregao"], how="left"
            )
            resumo_bdi = por_bdi.groupby("codigo_bdi").size().reset_index(name="ocorrencias")
            resumo_bdi["instrumento"] = resumo_bdi["codigo_bdi"].map(BDI_NOMES).fillna("(desconhecido)")
            print("\n  Retornos extremos por tipo de instrumento:")
            print(resumo_bdi.sort_values("ocorrencias", ascending=False).to_string(index=False))
            em_acoes = int(resumo_bdi.loc[resumo_bdi["codigo_bdi"] == 2, "ocorrencias"].sum())
            print(f"\n  Sobrariam {em_acoes} de {len(extremos)} ocorrências se o universo "
                  "fosse restrito a ações em lote padrão (codigo_bdi == 2).")

    if args.operacoes:
        print("\n=== 5. Concentração do lucro no backtest ===")
        ops = pd.read_csv(args.operacoes)
        concentracao_do_lucro(ops)


if __name__ == "__main__":
    main()