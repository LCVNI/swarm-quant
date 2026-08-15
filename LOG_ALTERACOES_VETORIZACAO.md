# LOG DE ALTERAÇÕES — Vetorização de Grafos

**Data**: 2026-08-14  
**Arquivo modificado**: `grafo_estrategia.py`  
**Plano de referência**: `plano_otimizacao.md`

---

## Resumo Geral

Substituição dos laços `for` aninhados O(N²) em Python puro por operações vetorizadas via **NumPy** e **Pandas** (implementadas em C), com inserção de arestas em lote via `nx.from_pandas_edgelist()`. Nenhuma mudança na API externa — os mesmos inputs produzem os mesmos grafos.

---

## 1. `construir_grafo_correlacao` (linhas 87–120)

### ANTES (código removido)
```python
grafo.add_nodes_from(corr.columns)
colunas = list(corr.columns)
for i, t1 in enumerate(colunas):
    for t2 in colunas[i + 1:]:
        peso = corr.loc[t1, t2]
        if pd.notna(peso) and abs(peso) >= limiar_correlacao:
            grafo.add_edge(t1, t2, weight=float(peso))
```

### DEPOIS (código inserido)
```python
# 1. Máscara Matricial: triangular superior (exclui diagonal e espelho)
mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)

# 2. Aplainamento (Stack): transforma a matriz em Series (source, target) -> weight
arestas = corr.where(mask).stack().reset_index()
arestas.columns = ["source", "target", "weight"]

# 3. Broadcasting de Filtro: filtra NaN e aplica limiar de correlação
arestas = arestas[arestas["weight"].abs() >= limiar_correlacao]

# 4. Inserção em Volume (Batch Edges): monta o grafo de uma só vez
grafo = nx.from_pandas_edgelist(arestas, source="source", target="target", edge_attr="weight")

# Garante que todos os nós existam, mesmo sem arestas (nós isolados)
grafo.add_nodes_from(corr.columns)
```

### O que mudou e por quê

| Aspecto | Antes | Depois |
|---------|-------|--------|
| **Loop** | `for i, t1 in enumerate(...)` + `for t2 in colunas[i+1:]` — O(N²) iterações em Python puro | Eliminado. `np.triu` + `stack()` fazem o mesmo em C |
| **Filtro** | `if pd.notna(peso) and abs(peso) >= limiar` — comparação escalar por iteração | `arestas["weight"].abs() >= limiar` — broadcasting vetorial SIMD |
| **Inserção** | `grafo.add_edge(t1, t2, weight=...)` — uma chamada NetworkX por aresta | `nx.from_pandas_edgelist()` — injeção única em lote |
| **Nós isolados** | `grafo.add_nodes_from()` antes do loop | `grafo.add_nodes_from()` após a edgelist (mesmo efeito) |

---

## 2. `construir_grafo_mst` (linhas 153–182)

### ANTES (código removido)
```python
grafo_completo = nx.Graph()
colunas = list(corr.columns)
for i, t1 in enumerate(colunas):
    for t2 in colunas[i + 1:]:
        d = distancia.loc[t1, t2]
        if pd.notna(d):
            grafo_completo.add_edge(t1, t2, weight=float(d), correlacao=float(corr.loc[t1, t2]))
if grafo_completo.number_of_edges() == 0:
    return nx.Graph()
```

### DEPOIS (código inserido)
```python
# 1. Máscara Matricial: triangular superior (exclui diagonal e espelho)
mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)

# 2. Aplainamento (Stack): DataFrames empilhados com weight (distância) e correlação
dist_stack = distancia.where(mask).stack().reset_index()
dist_stack.columns = ["source", "target", "weight"]
corr_stack = corr.where(mask).stack().reset_index()
corr_stack.columns = ["source", "target", "correlacao"]

# Junta distância + correlação num único DataFrame
arestas_df = dist_stack.copy()
arestas_df["correlacao"] = corr_stack["correlacao"]

# Remove pares com distância NaN
arestas_df = arestas_df.dropna(subset=["weight"])

if arestas_df.empty:
    return nx.Graph()

# 3. Inserção em Volume: monta o grafo completo de uma só vez
grafo_completo = nx.from_pandas_edgelist(
    arestas_df, source="source", target="target",
    edge_attr=["weight", "correlacao"],
)
```

### O que mudou e por quê

| Aspecto | Antes | Depois |
|---------|-------|--------|
| **Loop** | `for i, t1 in enumerate(...)` + `for t2 in colunas[i+1:]` — O(N²) em Python | Eliminado. Duas chamadas `stack()` (uma para distância, outra para correlação) |
| **Atributos múltiplos** | `add_edge(t1, t2, weight=d, correlacao=corr)` — 2 lookups `.loc[]` por iteração | `edge_attr=["weight", "correlacao"]` — passados em lote via DataFrame |
| **Guarda vazia** | `if grafo_completo.number_of_edges() == 0` após o loop completo | `if arestas_df.empty` — checagem antes da construção do grafo |
| **MST** | Idêntica: `nx.minimum_spanning_tree(grafo_completo, weight="weight")` | Sem alteração |

---

## Impacto Esperado

- **CPU**: Toda a computação pesada (mask, stack, filtro) roda em C (NumPy/Pandas), liberando o GIL do CPython.
- **Memória**: Mesmo consumo assintótico — a matriz de correlação já existia; agora é empilhada temporariamente.
- **Resultado matemático**: **Idêntico**. As mesmas arestas, os mesmos pesos — apenas o caminho de construção mudou.
