# Indicadores de Desempenho e Risco para o Desafio Quant AI 2026

No contexto do **Desafio Quant AI 2026 da Itaú Asset**, a avaliação não se baseia apenas no "lucro absoluto". Em tesourarias institucionais e asset managements, o retorno financeiro só tem valor se o risco tomado for simétrico e controlado. O Edital e o Guia valorizam estratégias que apresentem retornos consistentes, proteção contra quedas bruscas e descorrelação com o mercado tradicional.

Abaixo estão as explicações dos principais indicadores que **devem** constar no relatório final da estratégia.

---

## 1. Indicadores de Risco vs. Retorno Histórico

### 📌 Índice de Sharpe (Sharpe Ratio)
**O que é:** Mede o retorno excedente (acima da taxa livre de risco, geralmente o CDI no Brasil) por cada unidade de risco (volatilidade) tomada.  
**Fórmula Básica:** `(Retorno da Estratégia - Retorno do CDI) / Volatilidade da Estratégia`  
**Por que no Relatório (Itaú):** É o indicador institucional mais famoso do mundo quant. Um Sharpe superior a `1.0` indica que a estratégia gera valor real. Um Sharpe muito alto (ex: `+2.0`) mostra que os ganhos são quase "linhas retas" para cima, sem sustos, o que é altamente premiado em competições Quant, pois fundos preferem consistência a saltos esporádicos.

### 📌 Maximum Drawdown (Rebaixamento Máximo)
**O que é:** A pior queda histórica de capital que a estratégia já sofreu do pico até o fundo.  
**Por que no Relatório (Itaú):** Em gestão de fundos da Itaú Asset, um Max Drawdown elevado (ex. -30%) causa pânico em cotistas e exige paradas na mesa (stop loss institucional). Demonstrar que o *Market Graph* da B3 é capaz de gerar bons lucros com um Drawdown contido (idealmente entre -5% e -15%) provará ao júri que o algoritmo possui excelente gestão de risco em crises. Fator eliminatório muitas vezes.

### 📌 Sortino Ratio (O Primo do Sharpe)
**O que é:** Semelhante ao Sharpe, porém ele **só penaliza a volatilidade negativa** (dias de queda).  
**Por que é Interessante:** Estratégias quantitativas baseadas em *Spillover* podem ter altos saltos para cima. O Sharpe penaliza esses saltos por tratar todos os desvios como volatilidade indesejada. O Sortino mostra ao júri que a variação da nossa curva de capital vem de grandes lucros (positividade), e não de instabilidade sistêmica.

---

## 2. Indicadores de Perfil e Correlação Sistêmica

### 📌 Beta (Exposição ao Mercado)
**O que é:** Mede a sensibilidade da estratégia em relação ao Ibovespa (Benchmark). Um Beta de `1` anda junto com o IBOV. Um Beta `> 1` é muito mais submisso e agressivo às oscilações da Bolsa.  
**Por que no Relatório (Itaú):** A grande busca da Itaú Asset em teses Quants modernas frequentemente foca em fundos "Beta Neutro" (`Beta próximo de 0`). Se o nosso algoritmo tem Beta `0.1` ou `-0.1`, a gente argumenta brilhantemente no relatório que **"A estratégia gera ganhos absolutos que independem de o Ibovespa estar subindo ou caindo"**. Isso vale ouro em fundos Multimercado Quantitativos.

### 📌 Alpha de Jensen (A Mágica da Estratégia)
**O que é:** O rendimento autônomo gerado que supera o rendimento esperado pelo fator Beta do mercado. É o famoso "valor adicionado pelo algoritmo".  
**Por que no Relatório (Itaú):** Ter um **Alpha Positivo consistente** atesta que a nossa tese matemática topológica (Market Graph) captura de fato assimetrias que o mercado eficiente não precifica de imediato. É a prova matemática rigorosa de que "estamos extraindo valor intrínseco, não apenas pegando carona na bolsa".

---

## 3. Outros Indicadores Complementares Essenciais no Relatório

### 📊 Win Rate (Taxa de Acerto ou Hit Ratio)
**O que é:** Percentual de operações encerradas no lucro versus o total operado.  
**Por que incluir:** Modelos de convergência e de reversão (como o *Spillover* dos vértices) costumam ostentar taxas de acerto mais elevadas (frequentemente `60-65%`). Expor essa simetria de vitórias traz confiança técnica ao relatório de que o ruído branco do mercado é mitigado pela bolha de correlação.

### 📊 Profit Factor (Fator de Lucro)
**O que é:** A soma de todo o dinheiro ganho (Gross Profit) dividida pela soma de todo o dinheiro perdido (Gross Loss).  
**Por que incluir:** Um *Profit Factor* > `1.5` ou `2.0` demonstra tremenda estabilidade. Atesta que o nosso caixa engole confortavelmente os custos perversos de corretagem e B3 modelados na arquitetura de custos de vocês.

### 📊 Calmar Ratio
**O que é:** O Retorno Anualizado dividido pelo Maximum Drawdown absoluto.  
**Por que incluir:** É uma prova rápida para comparativos robustos. Quem extrai maiores rendimentos ao longo dos anos, com as menores covas de prejuízos possíveis na linha do tempo? Muito requisitado.

---

### Síntese para o Relatório Final (Júri do Desafio Quant)
No relatório ou notebook de apresentação final, deve-se construir uma tabela de métricas com a síntese desses KPIs listados. A principal linha estratégica de vendas do nosso modelo deve ser a comprovação de que gerar robôs que acertam mais do que dão prejuízo é fundamental, mas robôs com **Beta Neutro, Drawdown engessado e Alpha proeminente** formam o santo graal das Assets brasileiras, enquadrando rigorosamente o caso de uso nos guias avaliativos propostos pelo Edital do Itaú.
