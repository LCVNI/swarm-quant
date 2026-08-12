# Roadmap de Implementação — `app_grafo.py`

> **Importante:** as três fases abaixo devem ser implementadas **uma de cada vez**, nunca simultaneamente. Cada fase deve ser concluída, testada e validada antes de iniciar a seguinte. Misturar fases dificulta isolar a causa de qualquer resultado inesperado — especialmente relevante na Fase 3, que pode alterar o resultado da estratégia.

---

## Fase 1 — Benchmarks visuais (SELIC + Ibovespa) no gráfico de capital
**Prioridade: máxima e imediata.** Escopo puramente visual, sem impacto na lógica da estratégia.

### Objetivo
Sobrepor as curvas de capital equivalente da SELIC e do Ibovespa à curva de capital da estratégia, nos dois modos do app (execução única e comparação das 5 estratégias).

### O que muda

**`metricas_risco.py`** — adicionar duas funções novas, generalizando a lógica já existente em `_retorno_selic_periodo` e `_retorno_ibov_periodo` (que hoje calculam só o retorno acumulado total) para produzir uma **série diária de capital**:

```python
def curva_capital_selic(selic: pd.Series, data_inicio, data_fim, capital_inicial: float) -> pd.Series:
    janela = selic[(selic.index >= data_inicio) & (selic.index <= data_fim)]
    return capital_inicial * (1 + janela).cumprod()

def curva_capital_ibovespa(ibovespa: pd.DataFrame, data_inicio, data_fim, capital_inicial: float) -> pd.Series:
    precos = ibovespa["fechamento_ajustado"]
    janela = precos[(precos.index >= data_inicio) & (precos.index <= data_fim)]
    return capital_inicial * (janela / janela.iloc[0])
```

**`app_grafo.py`** — nos dois blocos de `st.line_chart`:
- Modo "Rodar uma estratégia": substituir `st.line_chart(resumo.set_index("data_decisao")["capital_apos_periodo"])` por um DataFrame com 3 colunas (Estratégia, SELIC, Ibovespa).
- Modo "Comparar as 5 estratégias": calcular as curvas de benchmark **uma única vez** (fora do loop das 5 estratégias, pois não dependem da estratégia) e adicioná-las ao dicionário `curvas` antes de `st.line_chart(pd.DataFrame(curvas))`.

### Alinhamento temporal
SELIC e Ibovespa são diárias; a curva da estratégia é discreta (um ponto a cada `horizonte` pregões, só em datas de decisão). Gerar os benchmarks em frequência diária cobrindo `data_min`–`data_max` do backtest e deixar o `st.line_chart` fazer o *outer join* pelos índices — evita interpolar/inventar capital da estratégia entre decisões.

### Impacto na estratégia
**Nenhum.** Não toca em `_backtest_com_sinal`, `gerar_sinal`, alocação, custos ou impostos. É camada de visualização sobre resultado já calculado, com o mesmo princípio causal já usado em `calcular_metricas_risco` (sem look-ahead).

---

## Fase 2 — Gráficos complementares de análise
**Prioridade: alta, após validar a Fase 1.** Também sem impacto na estratégia; só expõe dados que, em sua maioria, já são calculados internamente mas descartados ou só exibidos como tabela/texto.

Ordem sugerida de implementação (do mais barato ao mais caro):

| Gráfico | Fonte dos dados | Função de origem | Cálculo novo? |
|---|---|---|---|
| DARF mensal (barras) | `ir_mensal["darf_a_pagar"]` | `calcular_ir_mensal` (`grafo_estrategia.py`) | Nenhum |
| Custo acumulado vs. lucro bruto acumulado | `operacoes["custo"]`, `operacoes["lucro"]` | `_backtest_com_sinal` (`grafo_estrategia.py`) | Nenhum (`.cumsum()`) |
| Composição do universo por código BDI (pizza/barras) | saída de `composicao_por_bdi(df)` | `diagnostico_artefatos.py` | Nenhum |
| Retornos extremos por tipo de instrumento (barras) | `resumo_bdi` (merge de `retornos_extremos` com `codigo_bdi`) | `diagnostico_artefatos.py` | Nenhum |
| Drawdown ao longo do tempo (área) | série `drawdown` já computada internamente | `calcular_metricas_risco` (`metricas_risco.py`) | Pequeno (expor série já calculada) |
| Distribuição do lucro por operação (histograma) | `operacoes["lucro"]` | `_backtest_com_sinal` | Nenhum (só binning) |
| Retorno mensal em heatmap (calendário) | agregação de `resumo` por mês | padrão já usado em `calcular_ir_mensal` | Pequeno (reaproveita `groupby("mes")`) |
| Dispersão sinal previsto vs. retorno realizado | `operacoes["sinal"]` vs `operacoes["retorno_realizado"]` | `_backtest_com_sinal` | Nenhum |
| Beta rolling vs. Ibovespa | `retorno_periodo`/`retorno_ibov_periodo` internos | `calcular_metricas_risco` | Moderado (janela móvel) |
| Densidade/grau médio do grafo ao longo do tempo | não existe hoje como coluna de saída | precisa nova instrumentação em `_backtest_com_sinal` | Maior (única exceção da lista) |

