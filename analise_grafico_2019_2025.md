# Análise do Gráfico de Backtest (2019-2025): Diagnóstico e Melhorias

## 1. O Gráfico está preciso? (Diagnóstico de Erros)

**Não. O gráfico apresenta um erro crítico de renderização e estruturação dos dados subjacentes.** 
O que vemos na imagem não é a volatilidade real das estratégias, mas sim um "artefato visual" (frequentemente chamado de efeito "código de barras" ou "zig-zag"). 

### O que está acontecendo visualmente?
Se você observar as linhas de cada estratégia (principalmente os grandes blocos de cor), elas estão oscilando violentamente na vertical a cada ponto de dado:
- **Estratégia 2 (Azul Claro):** Oscila freneticamente entre uma linha base (que parece ser a curva de capital real em crescimento/queda) e um teto rigorosamente plano fixado na marca de 500.000.
- **Estratégias 3, 4 e 5 (Vermelho, Verde, Rosa):** Apresentam o sintoma invertido. O seu capital real parece desenhar a silhueta no topo dos picos, enquanto o fundo das linhas cai abruptamente de volta para perto de zero (ou um valor de linha base muito baixo) diariamente.

### Causas Técnicas Prováveis:
1. **Índices Duplicados / Dados Intercalados:** O DataFrame que está sendo passado para a biblioteca de gráficos (Plotly/Streamlit) provavelmente tem múltiplas entradas para a mesma data. A biblioteca desenha uma linha conectando o "Valor do Portfólio (ex: 180k)" ao valor de uma variável estática ou não preenchida do mesmo dia (ex: "Caixa Inicial = 500k"), e no dia seguinte faz o mesmo caminho.
2. **Falha no Pivot ou Melt:** Se os dados de diferentes estratégias vieram num formato "*long*" (melted) e não foram agrupados (pivot) corretamente pelo index de datas, a linha sendo traçada pula entre a Estratégia X e a Estratégia Y sequencialmente.
3. **Ausência de `ffill()` em falhas de dados:** Dias sem trades ou valores nulos sendo mapeados para 0 em vez de receberem um _forward-fill_ (replicar o saldo do dia útil anterior).

---

## 2. Como Melhorar a Apresentação para um Período Longo (6 anos)

Compreender de 2019 a 2025 abrange mais de 1500 dias úteis e várias condições extremas de mercado (como a crise de 2020). Plota-se 7 linhas (5 estratégias + 2 benchmarks), então, mesmo corrigindo os erros do ponto 1, teríamos o que chamam de _"Spaghetti Chart"_ (gráfico confuso, difícil interpretação). 

Para elevar para nível institucional (padrão Itaú Quant), você deve aplicar as seguintes melhorias:

### A. Normalização na Base 100 (Rebase)
As curvas e os benchmarks devem obrigatoriamente começar do cruzamento no valor **100** (ou 0%) no primeiro dia do backtest (2019).
* **Por que?** Um benchmark começando em 100k e a estratégia em 500k arruina a sensibilidade direcional. Com todos saindo de 100, no final, a linha em "150" representa diretamente +50% de rendimento acumulado absoluto, viabilizando comparação perfeitamente nivelada.

### B. Uso de Escala Logarítmica (Eixo Y)
Para 6 anos, ativos sofrem juros compostos consideravelmente. Um crescimento no gráfico linear faz com que ganhos em 2019 pareçam irrelevantes comparados a quedas num capital bem maior em 2024.
* **Solução:** Use o eixo logarítmico (`fig.update_yaxes(type="log")`). Numa escala log, a rampa angular mostra perfeitamente as proporções de ganho de percentual constante não importando o valor nominal.

### C. Subplots Separados: Drawdowns (Curva Submersa)
Analisar apenas curva de equidade ao longo de 6 anos é ocultar risco. 
* **Solução:** Reduza a altura do gráfico principal de equidade e anexe logo abaixo um _Area Chart_ preenchido de vermelho apontando para baixo (0% até -50%), mapeando os _Drawdowns_. Isso salienta o risco da estratégia e o tempo de recuperação (Underwater Period), um requisito severo na avaliação de robôs institucionais.

### D. Estrutura "Small Multiples" (Facet grids)
Ao invés de cruzar as 5 estratégias umas contra e sobre as outras, que tal dividi-las?
* Crie visões comparativas separadas sob demanda: Uma aba ou seletor onde o chart master exibe a **Estratégia Escolhida vs Ibovespa vs Selic**. Menos cores simultâneas equivalem a decisões mais bem inferidas no _dashboard_.

### E. Suavização (Resampling)
Uma nuvem com mais de mil pontos para linha excede os pixels monitorados horizontais. 
* **Solução Visual:** Utilize reamostragem semanal do capital no momento unicamente voltado a renderização gráfica (`df.resample('W').last()`), mantendo os cálculos de taxa sobre o dado real, diário. Destaque maior será dado na tendência geral sem a confusão fina e a variação intratrês-dias visual.
