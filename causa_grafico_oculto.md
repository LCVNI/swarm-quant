# Causa: Ocultação do Gráfico da Estratégia em Janelas Curtas (1 ano)

## O Problema Técnico
Você notou que, ao analisar apenas 1 ano de dados, a linha da estratégia "desaparece" do gráfico de evolução do capital, restando visíveis apenas o Ibovespa e a Selic, embora o rótulo da estratégia continue na legenda.

## A Causa Raiz: Esparsidade de Dados + Junção (Outer Join)

O problema ocorre na forma como a biblioteca gráfica (`st.line_chart` do Streamlit, baseada em Altair) lida com lacunas (`NaN`) em séries temporais combinadas em `app_grafo.py`.

A cronologia matemática no código é a seguinte:
1. **O Robô Opera por Janelas (T+5):** Segundo a `grafo_estrategia.py`, o horizonte de operação é 5. Logo, a série temporal da estratégia (variável `resumo`) gera apenas 1 ponto de dados a cada 5 pregões.
2. **Os Benchmarks são Diários:** O Ibovespa e o CDI/Selic possuem um valor para **todos os dias úteis**.
3. **O Desalinhamento (Outer Join):** No `app_grafo.py`, ocorre a junção das três curvas:
   ```python
   curva_df = curva_df.join(_selic_curva.rename("SELIC"), how="outer")
   curva_df = curva_df.join(_ibov_curva.rename("Ibovespa"), how="outer")
   ```
   Isso força o DataFrame a ter uma linha para cada dia do ano (cerca de 252 linhas). Como a sua estratégia só muda a cada 5 dias, entre dois pontos válidos da sua curva haverá 4 linhas com valor vazio (`NaN`).
4. **Comportamento do `st.line_chart`:** O Streamlit não desenha uma linha conectando dois pontos se houver valores nulos (`NaN`) entre eles. Ele simplesmente oculta a linha daquela série (ou a exibe como minúsculos pontos isolados e quase invisíveis no fundo), mas desenha normalmente as linhas do Ibov e Selic, que são 100% preenchidas.

### Por que só acontece (ou piora) em períodos de 1 ano?
Quando você usa 1 ano de dados, os primeiros ~120 dias ainda são consumidos pelo "período de treinamento" (`min_dias_treino`). Sobram pouco mais de ~130 dias para operações reais.
A cada 5 dias operando em 130 disponíveis, sua curva (`resumo`) termina com estressantes curtos **~25 pontos de dados soltos** mergulhados em meio a **mais de 200 pontos das outras curvas**. A esparsidade se torna tão grande que a linha colapsa visualmente.

## Como Resolver?
A correção requer a aplicação da técnica matemática de _Forward Fill_ (**ffill**), preenchendo os "dias ociosos" (entre compra e venda) onde o capital que está travado na operação (ou em caixa) simplesmente reflete o último saldo conhecido. 

No `app_grafo.py`, logo antes do `st.line_chart(curva_df)`, a seguinte linha resolve permanentemente esse *bug*:

```python
# Propaga o saldo para os dias em que o robô não executou operações
curva_df = curva_df.ffill().fillna(capital_inicial)
st.line_chart(curva_df)
```
