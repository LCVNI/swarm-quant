"""Mitigação de artefatos de preço (desdobramento/grupamento não ajustado no
COTAHIST) que contaminam o retorno usado no backtest.

CONTEXTO DO PROBLEMA (ver diagnostico_artefatos.py e universo.py do projeto):
- `fator_cotacao` só sinaliza uma fração pequena dos eventos reais (verificado
  empiricamente: 2 eventos em 3.201 tickers na base 2019-2026).
- O parâmetro `retorno_diario_maximo` de `universo.filtrar_universo` já existe
  mas é DESLIGADO por padrão porque descartar a linha do salto não resolve:
  o `pct_change` seguinte "costura" as duas pontas e reproduz a mesma
  distorção (caso testado: AMER3 manteve +13.866% mesmo com a linha removida).
- O verdadeiro ponto de contaminação do lucro é o `retorno_futuro` calculado
  em `grafo_estrategia.construir_features_grafo` — um retorno de N pregões à
  frente que nunca passa pelo filtro diário de `universo.py`.

O QUE ESTE MÓDULO FAZ (mitigação, não solução definitiva — ver ressalvas no
docstring de `tratar_eventos_societarios`):
1. Reaproveita `diagnostico_artefatos.retornos_extremos` como detector.
2. Invalida (NaN) o `retorno_futuro` de qualquer decisão cuja janela de
   holding [t, t+horizonte] contenha um salto de preço suspeito — isso é
   suficiente para o motor de backtest (`_backtest_com_sinal`) já ignorar
   essas linhas automaticamente, pois ele descarta NaN em retorno_futuro
   antes de gerar qualquer sinal.
3. Também invalida `retorno_1d`/`retorno_5d` no PRÓPRIO dia do salto, para
   que o grafo de correlação (que usa `retorno_1d` na janela móvel) não seja
   distorcido pelo mesmo evento.

Dependência: precisa estar na mesma pasta que `diagnostico_artefatos.py` e
`grafo_estrategia.py` do projeto (importa as duas).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import diagnostico_artefatos as da
import grafo_estrategia as ge

LIMIAR_EVENTO_PADRAO = da.LIMIAR_RETORNO_SUSPEITO  # 0.60, mesmo limiar do diagnóstico


def _janela_futura_maxima_abs(serie_retorno_1d: pd.Series, horizonte: int) -> pd.Series:
    """Para cada linha t, retorna o maior |retorno_1d| observado nas próximas
    `horizonte` linhas da MESMA série (assume-se já ordenada por data para um
    único ticker). Usado para checar se algum pregão dentro da janela de
    holding [t+1, t+horizonte] teve um salto suspeito."""
    abs_r = serie_retorno_1d.abs()
    colunas_futuras = [abs_r.shift(-k) for k in range(1, horizonte + 1)]
    return pd.concat(colunas_futuras, axis=1).max(axis=1)


def tratar_eventos_societarios(
    df_features: pd.DataFrame,
    horizonte: int,
    limiar: float = LIMIAR_EVENTO_PADRAO,
) -> pd.DataFrame:
    """Recebe o DataFrame já processado por `construir_features_grafo` (ou
    seja, já contém `retorno_1d`, `retorno_5d`, `retorno_futuro`) e devolve
    uma cópia com as linhas contaminadas por saltos de preço suspeitos
    invalidadas (NaN), prontas para o motor de backtest simplesmente ignorar.

    RESSALVAS IMPORTANTES (não esconder isso do time nem do relatório):
    - `limiar` é uma heurística de magnitude, não uma confirmação do evento
      societário. Um rali genuíno e muito forte (ex. num short squeeze real)
      pode ser removido por engano; um grupamento com razão pequena pode não
      ser pego.
    - Isto NÃO cria uma série de preços "ajustada" de verdade — só evita que
      a observação contaminada entre no cálculo de retorno. O ajuste correto
      exigiria uma base de eventos societários oficiais da B3 (proventos),
      que este projeto ainda não consome.
    - Depois de aplicar, rode `diagnostico_artefatos.concentracao_do_lucro`
      nas operações resultantes para confirmar que a concentração de lucro
      em poucos trades caiu — isto é uma mitigação, valide o resultado.
    """
    df = df_features.sort_values(["ticker", "data_pregao"]).copy()

    if "retorno_1d" not in df.columns:
        raise ValueError(
            "Rode grafo_estrategia.construir_features_grafo(df, horizonte) "
            "antes de chamar tratar_eventos_societarios."
        )

    # --- 1) Contaminação do RESULTADO (retorno_futuro / P&L da operação) ---
    # Para cada linha, olha se algum pregão dentro da janela de holding
    # [t+1, t+horizonte] teve |retorno_1d| acima do limiar.
    maximo_futuro = df.groupby("ticker", group_keys=False)["retorno_1d"].apply(
        lambda s: _janela_futura_maxima_abs(s, horizonte)
    )
    evento_na_janela_holding = maximo_futuro.reindex(df.index) > limiar

    n_contaminados = int(evento_na_janela_holding.sum())
    if n_contaminados:
        print(
            f"[tratamento_eventos_societarios] {n_contaminados} decisão(ões) "
            f"com janela de holding ({horizonte} pregões) contendo salto de "
            f"preço > {limiar:.0%}. retorno_futuro invalidado nessas linhas."
        )
    df.loc[evento_na_janela_holding, "retorno_futuro"] = np.nan

    # --- 2) Contaminação do SINAL/GRAFO (retorno_1d / retorno_5d no dia do evento) ---
    # O próprio dia do salto não deve alimentar a matriz de correlação nem o
    # momentum recente.
    evento_no_dia = df["retorno_1d"].abs() > limiar
    n_dias_evento = int(evento_no_dia.sum())
    if n_dias_evento:
        print(
            f"[tratamento_eventos_societarios] {n_dias_evento} pregão(ões) "
            f"com retorno diário > {limiar:.0%} (o próprio dia do salto). "
            "retorno_1d/retorno_5d invalidados nesses dias para não "
            "distorcer o grafo de correlação."
        )
    df.loc[evento_no_dia, ["retorno_1d", "retorno_5d"]] = np.nan

    return df


def construir_features_grafo_realista(
    df: pd.DataFrame,
    horizonte: int,
    limiar_evento: float = LIMIAR_EVENTO_PADRAO,
) -> pd.DataFrame:
    """Wrapper de conveniência: roda o pipeline padrão de features do projeto
    e em seguida aplica a mitigação de eventos societários. Use este no lugar
    de `grafo_estrategia.construir_features_grafo` diretamente."""
    df_features = ge.construir_features_grafo(df, horizonte=horizonte)
    return tratar_eventos_societarios(df_features, horizonte=horizonte, limiar=limiar_evento)