### Impacto na estratégia
**Nenhum**, com exceção do último item (densidade do grafo), que exige apenas *registrar* uma métrica adicional durante o loop de backtest — não altera decisão de compra/venda.

---

## Fase 3 — Aplicação do filtro de universo investível (`universo.py`)
**Prioridade: importante, mas NÃO urgente. Fazer por último, com calma.**

> ⚠️ **Atenção redobrada:** esta fase, ao contrário das duas anteriores, **pode alterar o resultado da estratégia**. Diferente de um ajuste visual, aqui estamos mudando o dado de entrada do backtest. Deve ser tratada com estudo aprofundado, testes comparativos (antes/depois do filtro) e validação cuidadosa — o objetivo é **aproximar** o backtest da realidade operacional, não afastá-lo. Qualquer ajuste malfeito aqui pode introduzir um viés novo (ex.: filtro excessivo removendo ativos legítimos, ou parâmetros de liquidez mal calibrados).

### Diagnóstico atual
`app_grafo.py` hoje **não chama `universo.py` em nenhum ponto**. A função `ge.carregar_dados` (`grafo_estrategia.py`) filtra apenas `tipo_mercado == 10` (mercado à vista) — que a própria docstring de `universo.py` já avisa ser insuficiente, pois mistura ações com direitos de subscrição, FIIs, BDRs e papéis em recuperação judicial.

### O que mudar (com cautela)
1. Integrar `filtrar_universo` (de `universo.py`) ao fluxo de carregamento de dados do `app_grafo.py`, antes de `ge.construir_features_grafo`.
2. Aplicar `ajustar_por_fator_cotacao` para tratar quebras de preço por eventos corporativos (desdobramento/grupamento), já que o COTAHIST não vem ajustado.
3. Usar `marcar_descontinuidades` para invalidar retornos calculados através de buracos na série (ex.: ticker que migrou de BDI 2 para BDI 58 e voltou).
4. **Não ativar `retorno_diario_maximo`** como solução principal — o próprio módulo documenta que descartar a linha do salto não elimina o salto (o `pct_change` seguinte "costura" as pontas e reproduz a mesma distorção). Esse parâmetro serve só para inspeção pontual.
5. Expor no app os parâmetros de `filtrar_universo` (código BDI, preço mínimo, volume mediano mínimo, janela de liquidez) como controles configuráveis, com os valores padrão do módulo.

### Validação recomendada antes de ir para produção
- Rodar o backtest **com e sem** o filtro no mesmo período e comparar os relatórios de `filtrar_universo` (quantas linhas cada etapa remove) e de `diagnostico_artefatos.py` (composição por BDI, retornos extremos).
- Conferir se o filtro de liquidez é de fato causal (usa `shift(1).rolling(...)`, olhando só passado) — já é o caso na implementação atual, mas deve ser reconferido após qualquer alteração.
- Testar sensibilidade dos parâmetros (`volume_mediano_minimo`, `janela_liquidez`, `negocios_minimos`) em mais de um período, para garantir que o filtro não está descartando ativos líquidos por parâmetro mal calibrado.

### Impacto na estratégia
**Real e esperado.** O objetivo é justamente que os resultados reflitam o que seria executável no mundo real — retornos vindos de instrumentos não-ação, saltos de preço não ajustados e ativos ilíquidos devem deixar de contaminar o backtest. Espera-se retorno bruto mais baixo (e mais realista) após o filtro.

---

## Resumo executivo

| Fase | O que faz | Impacto na estratégia | Urgência |
|---|---|---|---|
| 1 | Benchmarks SELIC/Ibovespa no gráfico | Nenhum (visual) | Imediata |
| 2 | Gráficos complementares de análise | Nenhum (visual, exceto densidade do grafo) | Alta |
| 3 | Filtro de universo investível | Sim (dado de entrada) | Importante, mas exige estudo — fazer por último |

**Fontes reaproveitadas:** `metricas_risco.py` (`_retorno_selic_periodo`, `_retorno_ibov_periodo`, `calcular_metricas_risco`), `grafo_estrategia.py` (`_backtest_com_sinal`, `calcular_ir_mensal`, `carregar_dados`), `diagnostico_artefatos.py` (`composicao_por_bdi`, `retornos_extremos`), `universo.py` (`filtrar_universo`, `ajustar_por_fator_cotacao`, `marcar_descontinuidades`), `app_grafo.py` (estrutura atual de session_state e gráficos).