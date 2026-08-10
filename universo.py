"""Filtragem do universo investível a partir do COTAHIST.

Problema que este módulo resolve: filtrar apenas `tipo_mercado == 10` (mercado à
vista) NÃO restringe a base a ações. Direitos e recibos de subscrição, fundos
imobiliários, BDRs e papéis de empresas em recuperação judicial também são
negociados à vista. Direitos de subscrição, em particular, são instrumentos de
vida curta e liquidez quase nula, cujo preço salta de R$ 0,01 para R$ 1,00 sem
que exista contraparte real para executar a ordem — e um backtest ingênuo lê
isso como +9900% de lucro.

O campo correto para separar ações é o `codigo_bdi`. Segundo o layout oficial do
COTAHIST (B3, SeriesHistoricas_Layout.pdf):

    02  LOTE PADRAO                 <- ações negociadas normalmente
    05  SANCIONADAS PELOS REGULAMENTOS
    06  CONCORDATARIAS
    07  RECUPERACAO EXTRAJUDICIAL
    08  RECUPERACAO JUDICIAL
    09  RAET (administração especial temporária)
    10  DIREITOS E RECIBOS          <- causa da maioria dos artefatos
    11  INTERVENCAO
    12  FUNDOS IMOBILIARIOS
    14  CERT.INVEST/TIT.DIV.PUBLICA
    18  OBRIGACOES
    22  BONUS (PRIVADOS)
    26  APOLICES/BONUS/TITULOS PUBLICOS
    32/33/38/42  EXERCICIO DE OPCOES
    46  LEILAO DE NAO COTADOS

Códigos como 13, 34, 35, 36 e 58 aparecem em bases recentes mas NÃO constam na
tabela anexa do layout publicado. Identifique-os na sua própria base (o
diagnostico_artefatos.py amostra tickers por código) antes de incluí-los.

Segunda camada, igualmente necessária: mesmo restrito a ações (BDI 2), o preço
do COTAHIST continua sem ajuste. A própria B3 declara que "as cotações são
fornecidas na moeda e forma de cotação da época, sem nenhum ajuste para a
inflação ou proventos (dividendos, bonificações, direitos de subscrição, etc.)"
(b3.com.br, página de Cotações Históricas). Verificado na base 2019-2026: após
filtrar só BDI 2, ainda restam centenas de saltos diários acima de 60% em ações
reais (AMER3, PDGR3 e outras que fizeram grupamento), e o campo `fator_cotacao`
sinalizou apenas 2 eventos em toda a base. Por isso `retorno_diario_maximo`
existe: é o que pega as quebras que nem o BDI nem o fator_cotacao capturam.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BDI_LOTE_PADRAO = 2
BDI_FUNDOS_IMOBILIARIOS = 12

# Sufixos de ticker de ações ordinárias/preferenciais/units. Direitos e recibos
# usam 1, 2, 9, 10, 12, 13, 14 etc. O filtro por codigo_bdi já resolve a maior
# parte; o sufixo é uma segunda barreira, útil quando o BDI vem ausente.
SUFIXOS_ACAO = ("3", "4", "5", "6", "7", "8", "11")


def marcar_descontinuidades(df: pd.DataFrame, max_dias_gap: int = 10) -> pd.DataFrame:
    """Anula o retorno calculado ATRAVÉS de buracos na série de um ticker.

    Por que isso é necessário: o filtro por `codigo_bdi` remove LINHAS, não
    tickers. Verificado na base 2019-2026: o código 58 mistura ações reais
    (AZUL4, CCXC3) com recibos de subscrição (AZUL53, AZUL54). Ou seja, um
    mesmo ticker pode ter parte dos pregões classificada como 2 e parte como
    58. Ao manter só o BDI 2, a série daquele ticker fica com um buraco no
    meio, e `pct_change()` passa a comparar dois preços separados por semanas
    como se fossem pregões consecutivos — inventando um retorno de um dia que
    nunca existiu. O mesmo vale para papéis suspensos e depois reabertos.

    Esta função adiciona `dias_desde_pregao_anterior` e `retorno_valido`
    (False quando o intervalo excede `max_dias_gap`), para que os cálculos de
    retorno possam descartar essas transições em vez de tratá-las como normais.
    """
    d = df.sort_values(["ticker", "data_pregao"]).copy()
    dias = d.groupby("ticker", group_keys=False)["data_pregao"].diff().dt.days
    d["dias_desde_pregao_anterior"] = dias
    d["retorno_valido"] = ~(dias > max_dias_gap).fillna(False)
    n_invalidos = int((~d["retorno_valido"]).sum())
    if n_invalidos:
        print(f"Descontinuidades: {n_invalidos} transição(ões) com intervalo > {max_dias_gap} "
              f"dias em {d.loc[~d['retorno_valido'], 'ticker'].nunique()} ticker(s). "
              "O retorno através delas foi marcado como inválido.")
    return d


def filtrar_universo(
    df: pd.DataFrame,
    codigos_bdi: tuple[int, ...] = (BDI_LOTE_PADRAO,),
    preco_minimo: float = 1.0,
    volume_mediano_minimo: float = 1_000_000.0,
    janela_liquidez: int = 60,
    negocios_minimos: int = 100,
    exigir_sufixo_acao: bool = True,
    retorno_diario_maximo: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Restringe a base ao universo efetivamente investível.

    IMPORTANTE — o filtro de liquidez é CAUSAL (média móvel para trás, por
    pregão), não estático. Um filtro do tipo "manter tickers cujo volume MÉDIO
    NO PERÍODO TODO passou de X" usaria informação futura para decidir o que
    era negociável no passado, o que é viés de sobrevivência disfarçado: você
    estaria escolhendo hoje os ativos que se sabe terem sido líquidos depois.

    Parâmetros:
      codigos_bdi: quais códigos manter. Padrão só (2,) = ações em lote padrão.
        Para incluir FIIs, passe (2, 12).
      preco_minimo: descarta pregões com preço abaixo disso. Em papéis de
        centavos, um tick mínimo de R$ 0,01 já representa dezenas de por cento
        de "retorno" que nunca seria capturável.
      volume_mediano_minimo: volume financeiro mediano (R$) na janela anterior.
      janela_liquidez: quantos pregões passados formam a mediana de liquidez.
      negocios_minimos: mediana do número de negócios na mesma janela.
      exigir_sufixo_acao: exige terminação de ticker compatível com ação.
      retorno_diario_maximo: DESATIVADO por padrão (None). Descartar a LINHA do
        salto não elimina o salto: recalculado o retorno sobre as linhas
        restantes, o pct_change costura as duas pontas e reproduz a mesma
        variação (verificado: AMER3 com grupamento manteve +13.866% mesmo com a
        linha removida). Pior, o descarte abre um buraco novo na série. O
        limiar correto é aplicado ao RETORNO, no momento em que ele é
        calculado — ver `_retorno_com_gap` em grafo_estrategia.py. Este
        parâmetro fica aqui apenas para inspeção pontual.

    Retorna (df_filtrado, relatorio) — o relatório traz quantas linhas cada
    etapa removeu, para auditoria.
    """
    etapas = []
    total_inicial = len(df)
    d = df.copy()

    def registrar(nome: str, antes: int, depois: int) -> None:
        etapas.append({
            "etapa": nome,
            "linhas_antes": antes,
            "linhas_depois": depois,
            "removidas": antes - depois,
            "pct_removido": round((antes - depois) / antes * 100, 2) if antes else 0.0,
        })

    if "codigo_bdi" in d.columns:
        antes = len(d)
        d = d[d["codigo_bdi"].isin(codigos_bdi)]
        registrar(f"codigo_bdi em {codigos_bdi}", antes, len(d))
    else:
        etapas.append({"etapa": "codigo_bdi AUSENTE no arquivo (filtro pulado)",
                       "linhas_antes": len(d), "linhas_depois": len(d),
                       "removidas": 0, "pct_removido": 0.0})

    if exigir_sufixo_acao:
        antes = len(d)
        d = d[d["ticker"].str.strip().str.endswith(SUFIXOS_ACAO)]
        registrar("sufixo de ticker compatível com ação", antes, len(d))

    antes = len(d)
    d = d[d["preco_fechamento"] > 0]
    registrar("preço de fechamento > 0", antes, len(d))

    antes = len(d)
    d = d[d["preco_fechamento"] >= preco_minimo]
    registrar(f"preço >= R$ {preco_minimo:.2f}", antes, len(d))

    d = d.sort_values(["ticker", "data_pregao"])

    if "volume_financeiro" in d.columns and volume_mediano_minimo > 0:
        antes = len(d)
        # shift(1) garante que a liquidez usada em cada pregão vem só do passado
        vol_mediano = d.groupby("ticker", group_keys=False)["volume_financeiro"].transform(
            lambda s: s.shift(1).rolling(janela_liquidez, min_periods=janela_liquidez // 2).median()
        )
        d = d[vol_mediano >= volume_mediano_minimo]
        registrar(f"volume mediano ({janela_liquidez}d, causal) >= R$ {volume_mediano_minimo:,.0f}",
                  antes, len(d))

    if "numero_negocios" in d.columns and negocios_minimos > 0:
        antes = len(d)
        neg_mediano = d.groupby("ticker", group_keys=False)["numero_negocios"].transform(
            lambda s: s.shift(1).rolling(janela_liquidez, min_periods=janela_liquidez // 2).median()
        )
        d = d[neg_mediano >= negocios_minimos]
        registrar(f"nº de negócios mediano ({janela_liquidez}d, causal) >= {negocios_minimos}",
                  antes, len(d))

    if retorno_diario_maximo is not None:
        antes = len(d)
        ret = d.groupby("ticker", group_keys=False)["preco_fechamento"].pct_change()
        d = d[~(ret.abs() > retorno_diario_maximo).fillna(False)]
        registrar(f"|retorno diário| <= {retorno_diario_maximo:.0%}", antes, len(d))

    relatorio = pd.DataFrame(etapas)
    if total_inicial:
        print(f"Universo: {total_inicial:,} -> {len(d):,} linhas "
              f"({len(d) / total_inicial * 100:.1f}% mantidas) | "
              f"{df['ticker'].nunique()} -> {d['ticker'].nunique()} tickers")
    return d.reset_index(drop=True), relatorio


def ajustar_por_fator_cotacao(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza preços pela base de cotação informada no COTAHIST.

    O campo `fator_cotacao` indica em que base o preço está expresso (1 = preço
    unitário; 1000 = preço por lote de mil). Quando ele muda para um ticker, a
    série tem uma quebra que não é retorno econômico. Dividir o preço pelo
    fator põe toda a série na mesma base unitária.

    Ressalva importante, verificada empiricamente: na base 2019-2026 esse campo
    sinalizou apenas 2 eventos em 3.201 tickers, número baixo demais para
    cobrir os desdobramentos e grupamentos que de fato ocorreram no período. Ou
    seja, este ajuste é necessário mas NÃO é suficiente: mantenha também o
    filtro `retorno_diario_maximo` de `filtrar_universo`, que pega as quebras
    que o campo não sinalizou.
    """
    if "fator_cotacao" not in df.columns:
        return df
    d = df.copy()
    fator = pd.to_numeric(d["fator_cotacao"], errors="coerce").fillna(1).replace(0, 1)
    for coluna in ("preco_abertura", "preco_maximo", "preco_minimo",
                   "preco_medio", "preco_fechamento"):
        if coluna in d.columns:
            d[coluna] = d[coluna] / fator
    return d