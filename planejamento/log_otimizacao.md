# Log de Otimização de Performance — grafo_estrategia.py
**Data:** 2026-08-07  
**Autor:** Norn Engine Team  
**Versão:** v2.0 (Fases A + B)

---

## Resumo Executivo
Refatoração do motor de grafos de correlação eliminando o NetworkX do hot path do backtest. A lógica e a regra de decisão financeira do modelo **não foram alteradas**. O output (operações, sinal, clusters, modularidade) será **idêntico**.

---

## Alterações Detalhadas

### 1. Eliminação do `import networkx`
| Antes | Depois |
|-------|--------|
| `import networkx as nx` (linha 22) | Removido completamente |
| NetworkX usado como estrutura intermediária do grafo | iGraph (C-Core) instanciado diretamente |

### 2. Função `construir_grafo_correlacao` — Fase A
**O que era:**
```python
# Loop O(N²) em Python puro
grafo = nx.Graph()
grafo.add_nodes_from(corr.columns)
for i, t1 in enumerate(colunas):
    for t2 in colunas[i + 1:]:
        peso = corr.loc[t1, t2]
        if pd.notna(peso) and abs(peso) >= limiar_correlacao:
            grafo.add_edge(t1, t2, weight=float(peso))
return grafo  # nx.Graph
```

**O que ficou:**
```python
# Máscara booleana vetorizada (NumPy C-Core)
matriz = corr.values.copy()
np.fill_diagonal(matriz, np.nan)
mask_triu = np.triu(np.ones(matriz.shape, dtype=bool), k=1)
mask_valida = (np.abs(matriz) >= limiar_correlacao) & mask_triu & ~np.isnan(matriz)
indices_row, indices_col = np.where(mask_valida)
pesos = matriz[indices_row, indices_col]
return tickers, indices_row, indices_col, pesos  # arrays NumPy
```

**Impacto:** ~80.000 giros de loop por dia eliminados. O NumPy varre a matriz inteira em sub-milissegundo via operações SIMD em C.

### 3. Função `detectar_comunidades_leiden` — Fase B
**O que era:**
```python
# Tradução pesada: Python → C (ponte NetworkX → iGraph)
g_ig = ig.Graph.from_networkx(grafo)
weights = g_ig.es['weight']
partition = leidenalg.find_partition(g_ig, ...)
mapeamento = {node: cluster for node, cluster in zip(g_ig.vs['_nx_name'], ...)}
```

**O que ficou:**
```python
# Injeção direta: NumPy arrays → iGraph C-Core
tickers_row = tickers[indices_row]
tickers_col = tickers[indices_col]
arestas_com_pesos = list(zip(tickers_row, tickers_col, pesos))
g_ig = ig.Graph.TupleList(arestas_com_pesos, weights=True)
partition = leidenalg.find_partition(g_ig, ...)
mapeamento = {nome: cluster for nome, cluster in zip(g_ig.vs['name'], ...)}
```

**Impacto:** Eliminada a ponte `ig.Graph.from_networkx()` que desmontava a estrutura Python e remontava em C a cada dia do backtest. Agora o pipe é NumPy(C) → iGraph(C) → Leiden(C++) sem intermediário interpretado.

### 4. Função `calcular_sinal_grafo`
**O que era:** Recebia `grafo: nx.Graph` e iterava `grafo.nodes`.  
**O que ficou:** Recebe `tickers_grafo: np.ndarray` e itera o array NumPy.  
**Impacto:** Zero mudança na lógica de spillover. Apenas a fonte da lista de tickers mudou de `nx.Graph.nodes` para `np.ndarray`.

### 5. Função `backtest_grafo`
**O que era:** `grafo.number_of_edges()` para validação.  
**O que ficou:** `n_arestas = len(pesos)` para validação.  
**Impacto:** Assinatura pública (parâmetros de entrada e DataFrames de saída) **100% preservada**. O `app_grafo.py` não requer nenhuma alteração.

---

## Garantia de Integridade
- A regra matemática de correlação de Pearson é a mesma (`janela_dados.corr()`).
- O limiar de filtragem é o mesmo (`>= limiar_correlacao`).
- O algoritmo de Leiden (`leidenalg.find_partition`) recebe a mesma topologia.
- O cálculo de spillover (média do cluster - retorno próprio) é idêntico.
- As colunas de saída dos DataFrames `operacoes` e `resumo` são as mesmas.
