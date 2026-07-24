# Estratégia feita por Vagner para o desafio do Itaú Quant A.I
Para rodar: python -m streamlit run app_grafo.py

## Explicação estratégia:
Como estrategia usando teoria de grafos para cada data de decisão, calcula a correlação dos retornos diários das ações nos últimos N pregões, então você controla essa janela e monta um grafo onde só entra aresta se a correlação passar de um limia. Depois, para cada ação, compara o retorno recente dela com a média (ponderada pela força da correlação) do retorno recente das suas "vizinhas" no grafo. Ação com sinal alto = grupo correlacionado subiu, ela ainda não acompanhou

## Grafo:
- Construção do grafo: correlação de Pearson (pandas.DataFrame.corr(), método padrão) entre os retornos diários de cada par de ações, numa janela móvel de N pregões, só com dados anteriores à decisão.
- Threshold/limiar: só vira aresta se |correlação| >= limiar — essa é a parte "market graph" propriamente dita.
- Sinal de decisão: média ponderada do retorno recente dos vizinhos de 1 salto (peso = força da correlação), comparada ao retorno recente do próprio nó. Isso é simplesmente uma média ponderada sobre vizinhança direta, não é um algoritmo de grafo sofisticado (por enquanto)

## Como futuro pode melhorar para:
como futuro pode melhorar para:
- Árvore geradora mínima (minimum spanning tree), abordagem de Mantegna, popular em outra vertente da mesma literatura (econofísica) pra simplificar o grafo de correlação numa estrutura hierárquica Springer
- Métricas de centralidade (PageRank, centralidade de autovetor, betweenness) para ranquear ações por importância estrutural na rede
- Detecção de comunidades (ex: algoritmo de Louvain) pra identificar clusters de ações que se movem juntas, em vez de olhar só vizinhança direta
- Graph Neural Networks, que é a linha que mencionei na sua pergunta anterior, e que eu decidi não implementar pelo custo/risco de overfitting que expliquei antes
